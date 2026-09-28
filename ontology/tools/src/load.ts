// Reads the concept files (plugins/runpod/skills/runpod-usage/concepts/*.yaml) and checks each file against the Zod schema.

import { readdirSync, readFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { Concept } from "./schema.ts";

export const ONTOLOGY_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
export const REPO_ROOT = resolve(ONTOLOGY_DIR, "..");
// The concepts ship inside the runpod-usage skill so installed plugins can read them.
export const CONCEPTS_DIR = join(REPO_ROOT, "plugins/runpod/skills/runpod-usage/concepts");
// The same REST v2 snapshot the runpod-migrate checks use; spec-drift refreshes it.
export const SPEC_PATH = join(REPO_ROOT, "testdata/runpod-migrate/v2-openapi.json");

export interface Loaded {
  concepts: Concept[];
  /** "<file>: <message>" for every file that failed to parse or match the schema. */
  errors: string[];
}

export function loadConcepts(dir = CONCEPTS_DIR): Loaded {
  const concepts: Concept[] = [];
  const errors: string[] = [];
  const files = readdirSync(dir)
    .filter((file) => file.endsWith(".yaml"))
    .sort();

  for (const file of files) {
    let raw: unknown;
    try {
      raw = parse(readFileSync(join(dir, file), "utf8"));
    } catch (error) {
      errors.push(`${file}: YAML does not parse: ${(error as Error).message.split("\n")[0]}`);
      continue;
    }
    const result = Concept.safeParse(raw);
    if (!result.success) {
      for (const issue of result.error.issues) {
        errors.push(`${file}: ${issue.path.join(".") || "(root)"}: ${issue.message}`);
      }
      continue;
    }
    if (result.data.id !== basename(file, ".yaml")) {
      errors.push(`${file}: id "${result.data.id}" does not match the file name`);
    }
    concepts.push(result.data);
  }
  return { concepts, errors };
}
