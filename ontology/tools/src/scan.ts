// Checks what ships in the plugin and @runpod/plugin-knowledge.
//
//   node src/scan.ts               every text file under plugins/, packages/ and ontology/ against SENSITIVE
//   node src/scan.ts --base <dir>  also list what the concept rules add over the concept
//                                  files in <dir>, a copy of the files at the base commit
//
// The list is informational: it goes to $GITHUB_STEP_SUMMARY when set, else to
// stdout. Of the additions, only a container image with a namespace outside
// runpod/ fails.

import { appendFileSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { parse } from "yaml";
import { CONCEPTS_DIR, REPO_ROOT } from "./load.ts";
import { SENSITIVE, TEXT_URL } from "./validate.ts";

// Names Git ignores, build output (the bundle is rebuilt from the scanned files
// when the package is packed), and paths that hold what the checks reject on
// purpose: the pattern table and the test fixtures. A file with a NUL byte, such
// as an npm pack tarball, is skipped as binary.
const SKIP = new Set([
  "node_modules",
  ".flash",
  "ontology/build",
  "packages/knowledge/knowledge.json",
  "ontology/tools/src/validate.ts",
  "ontology/tools/test",
]);

export interface Finding {
  file: string;
  line: number;
  why: string;
}

function walk(root: string, dir: string): string[] {
  return readdirSync(join(root, dir))
    .sort()
    .flatMap((name) => {
      const path = `${dir}/${name}`;
      if (SKIP.has(name) || SKIP.has(path)) return [];
      return statSync(join(root, path)).isDirectory() ? walk(root, path) : [path];
    });
}

/** Every line of a text file under `dirs` (relative to `root`) that matches SENSITIVE. */
export function scanFiles(
  root = REPO_ROOT,
  dirs = ["plugins", "packages", "ontology"],
): { files: number; binary: number; findings: Finding[] } {
  const findings: Finding[] = [];
  let files = 0;
  let binary = 0;
  for (const file of dirs.flatMap((dir) => walk(root, dir))) {
    const data = readFileSync(join(root, file));
    if (data.includes(0)) {
      binary++;
      continue;
    }
    files++;
    for (const [index, text] of data.toString("utf8").split("\n").entries()) {
      for (const [pattern, why] of SENSITIVE) {
        if (pattern.test(text)) findings.push({ file, line: index + 1, why });
      }
    }
  }
  return { files, binary, findings };
}

type Kind = "command" | "url" | "image" | "env";

// Heuristics for what an agent could act on. A command is a code span that
// starts with a lowercase word and goes on (`runpodctl pod list`, not
// `workers.max`); an image has a namespace and a tag or digest.
const INSTRUCTIONS: [Kind, RegExp][] = [
  ["command", /`((?:\$\s+)?[a-z][\w.-]*\s+[^`]+)`/g],
  ["url", TEXT_URL],
  ["image", /(?<![\w./:@-])([a-z0-9][\w.-]*(?:\/[\w.-]+)+(?::\w[\w.-]*|@sha256:[0-9a-f]{64}))/g],
  ["env", /\b([A-Z][A-Z0-9_]+=[^\s`]*)/g],
];
const RUNPOD_IMAGE = /^(docker\.io\/)?runpod\//;

export interface Addition {
  rule: string;
  kind: Kind;
  text: string;
}

/** Rule id to the text an agent reads, its statement and on_violation, for every concept file in `dir`. */
export function ruleTexts(dir = CONCEPTS_DIR): Map<string, string> {
  type Raw = { rules?: { id: string; statement?: string; on_violation?: string | number }[] } | null;
  const texts = new Map<string, string>();
  for (const file of readdirSync(dir).filter((name) => name.endsWith(".yaml"))) {
    const concept = parse(readFileSync(join(dir, file), "utf8")) as Raw;
    for (const rule of concept?.rules ?? []) texts.set(rule.id, `${rule.statement ?? ""}\n${rule.on_violation ?? ""}`);
  }
  return texts;
}

const instructions = (text: string) =>
  INSTRUCTIONS.flatMap(([kind, pattern]) => [...text.matchAll(pattern)].map((match) => ({ kind, text: match[1]! })));

/** What each rule in `head` says that the same rule in `base` does not, and which additions fail. */
export function compareRules(base: Map<string, string>, head: Map<string, string>) {
  const added: Addition[] = [];
  for (const [rule, text] of head) {
    const before = new Set(instructions(base.get(rule) ?? "").map((item) => `${item.kind} ${item.text}`));
    const seen = new Set<string>();
    for (const item of instructions(text)) {
      const key = `${item.kind} ${item.text}`;
      if (!before.has(key) && !seen.has(key)) added.push({ rule, ...item });
      seen.add(key);
    }
  }
  const errors = added
    .filter((item) => item.kind === "image" && !RUNPOD_IMAGE.test(item.text))
    .map((item) => `rule ${item.rule} adds image ${item.text}, which is not under runpod/`);
  return { added, errors };
}

function summary(added: Addition[]): string {
  const title = "### Concept rules: added commands, URLs, images and environment variables";
  if (!added.length) return `${title}\n\nNone.\n`;
  return [title, "", ...added.map((item) => `- \`${item.rule}\` ${item.kind}: \`${item.text}\``), ""].join("\n");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: { base: { type: "string" } } });
  const { files, binary, findings } = scanFiles();
  const errors = findings.map((finding) => `${finding.file}:${finding.line} mentions ${finding.why}`);
  if (values.base) {
    const { added, errors: ruleErrors } = compareRules(ruleTexts(values.base), ruleTexts());
    if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary(added));
    else console.log(summary(added));
    errors.push(...ruleErrors);
  }
  for (const error of errors) console.log(`error ${error}`);
  console.log(`${files} files scanned, ${binary} binary skipped, ${errors.length} errors`);
  process.exit(errors.length ? 1 : 0);
}
