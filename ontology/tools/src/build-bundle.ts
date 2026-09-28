// Packs the plugin's knowledge into one JSON file for other programs, such as
// the Runpod MCP server: every skill with its reference docs, the golden paths,
// and the validated concept files.
//
//   node src/build-bundle.ts [out.json]     default: ../../packages/knowledge/knowledge.json

import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { REPO_ROOT } from "./load.ts";
import type { Concept } from "./schema.ts";
import { validate } from "./validate.ts";

export const BUNDLE_FORMAT = 1;
export const DEFAULT_BUNDLE_PATH = join(REPO_ROOT, "packages/knowledge/knowledge.json");
const PLUGIN_DIR = join(REPO_ROOT, "plugins/runpod");
const SKILLS_DIR = join(PLUGIN_DIR, "skills");
const GOLDEN_DIR = join(SKILLS_DIR, "runpod/golden-paths");

export interface Guide {
  /** skill: "runpod-usage"; reference: "runpod-usage/storage"; golden path: "golden-path/06-dev-pod". */
  id: string;
  kind: "skill" | "reference" | "golden-path";
  title: string;
  description: string;
  /** Repo-relative path of the source file. */
  path: string;
  /** Tools the guide drives. Golden paths only, read from their "Lane" line. */
  lanes: string[];
  /** True when the guide needs a shell (runpodctl, flash, SSH, docker, hf, aws). */
  needs_shell: boolean;
  body: string;
}

export interface Bundle {
  format: typeof BUNDLE_FORMAT;
  version: string;
  commit: string;
  built_at: string;
  guides: Guide[];
  concepts: Concept[];
}

// Lane names as they appear in golden-path "Lane" lines.
const LANES: [string, RegExp][] = [
  ["runpodctl", /runpodctl/i],
  ["runpod-mcp", /\bMCP\b/],
  ["flash", /\bflash\b/i],
  ["ssh", /\bSSH\b/i],
  ["docker", /\bdocker\b/i],
  ["hf", /\bhf\b/],
  ["aws", /\baws\b/i],
  ["rest", /\bREST\b/],
];
const SHELL_LANES = new Set(["runpodctl", "flash", "ssh", "docker", "hf", "aws"]);

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

function guide(kind: Guide["kind"], id: string, file: string, description?: string): Guide {
  const { meta, body } = splitFrontmatter(readFileSync(file, "utf8"));
  const laneLine = kind === "golden-path" ? (body.match(/\*\*Lane(?:\(s\))?:?\*\*:?[^\n]*|Lane:[^*\n]*/)?.[0] ?? "") : "";
  const lanes = LANES.filter(([, pattern]) => pattern.test(laneLine)).map(([lane]) => lane);
  const skillShell = kind !== "golden-path" && /^(runpodctl|flash|companion-clis)(\/|$)/.test(id);
  return {
    id,
    kind,
    title: title(body, id),
    description: description ?? (typeof meta.description === "string" ? meta.description.trim() : summary(body)),
    path: relative(REPO_ROOT, file),
    lanes,
    needs_shell: skillShell || lanes.some((lane) => SHELL_LANES.has(lane)),
    body: body.trim(),
  };
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

export function collectGuides(): Guide[] {
  const guides: Guide[] = [];
  for (const skill of readdirSync(SKILLS_DIR).sort()) {
    const skillFile = join(SKILLS_DIR, skill, "SKILL.md");
    try {
      statSync(skillFile);
    } catch {
      continue;
    }
    guides.push(guide("skill", skill, skillFile));
    const referenceDir = join(SKILLS_DIR, skill, "reference");
    try {
      for (const file of markdownFiles(referenceDir)) {
        const name = relative(referenceDir, file).replace(/\.md$/, "");
        guides.push(guide("reference", `${skill}/${name}`, file));
      }
    } catch {
      // This skill has no reference docs.
    }
  }
  for (const file of markdownFiles(GOLDEN_DIR)) {
    if (file === join(GOLDEN_DIR, "README.md")) continue;
    // "02-comfyui-pod/README.md" -> "02-comfyui-pod"; "02-comfyui-pod/variant-a.md" -> "02-comfyui-pod/variant-a"
    const name = relative(GOLDEN_DIR, file).replace(/\/README\.md$/, "").replace(/\.md$/, "");
    guides.push(guide("golden-path", `golden-path/${name}`, file));
  }
  return guides;
}

function gitCommit(): string {
  try {
    return execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: REPO_ROOT, encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}

export function buildBundle(concepts: Concept[]): Bundle {
  const { version } = JSON.parse(readFileSync(join(PLUGIN_DIR, ".claude-plugin/plugin.json"), "utf8")) as { version: string };
  return { format: BUNDLE_FORMAT, version, commit: gitCommit(), built_at: new Date().toISOString(), guides: collectGuides(), concepts };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const out = resolve(process.argv[2] ?? DEFAULT_BUNDLE_PATH);
  const { concepts, errors } = validate();
  if (errors.length) {
    for (const error of errors) console.error(`error ${error}`);
    console.error(`not building: ${errors.length} validation errors`);
    process.exit(1);
  }
  const bundle = buildBundle(concepts);
  const text = JSON.stringify(bundle);
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, text);
  const counts = (["skill", "reference", "golden-path"] as const).map((kind) => `${bundle.guides.filter((g) => g.kind === kind).length} ${kind}s`);
  console.log(`wrote ${basename(out)} ${bundle.version} (${counts.join(", ")}, ${concepts.length} concepts, ${(text.length / 1024).toFixed(0)} KB)`);
}
