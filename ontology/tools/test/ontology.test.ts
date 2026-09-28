import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { collectGuides } from "../src/build-bundle.ts";
import { graphData, renderGraph } from "../src/build-graph.ts";
import { buildDatabase } from "../src/build-sqlite.ts";
import { getConcept, neighbors, resolve, search } from "../src/query.ts";
import { route } from "../src/server.ts";
import { validate } from "../src/validate.ts";

const fixtures = fileURLToPath(new URL("fixtures/", import.meta.url));
const noFile = join(fixtures, "does-not-exist");
const badErrors = () => validate(join(fixtures, "bad"), noFile, noFile).errors;

const assertHasError = (errors: string[], fragment: string) =>
  assert.ok(errors.some((error) => error.includes(fragment)), `missing error containing: ${fragment}\n${errors.join("\n")}`);

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
  assertHasError(badErrors(), "broken: rule broken.missing-skill-file cites skill file plugins/runpod/skills/nowhere/SKILL.md");
});

test("evidence with no ref, url, path or note is rejected", () => {
  assertHasError(badErrors(), "evidence needs at least one of ref, url, path or note");
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
  assert.deepEqual(volume.rules.map((rule) => rule.id), ["volume.backups", "volume.site-fixed"]);
  assert.deepEqual(volume.edges_out, [
    { type: "field_ref", target_id: "site" },
    { type: "located_in", target_id: "site" },
  ]);
  assert.deepEqual(volume.linked_rules.map((rule) => rule.id), ["site.capacity-hidden"]);

  const site = getConcept(db, "site")!;
  assert.deepEqual(site.transitions, [{ action: "close", from_state: "OPEN", to_state: "CLOSED" }]);
  assert.deepEqual(site.edges_in.map((edge) => `${edge.type}:${edge.source_id}`), [
    "field_ref:volume",
    "involves:volume-setup",
    "located_in:volume",
  ]);
});

test("evidence carries refs, urls, paths and notes", () => {
  const db = fixtureDb();
  const rule = getConcept(db, "volume")!.rules.find((r) => r.id === "volume.site-fixed")!;
  assert.deepEqual(rule.evidence.map((e) => e.source), ["rest-v2-spec", "public-docs", "other"]);
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
    neighbors(db, "site").map((edge) => `${edge.direction}:${edge.type}:${edge.concept_id}`).sort(),
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
    { step_id: "pick-site", title: "Pick a site", description: "Choose where the volume lives.", concepts: ["site"], rules: ["site.capacity-hidden"] },
    { step_id: "create", title: "Create the volume", description: "The volume is created in that site and stays there.", concepts: ["volume", "site"], rules: ["volume.site-fixed"] },
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
  assert.equal((get("/api/search?q=snapshots&limit=1").body as { rule: { id: string } }[])[0]?.rule.id, "volume.backups");
  assert.equal(get("/api/search").status, 400);
  assert.equal(get("/api/concepts/unknown").status, 404);
  assert.equal(get("/api/concepts/site/extra/path").status, 404);
  assert.equal(get("/other").status, 404);
});

test("golden-path frontmatter links to concepts and rejects unknown lanes, levels and concepts", () => {
  const { concepts } = validate(join(fixtures, "good"), noFile, noFile);
  const { guides, links, errors } = collectGuides(concepts, join(fixtures, "skills"), fixtures);
  assert.deepEqual(guides.map((g) => g.id), ["demo", "demo/intro", "golden-path/01-good", "golden-path/02-bad", "golden-path/03-untagged"]);

  const good = guides.find((g) => g.id === "golden-path/01-good")!;
  assert.deepEqual([good.tagged, good.mcp, good.needs_shell, good.concepts], [true, "full", false, ["site", "volume"]]);
  assert.deepEqual(links.filter((l) => l.from === good.id).map((l) => `${l.type}:${l.to}:${l.via}`), ["uses:volume:frontmatter", "uses:site:frontmatter"]);

  // An untagged path falls back to its Lane line and declares no mcp level.
  const untagged = guides.find((g) => g.id === "golden-path/03-untagged")!;
  assert.deepEqual([untagged.tagged, untagged.lanes, untagged.mcp, untagged.needs_shell], [false, ["runpodctl", "ssh"], null, true]);

  for (const fragment of ['lane "telnet" is not one of', "mcp must be one of", 'concept "nowhere" is not a concept']) {
    assertHasError(errors, `02-bad.md: ${fragment}`);
  }
  assert.equal(errors.length, 3);
});
