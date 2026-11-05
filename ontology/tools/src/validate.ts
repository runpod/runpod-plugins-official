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

// The public repositories under github.com/runpod, the only ones a file may link
// to or cite. Extend the list when a new one is cited.
const PUBLIC_GITHUB_REPOS = new Set([
  "runpod-plugins-official",
  "runpodctl",
  "runpod-python",
  "runpod-mcp",
  "docs",
  "containers",
  "flash",
]);
// The names as pattern alternatives; a dot is the one character a repository
// name may hold that a pattern reads specially.
const PUBLIC_REPO_NAMES = [...PUBLIC_GITHUB_REPOS].map((repo) => repo.replaceAll(".", "\\.")).join("|");

// Every file is public-facing. These catch links to repositories that are not
// public and to internal tools, email addresses and credentials. `pnpm scan`
// applies them to every file under plugins/, packages/ and ontology/.
export const SENSITIVE: [RegExp, string][] = [
  // A public name may end in .git; a longer name that starts with one is not public.
  [
    new RegExp(`\\bgithub\\.com[/:]runpod/(?!(${PUBLIC_REPO_NAMES})(\\.git)?(?![\\w-]|\\.\\w))[\\w.-]+`, "i"),
    "a link to a Runpod repository that is not public",
  ],
  // The private repositories named without a link.
  [/runpod\/(RunPod|host|ai-api|hapi|proxy|rphttp2)\b/, "a private repository"],
  [/\b(linear\.app|notion\.(so|site)|slack\.com)\b/i, "an internal tool's link"],
  // Any address except one on a placeholder domain, a URL's user:password part,
  // a Runpod SSH login, a git login before a repository path (git@hf.co:org/model)
  // or git@github.com itself, and the contact addresses Runpod publishes. Each
  // exemption holds for the whole name only, not a longer one that starts with it.
  // The lookbehind is bounded so a long line stays linear.
  [
    /(?<![\w.%+-]|\/\/[^\s/@]{0,256})(?!(team|support|help)@runpod\.io(?![\w-]|\.\w)|git@[\w.-]+[:/]|git@github\.com(?![\w-]|\.\w))[\w.%+-]+@(?!(example\.(com|org|net)|ssh\.runpod\.io)(?![\w-]|\.\w))[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}\b/i,
    "an email address",
  ],
  // Credentials: the Runpod API and S3 key shapes plus common vendor tokens.
  [/\brpa_[A-Za-z0-9]{16,}\b/, "a Runpod API key"],
  [/\brps_[A-Za-z0-9]{16,}\b/, "a Runpod S3 API key"],
  [/\b(?:sk|pk|ghp|gho|phc|phx|xoxb|xoxp)[-_][A-Za-z0-9_-]{16,}\b/, "an API key"],
  [/\b(?:github_pat_[A-Za-z0-9_]{22,}|gh[usr]_[A-Za-z0-9]{36})\b/, "a GitHub token"],
  [/\bhf_[A-Za-z0-9]{30,}\b/, "a Hugging Face token"],
  [/\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/, "an AWS access key id"],
  [/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/, "a JWT"],
];

// Internal names and the concept graph's own source vocabulary, checked in
// concept text only, where the rule has to be restated from a public source. In
// other files they are ordinary text: `torch.nn.Linear`, a Redis cache, a Slack
// webhook, a ComfyUI "workflow:" key, or "v1 had" about REST v1.
const DRAFT_WORDING: [RegExp, string][] = [
  [/\breq:[A-Z]/, "an internal requirement id"],
  [/\b(spec|doc):[a-z]/, "an internal design doc id"],
  [/\b(planetscale|tinybird|snowflake|mysql|redis|kafka)\b/i, "internal infrastructure"],
  [/\bhost[ -]daemon\b|\brphttp2?\b|\bgql-api\b|\bhapi\b|\boutbox\b/i, "an internal service"],
  [/\bcontext[ -]mcp\b|\bdev (graphql )?schema\b/i, "an internal source"],
  [/\bfeature[ -]flag/i, "unreleased behavior behind a flag"],
  [/\b(gold|silver|bronze)\.[a-z_]+|\bfct_[a-z_]+/i, "an internal warehouse table"],
  [/\b(Linear|Notion|Zendesk|Slack)\b/, "an internal tool"],
  [/\b(learning|glossary|entity|arch|domain|workflow|failure_mode):/i, "an internal source id"],
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

// Hosts a URL may point at, in evidence and in a rule's statement or
// on_violation. Every file ships in a public npm package, so a URL anywhere else
// (a private repo, an internal tool, localhost) is an error. Extend the list when
// a new public source or public Runpod endpoint is cited.
const PUBLIC_HOSTS = new Set([
  "docs.runpod.io",
  "docs.docker.com",
  "api.runpod.io",
  "api.runpod.ai",
  "rest.runpod.io",
  "console.runpod.io",
  "mcp.runpod.io",
  "cli.runpod.net",
  "graphql-spec.runpod.io",
  "runpod.io",
  "www.runpod.io",
  "huggingface.co",
]);
// Public Runpod endpoints named per endpoint, per pod or per data center.
const PUBLIC_HOST_PATTERNS = [
  /^[a-z0-9-]+\.api\.runpod\.ai$/,
  /^[a-z0-9-]+\.proxy\.runpod\.net$/,
  /^s3api-[a-z0-9-]+\.runpod\.io$/,
];

/** Why a URL is not a public source, or null when it is. */
export function urlProblem(raw: string): string | null {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return "is not a URL";
  }
  if (url.protocol !== "https:") return "is not https";
  if (url.hostname === "github.com") {
    const [owner, repo] = url.pathname.split("/").filter(Boolean);
    if (owner === "runpod" && repo && PUBLIC_GITHUB_REPOS.has(repo)) return null;
    return "is not a public Runpod GitHub repository";
  }
  const host = url.hostname;
  if (PUBLIC_HOSTS.has(host) || PUBLIC_HOST_PATTERNS.some((pattern) => pattern.test(host))) return null;
  return `is on ${host}, which is not a public source host`;
}

/** A URL inside prose, without trailing punctuation. */
export const TEXT_URL = /(https?:\/\/[^\s`'"]*[^\s`'".,;:)])/g;
const RULE_TEXT = /^rules\[\d+\]\.(statement|on_violation)$/;

// Every human-readable string in a concept, with where it sits. URLs are
// returned apart: a public docs URL may contain words the patterns above look
// for, so URLs are checked against PUBLIC_HOSTS instead.
function strings(concept: Concept): { path: string; text: string; url: boolean }[] {
  const out: { path: string; text: string; url: boolean }[] = [];
  const walk = (value: unknown, path: string) => {
    if (typeof value === "string") {
      out.push({ path, text: value, url: path.endsWith(".url") });
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

    for (const { path, text, url } of strings(concept)) {
      if (url) {
        const problem = urlProblem(text);
        if (problem) errors.push(`${where}: ${path} ${problem}: "${text}"`);
        continue;
      }
      // An agent acts on a rule's text, so its URLs are held to the same hosts.
      // A placeholder such as <pod-id> or ${POD_ID} stands for one name.
      if (RULE_TEXT.test(path)) {
        for (const [link] of text.matchAll(TEXT_URL)) {
          const problem = urlProblem(link.replace(/<[^<>]+>|\$\{[^{}]+\}/g, "x"));
          if (problem) errors.push(`${where}: ${path} has a URL that ${problem}: "${link}"`);
        }
      }
      for (const [pattern, why] of [...SENSITIVE, ...DRAFT_WORDING]) {
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

    // Skill evidence cites a file in this repo, so a rename or deletion fails here.
    const checkSkillPaths = (label: string, evidence: Concept["rules"][number]["evidence"]) => {
      for (const item of evidence) {
        if (item.source === "skill" && item.path && !existsSync(join(repoRoot, item.path.replace(/#.*$/, "")))) {
          errors.push(`${where}: ${label} cites skill file ${item.path}, which does not exist`);
        }
      }
    };
    checkSkillPaths("states", concept.states?.evidence ?? []);

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
      checkSkillPaths(`rule ${rule.id}`, rule.evidence);
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
