// Checks that need the whole set of concept files or the vendored REST v2
// spec. Run directly for a report; `--strict` also fails on warnings (CI).

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { loadConcepts, REPO_ROOT, SPEC_PATH } from "./load.ts";
import type { Concept } from "./schema.ts";

export interface Report {
  concepts: Concept[];
  errors: string[];
  warnings: string[];
}

type JsonSchema = {
  $ref?: string;
  properties?: Record<string, unknown>;
  allOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  anyOf?: JsonSchema[];
};

interface Spec {
  paths: Record<string, unknown>;
  components: { schemas: Record<string, JsonSchema> };
}

// Property names of a schema, following $ref and allOf/oneOf/anyOf.
function specProperties(spec: Spec, schema: JsonSchema | undefined, seen = new Set<string>()): Set<string> {
  const names = new Set<string>();
  if (!schema) return names;
  if (schema.$ref) {
    const name = schema.$ref.split("/").pop()!;
    if (seen.has(name)) return names;
    seen.add(name);
    return specProperties(spec, spec.components.schemas[name], seen);
  }
  for (const key of Object.keys(schema.properties ?? {})) names.add(key);
  for (const part of [...(schema.allOf ?? []), ...(schema.oneOf ?? []), ...(schema.anyOf ?? [])]) {
    for (const key of specProperties(spec, part, seen)) names.add(key);
  }
  return names;
}

// Every file is public-facing. These name internal systems, internal source
// ids or private repositories; the rule has to be restated from a public source.
const SENSITIVE: [RegExp, string][] = [
  [/\b(learning|glossary|entity|arch|domain|workflow|failure_mode):/i, "an internal source id"],
  [/\breq:[A-Z]/, "an internal requirement id"],
  [/\b(spec|doc):[a-z]/, "an internal design doc id"],
  [/\b(planetscale|tinybird|snowflake|mysql|redis|kafka)\b/i, "internal infrastructure"],
  [/\bhost[ -]daemon\b|\brphttp2?\b|\bgql-api\b|\bhapi\b|\boutbox\b/i, "an internal service"],
  [/\bcontext[ -]mcp\b|\bdev (graphql )?schema\b/i, "an internal source"],
  [/\bfeature[ -]flag/i, "unreleased behavior behind a flag"],
  [/runpod\/(RunPod|host|ai-api|hapi|proxy|rphttp2)\b/, "a private repository"],
  [/\b(gold|silver|bronze)\.[a-z_]+|\bfct_[a-z_]+/i, "an internal warehouse table"],
  [/\b(Linear|Notion|Zendesk|Slack)\b/, "an internal tool"],
  [/\binternal (design|doc|docs|requirement|requirements|learning|learnings|source|sources)\b/i, "an internal source"],
  [/\bv[01] (said|says|claimed|claims|marked|recorded|cited|listed|had)\b|\bontology\b/i, "the ontology's own drafts"],
];

// Wording that is only true for a while. Statements say what holds; when a
// fact may change, evidence carries the date it was checked.
const TIME_BOUND: RegExp[] = [
  /\bcurrently\b/i,
  /\bas of\b/i,
  /\bat the moment\b/i,
  /\bfor now\b/i,
  /\brecently\b/i,
  /\btoday\b/i,
  /\bnot yet\b/i,
  /\bsoon\b/i,
  /\bupcoming\b/i,
  /\bPR #?\d+/i,
];

function excerpt(text: string, pattern: RegExp): string {
  const at = text.search(pattern);
  return text
    .slice(Math.max(0, at - 20), at + 40)
    .replace(/\s+/g, " ")
    .trim();
}

// Every human-readable string in a concept, with where it sits. URLs are left
// out: a public docs URL may contain words the patterns above look for.
function strings(concept: Concept): { path: string; text: string }[] {
  const out: { path: string; text: string }[] = [];
  const walk = (value: unknown, path: string) => {
    if (typeof value === "string") {
      if (!path.endsWith(".url")) out.push({ path, text: value });
    } else if (Array.isArray(value)) {
      for (const [index, item] of value.entries()) walk(item, `${path}[${index}]`);
    } else if (value && typeof value === "object") {
      for (const [key, item] of Object.entries(value)) walk(item, path ? `${path}.${key}` : key);
    }
  };
  walk(concept, "");
  return out;
}

// "mounts.network[].volumeId" -> "mounts"
const fieldRoot = (name: string) => name.split(/[.[]/)[0]!;

export function validate(dir?: string, specPath = SPEC_PATH, repoRoot = REPO_ROOT): Report {
  const { concepts, errors } = loadConcepts(dir);
  const warnings: string[] = [];
  const byId = new Map(concepts.map((concept) => [concept.id, concept]));
  const ruleIds = new Map<string, string>();

  for (const concept of concepts) {
    for (const rule of concept.rules) {
      if (ruleIds.has(rule.id))
        errors.push(`${concept.id}: rule id ${rule.id} is also used in ${ruleIds.get(rule.id)}`);
      ruleIds.set(rule.id, concept.id);
    }
  }

  const spec: Spec | undefined = existsSync(specPath) ? JSON.parse(readFileSync(specPath, "utf8")) : undefined;
  if (!spec) warnings.push(`no REST v2 spec at ${specPath}; spec checks skipped`);

  for (const concept of concepts) {
    const where = concept.id;
    const ref = (label: string, target: string | null | undefined) => {
      if (target && !byId.has(target)) errors.push(`${where}: ${label} "${target}" is not a concept`);
    };

    ref("is_a", concept.is_a);
    ref("part_of", concept.part_of);
    for (const relation of concept.relations) ref(`relation ${relation.type}`, relation.target);
    for (const field of concept.fields) ref(`field ${field.name} ref`, field.ref);
    if (concept.summary.trim() === "TODO") warnings.push(`${where}: summary is TODO`);

    for (const { path, text } of strings(concept)) {
      for (const [pattern, why] of SENSITIVE) {
        if (pattern.test(text)) errors.push(`${where}: ${path} mentions ${why}: "${excerpt(text, pattern)}"`);
      }
      for (const pattern of TIME_BOUND) {
        if (pattern.test(text))
          errors.push(
            `${where}: ${path} is time-bound ("${excerpt(text, pattern)}"); state it so it stays true, or cite the checked date in evidence`,
          );
      }
    }

    // Processes: steps only on kind process, at least two, unique ids, and every
    // concept and rule a step names must exist.
    if (concept.kind === "process" && concept.steps.length < 2)
      errors.push(`${where}: a process needs at least two steps`);
    if (concept.kind !== "process" && concept.steps.length) errors.push(`${where}: only kind process may have steps`);
    const stepIds = new Set<string>();
    for (const step of concept.steps) {
      if (stepIds.has(step.id)) errors.push(`${where}: step id ${step.id} is used twice`);
      stepIds.add(step.id);
      for (const target of step.concepts) ref(`step ${step.id} concept`, target);
      for (const ruleId of step.rules) {
        if (!ruleIds.has(ruleId)) errors.push(`${where}: step ${step.id} names rule ${ruleId}, which is not a rule`);
      }
    }

    const fieldNames = new Set(concept.fields.map((field) => field.name));
    const stateNames = new Set(Object.keys(concept.states?.values ?? {}));
    const actionNames = new Set(concept.states?.transitions.map((transition) => transition.action) ?? []);

    for (const transition of concept.states?.transitions ?? []) {
      for (const state of [...transition.from, transition.to]) {
        if (!stateNames.has(state))
          errors.push(`${where}: transition ${transition.action} names unknown state ${state}`);
      }
    }

    for (const rule of concept.rules) {
      if (!rule.id.startsWith(`${concept.id}.`))
        errors.push(`${where}: rule ${rule.id} must start with "${concept.id}."`);
      for (const target of rule.applies_to) {
        const [kind, name] = [target.slice(0, target.indexOf(":")), target.slice(target.indexOf(":") + 1)];
        const known = kind === "field" ? fieldNames : kind === "state" ? stateNames : actionNames;
        if (!known.has(name))
          errors.push(`${where}: rule ${rule.id} applies_to ${target}, which ${where} does not declare`);
      }
      for (const see of rule.see) {
        if (!ruleIds.has(see)) errors.push(`${where}: rule ${rule.id} sees ${see}, which is not a rule`);
      }
      // Skill evidence cites a file in this repo, so a rename or deletion fails here.
      for (const evidence of rule.evidence) {
        if (evidence.source === "skill" && evidence.path && !existsSync(join(repoRoot, evidence.path))) {
          errors.push(`${where}: rule ${rule.id} cites skill file ${evidence.path}, which does not exist`);
        }
      }
      if (rule.conflict && rule.evidence.length < 2) {
        warnings.push(`${where}: rule ${rule.id} is a conflict with fewer than two pieces of evidence`);
      }
    }

    // Spec checks: named schemas and paths exist; every field on a concept with a
    // REST schema exists on that schema or its Create/Update request body.
    const rest = concept.surfaces.rest_v2;
    if (spec && rest) {
      for (const path of rest.paths) {
        if (!(path in spec.paths)) errors.push(`${where}: rest_v2 path ${path} is not in the spec`);
      }
      if (rest.schema) {
        if (!spec.components.schemas[rest.schema]) {
          errors.push(`${where}: rest_v2 schema ${rest.schema} is not in the spec`);
        } else {
          const known = new Set<string>();
          for (const name of [rest.schema, `Create${rest.schema}Request`, `Update${rest.schema}Request`]) {
            for (const key of specProperties(spec, spec.components.schemas[name])) known.add(key);
          }
          for (const field of concept.fields) {
            if (!known.has(fieldRoot(field.name))) {
              errors.push(`${where}: field ${field.name} is not on ${rest.schema} or its create/update request`);
            }
          }
        }
      }
    }
  }

  // Hierarchy must be a tree: no concept is its own ancestor.
  for (const key of ["is_a", "part_of"] as const) {
    for (const concept of concepts) {
      const seen = new Set<string>();
      let current: Concept | undefined = concept;
      while (current?.[key]) {
        if (seen.has(current.id)) {
          errors.push(`${concept.id}: ${key} chain loops`);
          break;
        }
        seen.add(current.id);
        current = byId.get(current[key]!);
      }
    }
  }

  return { concepts, errors, warnings };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const strict = process.argv.includes("--strict");
  const { concepts, errors, warnings } = validate();
  const rules = concepts.reduce((total, concept) => total + concept.rules.length, 0);
  for (const warning of warnings) console.log(`warn  ${warning}`);
  for (const error of errors) console.log(`error ${error}`);
  console.log(`${concepts.length} concepts, ${rules} rules, ${errors.length} errors, ${warnings.length} warnings`);
  process.exit(errors.length || (strict && warnings.length) ? 1 : 0);
}
