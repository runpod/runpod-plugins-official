// Packs the plugin's knowledge into one JSON file for other programs, such as
// the Runpod MCP server: every skill with its reference docs, the golden paths,
// and the validated concept files.
//
//   node src/build-bundle.ts [out.json]   write the bundle (default: packages/knowledge/knowledge.json)
//   node src/build-bundle.ts --check      check golden-path frontmatter and links, write nothing (CI)
//   node src/build-bundle.ts --suggest    list concepts each golden path mentions but does not link

import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { REPO_ROOT } from "./load.ts";
import type { Concept } from "./schema.ts";
import { validate } from "./validate.ts";

export const BUNDLE_FORMAT = 2;
export const DEFAULT_BUNDLE_PATH = join(REPO_ROOT, "packages/knowledge/knowledge.json");
const PLUGIN_DIR = join(REPO_ROOT, "plugins/runpod");
const SKILLS_DIR = join(PLUGIN_DIR, "skills");

/** The tools a golden path can drive. Closed set, checked when a path declares `lanes`. */
export const LANE_NAMES = ["runpod-mcp", "runpodctl", "flash", "ssh", "docker", "hf", "aws", "rest", "console"] as const;
/** Whether an agent with only the Runpod MCP tools can finish a golden path. */
export const MCP_LEVELS = ["full", "partial", "none"] as const;
const SHELL_LANES = new Set(["runpodctl", "flash", "ssh", "docker", "hf", "aws"]);

export interface Guide {
  /** skill: "runpod-usage"; reference: "runpod-usage/storage"; golden path: "golden-path/06-dev-pod". */
  id: string;
  kind: "skill" | "reference" | "golden-path";
  title: string;
  description: string;
  /** Repo-relative path of the source file. */
  path: string;
  /** Tools a golden path drives, from its frontmatter. Empty for skills and reference docs. */
  lanes: string[];
  /** Whether an agent with only the MCP tools can finish a golden path. Null for skills and reference docs. */
  mcp: (typeof MCP_LEVELS)[number] | null;
  /** True when the guide needs a shell (runpodctl, flash, SSH, docker, hf, aws). */
  needs_shell: boolean;
  /** Concepts the guide is linked to, by any link below. */
  concepts: string[];
  body: string;
}

/**
 * A link from a guide to a concept.
 * - uses: a golden path works with the concept (declared in its frontmatter, or it is cited as a rule's evidence).
 * - explains: a skill declares the concept under metadata.concepts, or a skill or
 *   reference doc is cited as evidence by the concept's rules.
 */
export interface Link {
  from: string;
  to: string;
  type: "uses" | "explains";
  via: "frontmatter" | "evidence";
  /** For via: evidence, the rules that cite the guide. */
  rules?: string[];
}

export interface Bundle {
  format: typeof BUNDLE_FORMAT;
  version: string;
  commit: string;
  built_at: string;
  guides: Guide[];
  concepts: Concept[];
  links: Link[];
}

const title = (body: string, fallback: string) => body.match(/^#\s+(.+)$/m)?.[1]?.trim() ?? fallback;

/** The first prose paragraph, for guides without a frontmatter description. */
function summary(body: string): string {
  const paragraph = body
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .find((block) => block && !/^(#|\||```|<|---|- |\d+\. )/.test(block));
  const text = (paragraph ?? "").replace(/\s+/g, " ");
  return text.length > 240 ? `${text.slice(0, 237)}...` : text;
}

function splitFrontmatter(text: string): { meta: Record<string, unknown>; body: string } {
  const match = text.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!match) return { meta: {}, body: text };
  return { meta: (parse(match[1]!) ?? {}) as Record<string, unknown>, body: text.slice(match[0].length) };
}

function markdownFiles(dir: string): string[] {
  return readdirSync(dir)
    .sort()
    .flatMap((name) => {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) return markdownFiles(path);
      return name.endsWith(".md") ? [path] : [];
    });
}

const exists = (path: string) => {
  try {
    statSync(path);
    return true;
  } catch {
    return false;
  }
};

/** Every guide file with its id and kind, before reading it. */
function guideFiles(skillsDir: string): { id: string; kind: Guide["kind"]; file: string }[] {
  const files: { id: string; kind: Guide["kind"]; file: string }[] = [];
  const goldenDir = join(skillsDir, "runpod/golden-paths");
  for (const skill of readdirSync(skillsDir).sort()) {
    const skillFile = join(skillsDir, skill, "SKILL.md");
    if (!exists(skillFile)) continue;
    files.push({ id: skill, kind: "skill", file: skillFile });
    const referenceDir = join(skillsDir, skill, "reference");
    if (!exists(referenceDir)) continue;
    for (const file of markdownFiles(referenceDir)) {
      files.push({ id: `${skill}/${relative(referenceDir, file).replace(/\.md$/, "")}`, kind: "reference", file });
    }
  }
  if (!exists(goldenDir)) return files;
  for (const file of markdownFiles(goldenDir)) {
    if (file === join(goldenDir, "README.md")) continue;
    // "02-comfyui-pod/README.md" -> "02-comfyui-pod"; "02-comfyui-pod/variant-a.md" -> "02-comfyui-pod/variant-a"
    const name = relative(goldenDir, file).replace(/\/README\.md$/, "").replace(/\.md$/, "");
    files.push({ id: `golden-path/${name}`, kind: "golden-path", file });
  }
  return files;
}

/**
 * Reads every guide and links it to the concepts. Errors name a golden path with
 * missing frontmatter or an unknown lane, mcp level or concept id, and a skill
 * with missing or unknown metadata.concepts.
 */
export function collectGuides(
  concepts: Concept[],
  skillsDir = SKILLS_DIR,
  root = REPO_ROOT,
): { guides: Guide[]; links: Link[]; errors: string[] } {
  const conceptIds = new Set(concepts.map((concept) => concept.id));
  const errors: string[] = [];
  const links: Link[] = [];

  // Rules whose evidence cites a repo file, by path: the evidence links.
  const citing = new Map<string, Map<string, string[]>>();
  for (const concept of concepts) {
    for (const rule of concept.rules) {
      for (const evidence of rule.evidence) {
        if (evidence.source !== "skill" || !evidence.path) continue;
        const path = evidence.path.trim().replace(/#.*$/, "");
        const byConcept = citing.get(path) ?? new Map<string, string[]>();
        byConcept.set(concept.id, [...new Set([...(byConcept.get(concept.id) ?? []), rule.id])]);
        citing.set(path, byConcept);
      }
    }
  }

  const declare = (id: string, path: string, value: unknown, type: Link["type"]) => {
    if (!Array.isArray(value) || !value.length) {
      errors.push(`${path}: concepts must be a non-empty list`);
      return;
    }
    for (const target of value.map(String)) {
      if (!conceptIds.has(target)) errors.push(`${path}: concept "${target}" is not a concept`);
      else links.push({ from: id, to: target, type, via: "frontmatter" });
    }
  };

  const guides = guideFiles(skillsDir).map(({ id, kind, file }): Guide => {
    const { meta, body } = splitFrontmatter(readFileSync(file, "utf8"));
    const path = relative(root, file);
    let lanes: string[] = [];
    let mcp: Guide["mcp"] = null;

    if (kind === "golden-path") {
      if (!Array.isArray(meta.lanes) || !meta.lanes.length) errors.push(`${path}: lanes must be a non-empty list`);
      else lanes = meta.lanes.map(String);
      for (const lane of lanes) {
        if (!(LANE_NAMES as readonly string[]).includes(lane)) errors.push(`${path}: lane "${lane}" is not one of ${LANE_NAMES.join(", ")}`);
      }
      if (!(MCP_LEVELS as readonly unknown[]).includes(meta.mcp)) errors.push(`${path}: mcp must be one of ${MCP_LEVELS.join(", ")}`);
      else mcp = meta.mcp as Guide["mcp"];
      declare(id, path, meta.concepts, "uses");
    } else if (kind === "skill") {
      // Skills keep their links under metadata, which skill loaders pass through.
      const metadata = (meta.metadata ?? {}) as Record<string, unknown>;
      declare(id, path, metadata.concepts, "explains");
    }

    for (const [target, rules] of citing.get(path) ?? []) {
      links.push({ from: id, to: target, type: kind === "golden-path" ? "uses" : "explains", via: "evidence", rules });
    }

    const skillShell = kind !== "golden-path" && /^(runpodctl|flash|companion-clis)(\/|$)/.test(id);
    return {
      id,
      kind,
      title: title(body, id),
      description: typeof meta.description === "string" ? meta.description.trim() : summary(body),
      path,
      lanes,
      mcp,
      needs_shell: skillShell || lanes.some((lane) => SHELL_LANES.has(lane)),
      concepts: [],
      body: body.trim(),
    };
  });

  for (const guide of guides) {
    guide.concepts = [...new Set(links.filter((link) => link.from === guide.id).map((link) => link.to))].sort();
  }
  return { guides, links, errors };
}

/**
 * Concepts a golden path mentions by name or alias but does not declare, most
 * mentioned first: candidates for its `concepts` frontmatter, for a person to review.
 */
export function suggestConcepts(guide: Guide, concepts: Concept[], minimum = 2): { concept: string; mentions: number }[] {
  const text = guide.body;
  return concepts
    .filter((concept) => concept.kind !== "platform" && !guide.concepts.includes(concept.id))
    .map((concept) => {
      const names = [concept.id, concept.name, ...concept.aliases].filter((name) => name.length >= 3);
      const mentions = names.reduce((total, name) => {
        const escaped = name.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
        // Short all-caps aliases (DC, NV) must match case; everything else ignores case.
        const flags = name === name.toUpperCase() && name.length <= 4 ? "g" : "gi";
        return total + (text.match(new RegExp(`(?<![\\w-])${escaped}(?![\\w-])`, flags))?.length ?? 0);
      }, 0);
      return { concept: concept.id, mentions };
    })
    .filter((hit) => hit.mentions >= minimum)
    .sort((a, b) => b.mentions - a.mentions);
}

function gitCommit(): string {
  try {
    return execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: REPO_ROOT, encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}

export function buildBundle(concepts: Concept[]): { bundle: Bundle; errors: string[] } {
  const { version } = JSON.parse(readFileSync(join(PLUGIN_DIR, ".claude-plugin/plugin.json"), "utf8")) as { version: string };
  const { guides, links, errors } = collectGuides(concepts);
  return {
    bundle: { format: BUNDLE_FORMAT, version, commit: gitCommit(), built_at: new Date().toISOString(), guides, concepts, links },
    errors,
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const { concepts, errors: conceptErrors } = validate();
  const { bundle, errors } = buildBundle(concepts);
  for (const error of [...conceptErrors, ...errors]) console.error(`error ${error}`);
  if (conceptErrors.length || errors.length) {
    console.error(`not building: ${conceptErrors.length + errors.length} errors`);
    process.exit(1);
  }

  const paths = bundle.guides.filter((g) => g.kind === "golden-path");
  const linkedConcepts = new Set(bundle.links.map((link) => link.to));
  const exampleConcepts = new Set(bundle.links.filter((link) => link.from.startsWith("golden-path/")).map((link) => link.to));

  if (args.includes("--suggest")) {
    // Candidate concepts for every golden path, to review before writing frontmatter.
    for (const guide of paths) {
      const hits = suggestConcepts(guide, concepts).slice(0, 8);
      const declared = guide.concepts.length ? ` linked: ${guide.concepts.join(", ")};` : "";
      console.log(`${guide.id}${declared} mentions: ${hits.map((h) => `${h.concept}(${h.mentions})`).join(", ") || "-"}`);
    }
    process.exit(0);
  }
  if (args.includes("--check")) {
    console.log(`links ok: ${bundle.links.length} links across ${bundle.guides.length} guides`);
    process.exit(0);
  }

  const out = resolve(args.find((arg) => !arg.startsWith("--")) ?? DEFAULT_BUNDLE_PATH);
  const text = JSON.stringify(bundle);
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, text);
  const counts = (["skill", "reference", "golden-path"] as const).map((kind) => `${bundle.guides.filter((g) => g.kind === kind).length} ${kind}s`);
  console.log(`wrote ${basename(out)} ${bundle.version} (${counts.join(", ")}, ${concepts.length} concepts, ${(text.length / 1024).toFixed(0)} KB)`);
  console.log(`links: ${bundle.links.length}; concepts with a guide ${linkedConcepts.size}/${concepts.length}, with an example ${exampleConcepts.size}/${concepts.length}`);
}
