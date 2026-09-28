// Validates concepts/*.yaml and writes them into a fresh SQLite file using
// sqlite/schema.sql. Refuses to build when validation has errors.
//
//   node src/build-sqlite.ts [out.sqlite]     default: ../build/ontology.sqlite

import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import { ONTOLOGY_DIR, REPO_ROOT, SPEC_PATH } from "./load.ts";
import { collectGuides, type Guide, type Link } from "./build-bundle.ts";
import type { Concept } from "./schema.ts";
import { validate } from "./validate.ts";

export const DEFAULT_DB_PATH = join(ONTOLOGY_DIR, "build/ontology.sqlite");
const SCHEMA_PATH = join(ONTOLOGY_DIR, "sqlite/schema.sql");

function gitCommit(): string {
  try {
    return execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: REPO_ROOT, encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}

const text = (value: unknown) => (value === undefined || value === null ? null : String(value));

export function buildDatabase(concepts: Concept[], path: string, guides: Guide[] = [], guideLinks: Link[] = []): DatabaseSync {
  rmSync(path, { force: true });
  mkdirSync(dirname(path), { recursive: true });
  const db = new DatabaseSync(path);
  db.exec(readFileSync(SCHEMA_PATH, "utf8"));
  db.exec("PRAGMA foreign_keys = ON");

  const insert = (sql: string) => db.prepare(sql);
  const concept = insert("INSERT INTO concepts VALUES (?, ?, ?, ?, ?, ?, ?)");
  const name = insert("INSERT OR IGNORE INTO names VALUES (?, ?, ?)");
  const surface = insert("INSERT OR IGNORE INTO surfaces VALUES (?, ?, ?, ?)");
  const field = insert("INSERT INTO fields VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");
  const state = insert("INSERT INTO states VALUES (?, ?, ?, ?)");
  const transition = insert("INSERT INTO transitions VALUES (?, ?, ?, ?)");
  const relation = insert("INSERT INTO relations VALUES (?, ?, ?, ?)");
  const step = insert("INSERT INTO process_steps VALUES (?, ?, ?, ?, ?)");
  const stepConcept = insert("INSERT INTO step_concepts VALUES (?, ?, ?)");
  const stepRule = insert("INSERT INTO step_rules VALUES (?, ?, ?)");
  const rule = insert("INSERT INTO rules VALUES (?, ?, ?, ?, ?, ?)");
  const target = insert("INSERT INTO rule_targets VALUES (?, ?, ?)");
  const link = insert("INSERT INTO rule_links VALUES (?, ?)");
  const evidence = insert("INSERT INTO evidence (concept_id, rule_id, source, ref, url, path, seen, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)");
  const fts = insert("INSERT INTO rules_fts VALUES (?, ?, ?, ?)");

  db.exec("BEGIN");
  // Concepts first so every foreign key below has a row to point at.
  for (const c of concepts) {
    concept.run(c.id, c.name, c.kind, c.summary.trim(), c.product, null, null);
  }
  const setParents = insert("UPDATE concepts SET is_a = ?, part_of = ? WHERE id = ?");
  for (const c of concepts) {
    setParents.run(c.is_a, c.part_of, c.id);

    name.run(c.id.toLowerCase(), c.id, "id");
    name.run(c.name.toLowerCase(), c.id, "name");
    for (const alias of c.aliases) name.run(alias.toLowerCase(), c.id, "alias");

    const s = c.surfaces;
    if (s.rest_v2?.schema) surface.run(c.id, "rest_v2", "schema", s.rest_v2.schema);
    for (const p of s.rest_v2?.paths ?? []) surface.run(c.id, "rest_v2", "path", p);
    if (s.graphql?.type) surface.run(c.id, "graphql", "type", s.graphql.type);
    for (const q of s.graphql?.queries ?? []) surface.run(c.id, "graphql", "query", q);
    for (const m of s.graphql?.mutations ?? []) surface.run(c.id, "graphql", "mutation", m);
    for (const tool of s.mcp) surface.run(c.id, "mcp", "tool", tool);
    for (const command of s.runpodctl) surface.run(c.id, "runpodctl", "command", command);
    if (s.console) surface.run(c.id, "console", "page", s.console);

    for (const f of c.fields) {
      field.run(
        c.id, f.name, f.type, f.set, f.required ? 1 : 0, text(f.ref), text(f.unit), text(f.default),
        f.values ? JSON.stringify(f.values) : null, text(f.note),
      );
    }

    if (c.states) {
      for (const [value, description] of Object.entries(c.states.values)) state.run(c.id, c.states.field, value, description);
      for (const t of c.states.transitions) for (const from of t.from) transition.run(c.id, t.action, from, t.to);
      for (const e of c.states.evidence) evidence.run(c.id, null, e.source, text(e.ref), text(e.url), text(e.path), text(e.seen), text(e.note));
    }

    for (const r of c.relations) relation.run(c.id, r.type, r.target, text(r.cardinality));

    c.steps.forEach((s, position) => {
      step.run(c.id, position + 1, s.id, s.title, s.description.trim());
      for (const target of s.concepts) stepConcept.run(c.id, s.id, target);
      for (const ruleId of s.rules) stepRule.run(c.id, s.id, ruleId);
    });

    const conceptNames = [c.name, ...c.aliases].join(" ");
    for (const r of c.rules) {
      rule.run(r.id, c.id, r.statement.trim(), text(r.on_violation), r.status, r.conflict ? 1 : 0);
      for (const t of r.applies_to) {
        const split = t.indexOf(":");
        target.run(r.id, t.slice(0, split), t.slice(split + 1));
      }
      for (const e of r.evidence) evidence.run(c.id, r.id, e.source, text(e.ref), text(e.url), text(e.path), text(e.seen), text(e.note));
      fts.run(r.id, c.id, r.statement.trim(), conceptNames);
    }
  }
  // Links last: a rule may point at a rule defined in a later file.
  for (const c of concepts) for (const r of c.rules) for (const see of r.see) link.run(r.id, see);

  const guide = insert("INSERT INTO guides VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)");
  const lane = insert("INSERT INTO guide_lanes VALUES (?, ?)");
  const guideLink = insert("INSERT OR IGNORE INTO guide_links VALUES (?, ?, ?, ?)");
  for (const g of guides) {
    guide.run(g.id, g.kind, g.title, g.description, g.path, g.mcp, g.needs_shell ? 1 : 0, g.parent, g.body);
    for (const name of g.lanes) lane.run(g.id, name);
  }
  for (const l of guideLinks) guideLink.run(l.from, l.to, l.type, l.via);

  const meta = insert("INSERT INTO meta VALUES (?, ?)");
  const spec = JSON.parse(readFileSync(SPEC_PATH, "utf8")) as { info: { version: string } };
  meta.run("built_at", new Date().toISOString());
  meta.run("git_commit", gitCommit());
  meta.run("rest_v2_spec_version", spec.info.version);
  meta.run("concepts", String(concepts.length));
  meta.run("rules", String(concepts.reduce((total, c) => total + c.rules.length, 0)));
  meta.run("guides", String(guides.length));
  db.exec("COMMIT");
  return db;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const out = resolve(process.argv[2] ?? DEFAULT_DB_PATH);
  const { concepts, errors } = validate();
  const linked = errors.length ? { guides: [], links: [], errors: [] } : collectGuides(concepts);
  const all = [...errors, ...linked.errors];
  if (all.length) {
    for (const error of all) console.error(`error ${error}`);
    console.error(`not building: ${all.length} errors`);
    process.exit(1);
  }
  const db = buildDatabase(concepts, out, linked.guides, linked.links);
  const count = (table: string) => (db.prepare(`SELECT count(*) AS n FROM ${table}`).get() as { n: number }).n;
  const tables = ["concepts", "names", "surfaces", "fields", "states", "transitions", "process_steps", "relations", "rules", "evidence", "guides", "guide_links"];
  console.log(`wrote ${out}`);
  console.log(tables.map((table) => `${table} ${count(table)}`).join(", "));
  db.close();
}
