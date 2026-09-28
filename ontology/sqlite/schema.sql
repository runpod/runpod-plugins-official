-- SQLite schema for the concept ontology. tools/src/build-sqlite.ts fills it
-- from concepts/*.yaml. Plain tables plus one full-text index, so the same
-- shape maps to Postgres, Convex or a graph database.
--
-- The graph: `concepts` are the nodes, and the `edges` view is every link
-- between them (is_a, part_of, typed relations, field references).

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE concepts (
  id         TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  kind       TEXT NOT NULL,
  summary    TEXT NOT NULL,
  product    TEXT,
  is_a       TEXT REFERENCES concepts(id),
  part_of    TEXT REFERENCES concepts(id)
);

-- Every name a concept can be looked up by: its id, name and aliases, lower-cased.
-- One name can point at several concepts; the lookup returns all of them.
CREATE TABLE names (
  name       TEXT NOT NULL,
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  source     TEXT NOT NULL CHECK (source IN ('id', 'name', 'alias')),
  PRIMARY KEY (name, concept_id)
);

-- Where a concept appears on each surface. `item` is the kind of entry
-- (schema, path, type, query, mutation, tool, command, page).
CREATE TABLE surfaces (
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  surface    TEXT NOT NULL CHECK (surface IN ('rest_v2', 'graphql', 'mcp', 'runpodctl', 'console')),
  item       TEXT NOT NULL,
  value      TEXT NOT NULL,
  PRIMARY KEY (concept_id, surface, item, value)
);

CREATE TABLE fields (
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  name       TEXT NOT NULL,
  type       TEXT NOT NULL,
  set_on     TEXT NOT NULL CHECK (set_on IN ('create', 'update', 'create,update', 'read')),
  required   INTEGER NOT NULL DEFAULT 0,
  ref        TEXT REFERENCES concepts(id),
  unit       TEXT,
  default_value TEXT,
  enum_values TEXT, -- JSON array
  note       TEXT,
  PRIMARY KEY (concept_id, name)
);

CREATE TABLE states (
  concept_id  TEXT NOT NULL REFERENCES concepts(id),
  field       TEXT NOT NULL,
  value       TEXT NOT NULL,
  description TEXT NOT NULL,
  PRIMARY KEY (concept_id, value)
);

CREATE TABLE transitions (
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  action     TEXT NOT NULL,
  from_state TEXT NOT NULL,
  to_state   TEXT NOT NULL,
  PRIMARY KEY (concept_id, action, from_state)
);

-- The ordered steps of a process concept, and what each step involves.
CREATE TABLE process_steps (
  concept_id  TEXT NOT NULL REFERENCES concepts(id),
  position    INTEGER NOT NULL,
  step_id     TEXT NOT NULL,
  title       TEXT NOT NULL,
  description TEXT NOT NULL,
  PRIMARY KEY (concept_id, step_id),
  UNIQUE (concept_id, position)
);

CREATE TABLE step_concepts (
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  step_id    TEXT NOT NULL,
  target_id  TEXT NOT NULL REFERENCES concepts(id),
  PRIMARY KEY (concept_id, step_id, target_id),
  FOREIGN KEY (concept_id, step_id) REFERENCES process_steps(concept_id, step_id)
);

-- Rules are inserted after steps, so this table has no foreign key to rules;
-- the validator guarantees every rule_id exists.
CREATE TABLE step_rules (
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  step_id    TEXT NOT NULL,
  rule_id    TEXT NOT NULL,
  PRIMARY KEY (concept_id, step_id, rule_id),
  FOREIGN KEY (concept_id, step_id) REFERENCES process_steps(concept_id, step_id)
);

CREATE TABLE relations (
  source_id   TEXT NOT NULL REFERENCES concepts(id),
  type        TEXT NOT NULL,
  target_id   TEXT NOT NULL REFERENCES concepts(id),
  cardinality TEXT,
  PRIMARY KEY (source_id, type, target_id)
);

CREATE TABLE rules (
  id           TEXT PRIMARY KEY,
  concept_id   TEXT NOT NULL REFERENCES concepts(id),
  statement    TEXT NOT NULL,
  on_violation TEXT,
  status       TEXT NOT NULL CHECK (status IN ('verified', 'documented')),
  conflict     INTEGER NOT NULL DEFAULT 0
);

-- What a rule constrains: target_kind 'field', 'state' or 'action' plus the
-- name. A rule with no rows here applies to the concept as a whole.
CREATE TABLE rule_targets (
  rule_id     TEXT NOT NULL REFERENCES rules(id),
  target_kind TEXT NOT NULL CHECK (target_kind IN ('field', 'state', 'action')),
  target_name TEXT NOT NULL,
  PRIMARY KEY (rule_id, target_kind, target_name)
);

CREATE TABLE rule_links (
  rule_id     TEXT NOT NULL REFERENCES rules(id),
  see_rule_id TEXT NOT NULL REFERENCES rules(id),
  PRIMARY KEY (rule_id, see_rule_id)
);

-- Evidence for a rule, or for a concept's state machine when rule_id is null.
CREATE TABLE evidence (
  id         INTEGER PRIMARY KEY,
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  rule_id    TEXT REFERENCES rules(id),
  source     TEXT NOT NULL CHECK (source IN ('rest-v2-spec', 'public-docs', 'skill', 'live-probe', 'other')),
  ref        TEXT,
  url        TEXT,
  path       TEXT,
  seen       TEXT,
  note       TEXT
);

CREATE INDEX idx_rules_concept ON rules(concept_id);
CREATE INDEX idx_relations_target ON relations(target_id);
CREATE INDEX idx_evidence_rule ON evidence(rule_id);

-- Every link between two concepts, whatever declared it. A process links to
-- each concept its steps involve.
-- The plugin's skills, reference docs and golden paths, and their links to concepts.
-- mcp says whether an agent with only the Runpod MCP tools can finish a golden path.
CREATE TABLE guides (
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL CHECK (kind IN ('skill', 'reference', 'golden-path')),
  title       TEXT NOT NULL,
  description TEXT NOT NULL,
  path        TEXT NOT NULL,
  mcp         TEXT CHECK (mcp IN ('full', 'partial', 'none')),
  needs_shell INTEGER NOT NULL,
  parent      TEXT,           -- the skill or golden path this guide belongs to
  body        TEXT NOT NULL
);

CREATE TABLE guide_lanes (
  guide_id TEXT NOT NULL REFERENCES guides(id),
  lane     TEXT NOT NULL,
  PRIMARY KEY (guide_id, lane)
);

-- uses: a golden path works with the concept. explains: a doc explains it.
-- via says where the link comes from: the guide's frontmatter, a golden path's lane
-- (runpodctl, flash), or rule evidence.
CREATE TABLE guide_links (
  guide_id   TEXT NOT NULL REFERENCES guides(id),
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  type       TEXT NOT NULL CHECK (type IN ('uses', 'explains')),
  via        TEXT NOT NULL CHECK (via IN ('frontmatter', 'lane', 'evidence')),
  PRIMARY KEY (guide_id, concept_id, via)
);

CREATE VIEW edges AS
  SELECT id AS source_id, 'is_a' AS type, is_a AS target_id FROM concepts WHERE is_a IS NOT NULL
  UNION ALL
  SELECT id, 'part_of', part_of FROM concepts WHERE part_of IS NOT NULL
  UNION ALL
  SELECT source_id, type, target_id FROM relations
  UNION ALL
  SELECT DISTINCT concept_id, 'field_ref', ref FROM fields WHERE ref IS NOT NULL
  UNION ALL
  SELECT DISTINCT concept_id, 'involves', target_id FROM step_concepts;

-- Full-text search over rules, with the concept's name and aliases folded in
-- so "volume" finds network-volume rules that never say "volume".
CREATE VIRTUAL TABLE rules_fts USING fts5(
  rule_id UNINDEXED,
  concept_id UNINDEXED,
  statement,
  concept_names,
  tokenize = 'porter unicode61'
);
