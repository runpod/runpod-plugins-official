import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { collectGuides } from "../src/build-bundle.ts";
import { graphData, renderGraph } from "../src/build-graph.ts";
import { buildDatabase } from "../src/build-sqlite.ts";
import { formatConcept } from "../src/format.ts";
import { getConcept, guidesFor, neighbors, resolve, search, tree } from "../src/query.ts";
import { route } from "../src/server.ts";
import { validate } from "../src/validate.ts";

const fixtures = fileURLToPath(new URL("fixtures/", import.meta.url));
const noFile = join(fixtures, "does-not-exist");
const badErrors = () => validate(join(fixtures, "bad"), noFile, noFile).errors;

const assertHasError = (errors: string[], fragment: string) =>
  assert.ok(
    errors.some((error) => error.includes(fragment)),
    `missing error containing: ${fragment}\n${errors.join("\n")}`,
  );

test("the good fixtures validate cleanly", () => {
  const report = validate(join(fixtures, "good"), noFile, noFile);
  assert.deepEqual(report.errors, []);
  assert.equal(report.concepts.length, 3);
});

test("the validator reports every broken reference", () => {
  const errors = badErrors();
  for (const fragment of [
    "wrong-name.yaml: kind: Invalid option",
    'broken: is_a "missing-parent" is not a concept',
    'broken: relation located_in "nowhere" is not a concept',
    "broken: rule broken.bad-target applies_to field:color",
    "broken: rule broken.bad-target applies_to state:GONE",
    "broken: rule broken.bad-target sees nothing.here",
    'broken: rule other.wrong-prefix must start with "broken."',
  ]) {
    assertHasError(errors, fragment);
  }
});

test("internal statuses and sources are rejected by the schema", () => {
  const errors = badErrors();
  assertHasError(errors, "internal-source.yaml: rules.0.status");
  assertHasError(errors, "internal-source.yaml: rules.0.evidence.0.source");
});

test("internal names and ids are rejected anywhere in a file", () => {
  const errors = badErrors();
  assertHasError(errors, "broken: rules[2].statement mentions internal infrastructure");
  assertHasError(errors, "broken: rules[2].statement mentions an internal service");
  assertHasError(errors, "broken: rules[2].evidence[0].ref mentions an internal source id");
});

test("time-bound wording is rejected", () => {
  assertHasError(badErrors(), 'broken: rules[3].statement is time-bound ("Resizing is currently');
});

test("skill evidence must point at a file in the repo", () => {
  assertHasError(
    badErrors(),
    "broken: rule broken.missing-skill-file cites skill file plugins/runpod/skills/nowhere/SKILL.md",
  );
});

test("evidence with no ref, url, path or note is rejected", () => {
  assertHasError(badErrors(), "evidence needs at least one of ref, url, path or note");
});

test("evidence needs the keys that locate its source", () => {
  const errors = badErrors();
  assertHasError(errors, "unlocatable-evidence.yaml: rules.0.evidence.0: skill evidence needs path");
  assertHasError(errors, "unlocatable-evidence.yaml: rules.0.evidence.1: public-docs evidence needs url");
  assertHasError(errors, "unlocatable-evidence.yaml: rules.0.evidence.2: other evidence needs a ref or url");
  assertHasError(errors, "unlocatable-evidence.yaml: rules.0.evidence.3: live-probe evidence needs ref and seen");
});

test("skill evidence on states must point at a file in the repo", () => {
  assertHasError(badErrors(), "states-missing-skill: states cites skill file plugins/runpod/skills/nowhere/states.md");
});

test("a url must be on a public source host", () => {
  const errors = badErrors();
  assertHasError(
    errors,
    "private-url: rules[0].evidence[0].url is on www.notion.so, which is not a public source host",
  );
  assertHasError(errors, "private-url: rules[0].evidence[1].url is on linear.app");
  assertHasError(errors, "private-url: rules[0].evidence[2].url is not https");
  assertHasError(errors, "private-url: rules[0].evidence[3].url is not a public Runpod GitHub repository");
  assert.ok(!errors.some((error) => error.includes("rules[0].evidence[4]")));
});

function fixtureDb() {
  const { concepts } = validate(join(fixtures, "good"), noFile, noFile);
  return buildDatabase(concepts, join(mkdtempSync(join(tmpdir(), "ontology-")), "test.sqlite"));
}

test("names resolve by id, name and alias, case-insensitively", () => {
  const db = fixtureDb();
  assert.deepEqual(resolve(db, "volume"), ["volume"]);
  assert.deepEqual(resolve(db, "Disk Store"), ["volume"]);
  assert.deepEqual(resolve(db, "DATACENTER"), ["site"]);
  assert.deepEqual(resolve(db, "unknown"), []);
});

test("getConcept assembles fields, edges, states and linked rules", () => {
  const db = fixtureDb();
  const volume = getConcept(db, "volume")!;
  assert.equal(volume.fields.length, 1);
  assert.deepEqual(
    volume.rules.map((rule) => rule.id),
    ["volume.backups", "volume.site-fixed"],
  );
  assert.deepEqual(volume.edges_out, [
    { type: "field_ref", target_id: "site" },
    { type: "located_in", target_id: "site" },
  ]);
  assert.deepEqual(
    volume.linked_rules.map((rule) => rule.id),
    ["site.capacity-hidden"],
  );

  const site = getConcept(db, "site")!;
  assert.deepEqual(site.transitions, [{ action: "close", from_state: "OPEN", to_state: "CLOSED" }]);
  assert.deepEqual(
    site.edges_in.map((edge) => `${edge.type}:${edge.source_id}`),
    ["field_ref:volume", "involves:volume-setup", "located_in:volume"],
  );
});

test("evidence carries refs, urls, paths and notes", () => {
  const db = fixtureDb();
  const rule = getConcept(db, "volume")!.rules.find((r) => r.id === "volume.site-fixed")!;
  assert.deepEqual(
    rule.evidence.map((e) => e.source),
    ["rest-v2-spec", "public-docs", "other"],
  );
  assert.equal(rule.evidence[1]?.url, "https://docs.runpod.io/storage/network-volumes");
  assert.equal(rule.evidence[1]?.note, "Docs page for volumes");
  assert.equal(rule.evidence[2]?.path, "notes/volume-probe.md");
});

test("search matches concept aliases as well as rule text", () => {
  const db = fixtureDb();
  assert.equal(search(db, "snapshots")[0]?.rule.id, "volume.backups");
  // "disk store" appears only as an alias of volume, never in a statement.
  const aliasHits = search(db, "disk store");
  assert.ok(aliasHits.length > 0 && aliasHits.every((hit) => hit.rule.concept_id === "volume"));
});

test("neighbors walks edges in both directions", () => {
  const db = fixtureDb();
  assert.deepEqual(
    neighbors(db, "site")
      .map((edge) => `${edge.direction}:${edge.type}:${edge.concept_id}`)
      .sort(),
    ["in:field_ref:volume", "in:involves:volume-setup", "in:located_in:volume"],
  );
});

test("the graph page embeds every concept and link and escapes the data", () => {
  const { concepts } = validate(join(fixtures, "good"), noFile, noFile);
  const { links } = graphData(concepts);
  assert.deepEqual(links.map((l) => `${l.source}-${l.type}-${l.target}`).sort(), [
    "volume-field_ref-site",
    "volume-located_in-site",
    "volume-setup-involves-site",
    "volume-setup-involves-volume",
  ]);
  const html = renderGraph(concepts);
  assert.ok(!html.includes("/*DATA*/null"));
  assert.ok(html.includes('"id":"volume"'));
  // The page has two script tags; a summary containing one must not add a third.
  const hostile = renderGraph([{ ...concepts[0]!, summary: "</script><b>x</b>" }, ...concepts.slice(1)]);
  assert.equal(hostile.split("</script>").length - 1, 2);
});

test("a process keeps its steps in order with their concepts and rules", () => {
  const db = fixtureDb();
  const setup = getConcept(db, "volume-setup")!;
  assert.deepEqual(setup.steps, [
    {
      step_id: "pick-site",
      title: "Pick a site",
      description: "Choose where the volume lives.",
      concepts: ["site"],
      rules: ["site.capacity-hidden"],
    },
    {
      step_id: "create",
      title: "Create the volume",
      description: "The volume is created in that site and stays there.",
      concepts: ["volume", "site"],
      rules: ["volume.site-fixed"],
    },
  ]);
  assert.deepEqual(getConcept(db, "volume")!.steps, []);
});

test("the validator checks process steps", () => {
  const errors = badErrors();
  assertHasError(errors, "bad-process: a process needs at least two steps");
  assertHasError(errors, 'bad-process: step only concept "nowhere" is not a concept');
  assertHasError(errors, "bad-process: step only names rule nothing.here");
  assertHasError(errors, "steps-on-resource: only kind process may have steps");
});

test("the API routes concepts, neighbors and search, and rejects the rest", () => {
  const db = fixtureDb();
  const get = (path: string) => route(db, new URL(path, "http://localhost"));
  assert.equal((get("/api/concepts").body as { id: string }[]).length, 3);
  assert.equal((get("/api/concepts/Disk%20Store").body as { id: string }).id, "volume");
  assert.deepEqual(get("/api/concepts/site/neighbors").body, neighbors(db, "site"));
  assert.equal(
    (get("/api/search?q=snapshots&limit=1").body as { rule: { id: string } }[])[0]?.rule.id,
    "volume.backups",
  );
  assert.equal(get("/api/search").status, 400);
  assert.equal(get("/api/concepts/unknown").status, 404);
  assert.equal(get("/api/concepts/site/extra/path").status, 404);
  assert.equal(get("/other").status, 404);
  assert.ok(Array.isArray(get("/api/tree").body));
  assert.equal(get("/api/tree?root=nowhere").status, 404);
});

test("golden-path and skill frontmatter link to concepts and reject bad or missing tags", () => {
  const { concepts } = validate(join(fixtures, "good"), noFile, noFile);
  const { guides, links, errors } = collectGuides(concepts, join(fixtures, "skills"), fixtures);
  assert.deepEqual(
    guides.map((g) => g.id),
    ["demo", "demo/intro", "runpod", "golden-path/01-good", "golden-path/02-bad", "golden-path/03-untagged"],
  );
  assert.deepEqual(
    guides.map((g) => g.parent),
    [null, "demo", null, "runpod", "runpod", "runpod"],
  );

  const good = guides.find((g) => g.id === "golden-path/01-good")!;
  assert.deepEqual(
    [good.lanes, good.mcp, good.needs_shell, good.concepts],
    [["runpod-mcp", "rest"], "full", false, ["site", "volume", "volume-setup"]],
  );
  assert.deepEqual(
    links.filter((l) => l.from === good.id).map((l) => `${l.type}:${l.to}:${l.via}`),
    ["uses:volume:frontmatter", "uses:site:frontmatter", "uses:volume-setup:frontmatter"],
  );
  assert.deepEqual(
    links.filter((l) => l.from === "demo").map((l) => `${l.type}:${l.to}`),
    ["explains:volume"],
  );
  assert.equal(guides.find((g) => g.id === "demo/intro")!.mcp, null);

  for (const fragment of [
    '02-bad.md: lane "telnet" is not one of',
    "02-bad.md: mcp must be one of",
    '02-bad.md: concept "nowhere" is not a concept',
    "03-untagged.md: lanes must be a non-empty list",
    "03-untagged.md: mcp must be one of",
    "03-untagged.md: concepts must be a non-empty list",
    "03-untagged.md: links to no concept",
  ]) {
    assertHasError(errors, fragment);
  }
  assert.equal(errors.length, 7);
});

test("the database stores guides and the tree hangs concepts and their guides off their parents", () => {
  const { concepts } = validate(join(fixtures, "good"), noFile, noFile);
  const { guides, links } = collectGuides(concepts, join(fixtures, "skills"), fixtures);
  const good = guides.filter((g) => g.id !== "golden-path/02-bad" && g.id !== "golden-path/03-untagged");
  const db = buildDatabase(
    concepts,
    join(mkdtempSync(join(tmpdir(), "ontology-")), "guides.sqlite"),
    good,
    links.filter((l) => good.some((g) => g.id === l.from)),
  );

  assert.deepEqual(
    guidesFor(db, "volume").map((g) => `${g.kind}:${g.id}:${g.mcp}`),
    ["golden-path:golden-path/01-good:full", "skill:demo:null", "reference:demo/intro:null"],
  );
  assert.deepEqual(
    getConcept(db, "site")!.guides.map((g) => g.id),
    ["golden-path/01-good", "runpod"],
  );

  const roots = tree(db);
  assert.deepEqual(roots.map((node) => node.id).sort(), ["site", "volume", "volume-setup"]);
  assert.deepEqual(
    tree(db, "volume")[0]!.guides.map((g) => g.id),
    ["golden-path/01-good", "demo", "demo/intro"],
  );
});

test("a guide whose id matches a concept id stays a separate graph node", () => {
  const { concepts } = validate(join(fixtures, "good"), noFile, noFile);
  const { guides, links } = collectGuides(concepts, join(fixtures, "skills"), fixtures);
  // A skill named like a concept, as the flash skill and the Flash concept are.
  const clash = { ...guides[0]!, id: "volume" };
  const { nodes, links: graphLinks } = graphData(
    concepts,
    [clash],
    [{ from: "volume", to: "site", type: "explains", via: "frontmatter" }],
  );
  const ids = nodes.map((node) => node.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(ids.includes("volume") && ids.includes("guide:volume"));
  assert.ok(graphLinks.some((l) => l.source === "guide:volume" && l.target === "site" && l.type === "explains"));
  assert.ok(links.length > 0);
});

test("a concept that no guide covers is an error", () => {
  const { concepts } = validate(join(fixtures, "good"), noFile, noFile);
  const { errors } = collectGuides(
    [...concepts, { ...concepts[0]!, id: "orphan", rules: [] }],
    join(fixtures, "skills"),
    fixtures,
  );
  assertHasError(errors, "concept orphan: no skill, reference doc or golden path covers it");
});

test("the formatter is stable and never changes the data", () => {
  const messy = [
    "rules:",
    "  - evidence: [{source: rest-v2-spec, ref: x}]",
    "    statement: Short one-line statement.",
    "    id: volume.x",
    "    status: documented",
    "name: Volume",
    "id: volume",
    "kind: resource",
    "aliases: [ disk, 'store, backup' ]",
    "summary: A long summary that goes on and on so that it has to be folded across more than one line of the file.",
    "product: null",
    "is_a: null",
    "part_of: null",
    "",
  ].join("\n");
  const once = formatConcept(messy);
  assert.equal(formatConcept(once), once);
  assert.ok(once.startsWith("id: volume\nname: Volume\nkind: resource\nsummary: >\n"));
  assert.ok(once.includes('aliases: [disk, "store, backup"]'));
  // Python YAML parsers reject ?, : and quotes in plain flow scalars, so those are quoted.
  const tricky = formatConcept(
    `${once}fields:\n  - { name: q, note: 'Is it? See "docs": yes', url: https://x.io/a }\n`,
  );
  assert.ok(tricky.includes('{ name: q, note: "Is it? See \\"docs\\": yes", url: "https://x.io/a" }'));
  assert.ok(
    once.includes(
      "  - id: volume.x\n    statement: >\n      Short one-line statement.\n    status: documented\n    evidence:\n      - { source: rest-v2-spec, ref: x }",
    ),
  );
  assert.ok(once.split("\n").every((line) => line.length <= 80 || line.includes("{") || line.includes("[")));
  for (const file of ["volume.yaml", "site.yaml", "volume-setup.yaml"]) {
    const text = readFileSync(join(fixtures, "good", file), "utf8");
    assert.equal(formatConcept(formatConcept(text)), formatConcept(text));
  }
});

test("the formatter refuses comments and quotes YAML 1.1 booleans in block context", () => {
  const base = "id: volume\nname: Volume\nkind: resource\nsummary: A volume.\n";
  assert.throws(() => formatConcept(`${base}# a contributor note\nproduct: null\n`), /# comment/);
  assert.throws(() => formatConcept(`${base}product: null # trailing\n`), /# comment/);
  const out = formatConcept(`${base}states:\n  field: power\n  values:\n    "on": Powered.\n    "no": Off.\n`);
  assert.ok(out.includes('    "on": Powered.\n    "no": Off.'), out);
});

test("a guide whose frontmatter is not a map is an error, not a crash", () => {
  const { concepts } = validate(join(fixtures, "good"), noFile, noFile);
  const root = mkdtempSync(join(tmpdir(), "guides-"));
  const skill = join(root, "skills", "demo");
  mkdirSync(join(skill, "reference"), { recursive: true });
  writeFileSync(join(skill, "SKILL.md"), "---\nname: demo\nmetadata:\n  concepts: [volume]\n---\n# Demo\n");
  writeFileSync(join(skill, "reference", "scalar.md"), "---\njust text\n---\n# Scalar\n");
  const { errors } = collectGuides(concepts, join(root, "skills"), root);
  assertHasError(errors, "scalar.md: frontmatter must be a map of keys");
});
