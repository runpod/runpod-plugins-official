// Formats the concept files in one canonical style, so every file reads the
// same and diffs show only real changes. The data never changes: each output
// is parsed again and compared with the input before it is written.
//
//   node src/format.ts           rewrite files that are not canonical
//   node src/format.ts --check   list them and exit 1 (CI)
//
// The style: top-level keys in schema order with a blank line between
// sections; summaries, statements and step descriptions as folded blocks
// wrapped at 80 columns; lists of names as [a, b]; fields, relations,
// transitions and evidence as one-line { key: value } entries; a blank line
// between rules and between steps.

import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { isDeepStrictEqual } from "node:util";
import { parse, stringify } from "yaml";
import { CONCEPTS_DIR } from "./load.ts";

const WIDTH = 80;
const HEADER = ["id", "name", "kind", "summary", "product", "is_a", "part_of", "aliases"];
const SECTIONS = ["surfaces", "fields", "states", "relations", "steps", "rules"];
const RULE_KEYS = ["id", "applies_to", "statement", "on_violation", "status", "conflict", "see", "evidence"];
const STEP_KEYS = ["id", "title", "description", "concepts", "rules"];
const STATE_KEYS = ["field", "values", "transitions", "on_invalid_action", "evidence"];
const FOLDED = new Set(["summary", "statement", "description"]);

type Value = null | boolean | number | string | Value[] | { [key: string]: Value };
const isObject = (v: Value): v is { [key: string]: Value } => typeof v === "object" && v !== null && !Array.isArray(v);

/** Keys in the preferred order first, then any others in their original order. */
const ordered = (object: Record<string, unknown>, preferred: string[]) => [
  ...preferred.filter((key) => key in object),
  ...Object.keys(object).filter((key) => !preferred.includes(key)),
];

// Words YAML 1.1 parsers (PyYAML, used by yamllint and other Python tools) read as booleans or null.
const RESERVED = /^(y|n|yes|no|on|off|true|false|null|~)$/i;
// A string that every YAML parser reads as the same plain string inside [ ] or { }.
const SAFE_PLAIN = /^[A-Za-z_/][A-Za-z0-9 _./()+=<>-]*$/;

/**
 * A scalar as it must be written inside [ ] or { }. Anything beyond plain words,
 * paths and simple punctuation is double-quoted, so Python YAML parsers read the
 * file the same way the Node one does (a `?`, `:`, `#`, quote or backtick in a
 * plain flow scalar is valid YAML 1.2 but trips PyYAML).
 */
function flowScalar(value: Value): string {
  if (typeof value !== "string") return stringify(value, { lineWidth: 0 }).trim();
  const plain = SAFE_PLAIN.test(value) && !RESERVED.test(value) && !value.endsWith(" ") && !/^[-.]?\d/.test(value);
  return plain ? value : JSON.stringify(value);
}

/** A value on one line: [a, b] for lists, { key: value } for maps. */
function flow(value: Value): string {
  if (Array.isArray(value)) return `[${value.map(flow).join(", ")}]`;
  if (isObject(value))
    return `{ ${Object.entries(value)
      .map(([k, v]) => `${flowScalar(k)}: ${flow(v)}`)
      .join(", ")} }`;
  return flowScalar(value);
}

/** A scalar in block context, on one line. */
function scalar(value: Value): string {
  if (value === null) return "null";
  const text = stringify(value, { lineWidth: 0 }).trimEnd();
  if (text.includes("\n")) throw new Error(`cannot write ${JSON.stringify(value)} on one line`);
  return text;
}

/** A folded block (>) wrapped at WIDTH columns. Paragraphs stay separated by a blank line. */
function folded(key: string, text: string, indent: number): string[] {
  const pad = " ".repeat(indent + 2);
  const lines = [`${" ".repeat(indent)}${key}: >`];
  const paragraphs = text.trimEnd().split(/\n\s*\n|\n/);
  paragraphs.forEach((paragraph, index) => {
    if (index > 0) lines.push("");
    let line = "";
    for (const word of paragraph.trim().split(/ +/)) {
      if (line && pad.length + line.length + 1 + word.length > WIDTH) {
        lines.push(pad + line);
        line = word;
      } else line = line ? `${line} ${word}` : word;
    }
    if (line) lines.push(pad + line);
  });
  return lines;
}

/** One key: value line, a folded block, or a block of one-line list items. */
function entry(key: string, value: Value, indent: number): string[] {
  const pad = " ".repeat(indent);
  if (FOLDED.has(key) && typeof value === "string") return folded(key, value, indent);
  if (Array.isArray(value) && value.some(isObject))
    return [`${pad}${key}:`, ...value.map((item) => `${pad}  - ${flow(item)}`)];
  if (Array.isArray(value) || isObject(value)) return [`${pad}${key}: ${flow(value)}`];
  return [`${pad}${key}: ${scalar(value)}`];
}

/** A list of block maps (rules, steps), with a blank line between items. */
function blockList(items: Value[], keys: string[], indent: number): string[] {
  const lines: string[] = [];
  items.forEach((item, index) => {
    if (!isObject(item)) throw new Error("expected a map in a block list");
    if (index > 0) lines.push("");
    ordered(item, keys).forEach((key, position) => {
      const [first, ...rest] = entry(key, item[key]!, indent + 2);
      lines.push(position === 0 ? `${" ".repeat(indent)}- ${first!.trimStart()}` : first!, ...rest);
    });
  });
  return lines;
}

function section(key: string, value: Value): string[] {
  if (key === "rules" || key === "steps") {
    return [`${key}:`, ...blockList(value as Value[], key === "rules" ? RULE_KEYS : STEP_KEYS, 2)];
  }
  if (key === "states" && isObject(value)) {
    const lines = ["states:"];
    for (const k of ordered(value, STATE_KEYS)) {
      const v = value[k]!;
      if (k === "values" && isObject(v))
        lines.push("  values:", ...Object.entries(v).map(([s, d]) => `    ${scalar(s)}: ${scalar(d)}`));
      else lines.push(...entry(k, v, 2));
    }
    return lines;
  }
  if (key === "surfaces" && isObject(value))
    return ["surfaces:", ...Object.entries(value).flatMap(([k, v]) => entry(k, v, 2))];
  return entry(key, value, 0);
}

/** Trailing whitespace on text is not data: a one-line statement and a folded one ending in a newline are the same. */
function normalize(value: Value): Value {
  if (Array.isArray(value)) return value.map(normalize);
  if (isObject(value)) return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, normalize(v)]));
  return typeof value === "string" ? value.trimEnd() : value;
}

/** The canonical text of one concept file. Throws if the data would change. */
export function formatConcept(text: string): string {
  const data = parse(text) as { [key: string]: Value };
  const header = ordered(data, HEADER).filter((key) => !SECTIONS.includes(key));
  const lines = header.flatMap((key) => entry(key, data[key]!, 0));
  for (const key of SECTIONS) if (key in data) lines.push("", ...section(key, data[key]!));
  const out = `${lines.join("\n")}\n`;
  if (!isDeepStrictEqual(normalize(parse(out)), normalize(data))) throw new Error("formatting would change the data");
  return out;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const check = process.argv.includes("--check");
  const changed: string[] = [];
  for (const file of readdirSync(CONCEPTS_DIR)
    .filter((f) => f.endsWith(".yaml"))
    .sort()) {
    const path = join(CONCEPTS_DIR, file);
    const before = readFileSync(path, "utf8");
    let after: string;
    try {
      after = formatConcept(before);
    } catch (error) {
      console.error(`error ${file}: ${(error as Error).message}`);
      process.exitCode = 1;
      continue;
    }
    if (after === before) continue;
    changed.push(file);
    if (!check) writeFileSync(path, after);
  }
  if (check && changed.length) {
    for (const file of changed) console.log(`not formatted: ${file}`);
    console.log(`${changed.length} concept files need formatting; run pnpm format`);
    process.exitCode = 1;
  } else console.log(check ? "concept files are formatted" : `formatted ${changed.length} concept files`);
}
