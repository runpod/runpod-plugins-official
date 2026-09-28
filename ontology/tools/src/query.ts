// Read side: the queries an agent tool would run against the built SQLite
// file. Every rule in the ontology is public-facing, so nothing is filtered.

import { DatabaseSync } from "node:sqlite";

export interface RuleRecord {
  id: string;
  concept_id: string;
  statement: string;
  on_violation: string | null;
  status: string;
  conflict: boolean;
  applies_to: string[];
  see: string[];
  evidence: { source: string; ref: string | null; url: string | null; path: string | null; seen: string | null; note: string | null }[];
}

export interface ConceptRecord {
  id: string;
  name: string;
  kind: string;
  summary: string;
  product: string | null;
  is_a: string | null;
  part_of: string | null;
  aliases: string[];
  surfaces: Record<string, string[]>;
  fields: Record<string, unknown>[];
  states: { field: string; value: string; description: string }[];
  transitions: { action: string; from_state: string; to_state: string }[];
  /** For a process: its steps in order, with the concepts and rules each involves. */
  steps: { step_id: string; title: string; description: string; concepts: string[]; rules: string[] }[];
  edges_out: { type: string; target_id: string }[];
  edges_in: { type: string; source_id: string }[];
  rules: RuleRecord[];
  /** Rules on other concepts that this concept's rules point at with see:. */
  linked_rules: RuleRecord[];
  /** Skills, reference docs and golden paths linked to the concept. */
  guides: GuideRef[];
  /** Set when the reference matched more than one concept. */
  ambiguous?: string[];
}

export interface GuideRef {
  id: string;
  kind: "skill" | "reference" | "golden-path";
  title: string;
  mcp: "full" | "partial" | "none" | null;
  /** uses (a golden path works with the concept) or explains (a doc explains it). */
  type: "uses" | "explains";
}

export interface TreeNode {
  id: string;
  name: string;
  kind: string;
  /** How the node hangs off its parent: a kind of it (is_a) or a part of it (part_of). */
  relation: "is_a" | "part_of" | null;
  guides: GuideRef[];
  children: TreeNode[];
}

export interface SearchHit {
  rule: RuleRecord;
  concept_name: string;
  rank: number;
}

type Row = Record<string, unknown>;

// node:sqlite rows have a null prototype; spread them into plain objects.
const plain = (rows: unknown[]) => (rows as Row[]).map((row) => ({ ...row }));

export function openOntology(path: string): DatabaseSync {
  return new DatabaseSync(path, { readOnly: true });
}

/** Concept ids a name, id or alias refers to, in id order. */
export function resolve(db: DatabaseSync, reference: string): string[] {
  const rows = db
    .prepare("SELECT concept_id FROM names WHERE name = ? ORDER BY source = 'id' DESC, concept_id")
    .all(reference.trim().toLowerCase()) as Row[];
  return [...new Set(rows.map((row) => String(row.concept_id)))];
}

function loadRules(db: DatabaseSync, where: string, params: string[]): RuleRecord[] {
  const rows = db.prepare(`SELECT * FROM rules WHERE ${where} ORDER BY id`).all(...params) as Row[];
  return rows.map((row) => {
    const id = String(row.id);
    const targets = db.prepare("SELECT target_kind, target_name FROM rule_targets WHERE rule_id = ?").all(id) as Row[];
    const see = db.prepare("SELECT see_rule_id FROM rule_links WHERE rule_id = ?").all(id) as Row[];
    const evidence = plain(db.prepare("SELECT source, ref, url, path, seen, note FROM evidence WHERE rule_id = ? ORDER BY id").all(id));
    return {
      id,
      concept_id: String(row.concept_id),
      statement: String(row.statement),
      on_violation: (row.on_violation as string | null) ?? null,
      status: String(row.status),
      conflict: row.conflict === 1,
      applies_to: targets.map((t) => `${t.target_kind}:${t.target_name}`),
      see: see.map((s) => String(s.see_rule_id)),
      evidence: evidence as RuleRecord["evidence"],
    };
  });
}

/** The full record for one concept, by id, name or alias. */
export function getConcept(db: DatabaseSync, reference: string): ConceptRecord | undefined {
  const ids = resolve(db, reference);
  const id = ids[0];
  if (!id) return undefined;

  const concept = db.prepare("SELECT * FROM concepts WHERE id = ?").get(id) as Row;
  const all = (sql: string) => plain(db.prepare(sql).all(id));

  const surfaces: Record<string, string[]> = {};
  for (const row of all("SELECT surface, item, value FROM surfaces WHERE concept_id = ? ORDER BY surface, item, value")) {
    (surfaces[`${row.surface}.${row.item}`] ??= []).push(String(row.value));
  }

  const rules = loadRules(db, "concept_id = ?", [id]);
  const linkedIds = [...new Set(rules.flatMap((rule) => rule.see))].filter((see) => !see.startsWith(`${id}.`));
  const linked_rules = linkedIds.length ? loadRules(db, `id IN (${linkedIds.map(() => "?").join(",")})`, linkedIds) : [];

  return {
    id,
    name: String(concept.name),
    kind: String(concept.kind),
    summary: String(concept.summary),
    product: (concept.product as string | null) ?? null,
    is_a: (concept.is_a as string | null) ?? null,
    part_of: (concept.part_of as string | null) ?? null,
    aliases: all("SELECT name FROM names WHERE concept_id = ? AND source = 'alias' ORDER BY name").map((r) => String(r.name)),
    surfaces,
    fields: all("SELECT name, type, set_on, required, ref, unit, default_value, enum_values, note FROM fields WHERE concept_id = ? ORDER BY rowid").map(
      (row) => ({ ...row, required: row.required === 1, enum_values: row.enum_values ? JSON.parse(String(row.enum_values)) : null }),
    ),
    states: all("SELECT field, value, description FROM states WHERE concept_id = ? ORDER BY rowid") as ConceptRecord["states"],
    transitions: all("SELECT action, from_state, to_state FROM transitions WHERE concept_id = ? ORDER BY rowid") as ConceptRecord["transitions"],
    steps: all("SELECT step_id, title, description FROM process_steps WHERE concept_id = ? ORDER BY position").map((row) => ({
      step_id: String(row.step_id),
      title: String(row.title),
      description: String(row.description),
      concepts: (db.prepare("SELECT target_id FROM step_concepts WHERE concept_id = ? AND step_id = ? ORDER BY rowid").all(id, String(row.step_id)) as Row[]).map((r) => String(r.target_id)),
      rules: (db.prepare("SELECT rule_id FROM step_rules WHERE concept_id = ? AND step_id = ? ORDER BY rowid").all(id, String(row.step_id)) as Row[]).map((r) => String(r.rule_id)),
    })),
    edges_out: all("SELECT type, target_id FROM edges WHERE source_id = ? ORDER BY type, target_id") as ConceptRecord["edges_out"],
    edges_in: all("SELECT type, source_id FROM edges WHERE target_id = ? ORDER BY type, source_id") as ConceptRecord["edges_in"],
    rules,
    linked_rules,
    guides: guidesFor(db, id),
    ...(ids.length > 1 ? { ambiguous: ids } : {}),
  };
}

/** Rules ranked against free text (FTS5 bm25 over statements and concept names). */
export function search(db: DatabaseSync, query: string, options: { limit?: number } = {}): SearchHit[] {
  const words = query.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  if (!words.length) return [];
  const match = words.map((word) => `"${word}"`).join(" OR ");
  const rows = db
    .prepare(
      `SELECT f.rule_id, c.name AS concept_name, bm25(rules_fts, 0, 0, 1.0, 0.5) AS rank
         FROM rules_fts f
         JOIN rules r ON r.id = f.rule_id
         JOIN concepts c ON c.id = r.concept_id
        WHERE rules_fts MATCH ?
        ORDER BY rank
        LIMIT ?`,
    )
    .all(match, options.limit ?? 10) as Row[];
  return rows.map((row) => ({
    rule: loadRules(db, "id = ?", [String(row.rule_id)])[0]!,
    concept_name: String(row.concept_name),
    rank: Number(row.rank),
  }));
}

/** Concepts one edge away, in either direction. */
export function neighbors(db: DatabaseSync, id: string): { direction: "out" | "in"; type: string; concept_id: string }[] {
  const out = db.prepare("SELECT type, target_id AS concept_id FROM edges WHERE source_id = ?").all(id) as Row[];
  const into = db.prepare("SELECT type, source_id AS concept_id FROM edges WHERE target_id = ?").all(id) as Row[];
  return [
    ...out.map((row) => ({ direction: "out" as const, type: String(row.type), concept_id: String(row.concept_id) })),
    ...into.map((row) => ({ direction: "in" as const, type: String(row.type), concept_id: String(row.concept_id) })),
  ];
}

/** Guides linked to a concept: golden paths first, then skills, then reference docs. */
export function guidesFor(db: DatabaseSync, conceptId: string): GuideRef[] {
  const rows = db
    .prepare(
      `SELECT g.id, g.kind, g.title, g.mcp, min(l.type) AS type FROM guide_links l JOIN guides g ON g.id = l.guide_id
       WHERE l.concept_id = ? GROUP BY g.id
       ORDER BY CASE g.kind WHEN 'golden-path' THEN 0 WHEN 'skill' THEN 1 ELSE 2 END, g.id`,
    )
    .all(conceptId) as Row[];
  return rows.map((row) => ({
    id: String(row.id),
    kind: row.kind as GuideRef["kind"],
    title: String(row.title),
    mcp: (row.mcp ?? null) as GuideRef["mcp"],
    type: row.type as GuideRef["type"],
  }));
}

/**
 * The concept hierarchy as a tree. A concept hangs under its is_a parent when it
 * has one, otherwise under its part_of parent. Without a root, returns every
 * top-level concept (normally just the platform).
 */
export function tree(db: DatabaseSync, rootId?: string): TreeNode[] {
  const rows = db.prepare("SELECT id, name, kind, is_a, part_of FROM concepts ORDER BY name").all() as Row[];
  const children = new Map<string, Row[]>();
  for (const row of rows) {
    const parent = (row.is_a ?? row.part_of) as string | null;
    if (parent) children.set(parent, [...(children.get(parent) ?? []), row]);
  }
  const build = (row: Row): TreeNode => ({
    id: String(row.id),
    name: String(row.name),
    kind: String(row.kind),
    relation: row.is_a ? "is_a" : row.part_of ? "part_of" : null,
    guides: guidesFor(db, String(row.id)),
    children: (children.get(String(row.id)) ?? []).map(build),
  });
  const roots = rootId ? rows.filter((row) => row.id === rootId) : rows.filter((row) => !row.is_a && !row.part_of);
  return roots.map(build);
}
