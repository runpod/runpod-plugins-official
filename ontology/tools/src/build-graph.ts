// Writes a single-file HTML graph: nodes are concepts plus the plugin's skills,
// reference docs and golden paths; links are is_a, part_of, typed relations,
// field references, and the guide links (a golden path is an example of a
// concept, a doc explains it). Hover highlights a node's neighbours; click opens
// its fields, states, rules and evidence, or a guide's lanes, mcp level and concepts.
//
//   node src/build-graph.ts [out.html]     default: ../build/graph.html
//
// The page loads the force-graph library from unpkg, so opening it needs a
// network connection; the data itself is embedded.

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { collectGuides, type Guide, type Link } from "./build-bundle.ts";
import { ONTOLOGY_DIR } from "./load.ts";
import type { Concept } from "./schema.ts";
import { validate } from "./validate.ts";

export const DEFAULT_GRAPH_PATH = join(ONTOLOGY_DIR, "build/graph.html");

export interface GraphLink {
  source: string;
  target: string;
  type: string;
}

/** A guide drawn as a node, shaped like a concept so the page treats both alike. */
export interface GuideNode {
  id: string;
  name: string;
  kind: "skill" | "reference" | "golden-path";
  summary: string;
  aliases: string[];
  rules: [];
  guide: Pick<Guide, "title" | "path" | "lanes" | "mcp" | "needs_shell">;
}

const shortName = (guide: Guide) => (guide.kind === "golden-path" ? guide.id.replace("golden-path/", "") : guide.id);

export function graphData(
  concepts: Concept[],
  guides: Guide[] = [],
  guideLinks: Link[] = [],
): { nodes: (Concept | GuideNode)[]; links: GraphLink[] } {
  const links: GraphLink[] = [];
  const seen = new Set<string>();
  const add = (source: string, target: string | null | undefined, type: string) => {
    const key = `${source}|${type}|${target}`;
    if (!target || seen.has(key)) return;
    seen.add(key);
    links.push({ source, target, type });
  };
  for (const concept of concepts) {
    add(concept.id, concept.is_a, "is_a");
    add(concept.id, concept.part_of, "part_of");
    for (const relation of concept.relations) add(concept.id, relation.target, relation.type);
    for (const field of concept.fields) add(concept.id, field.ref, "field_ref");
    for (const step of concept.steps) for (const target of step.concepts) add(concept.id, target, "involves");
  }
  for (const link of guideLinks) add(link.from, link.to, link.type === "uses" ? "example" : "explains");
  const guideNodes: GuideNode[] = guides.map((guide) => ({
    id: guide.id,
    name: shortName(guide),
    kind: guide.kind,
    summary: guide.description,
    aliases: [],
    rules: [],
    guide: { title: guide.title, path: guide.path, lanes: guide.lanes, mcp: guide.mcp, needs_shell: guide.needs_shell },
  }));
  return { nodes: [...concepts, ...guideNodes], links };
}

export function renderGraph(concepts: Concept[], guides: Guide[] = [], guideLinks: Link[] = []): string {
  // `</script>` inside the data would end the script block early.
  const data = JSON.stringify(graphData(concepts, guides, guideLinks)).replaceAll("<", "\\u003c");
  return PAGE.replace("/*DATA*/null", data);
}

const PAGE = String.raw`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Runpod concept graph</title>
<script src="https://unpkg.com/force-graph@1"></script>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; display: flex; height: 100vh; font: 13px/1.45 system-ui, sans-serif; background: #0f1115; color: #d8dbe2; }
  #stage { flex: 1; min-width: 0; position: relative; }
  #graph { position: absolute; inset: 0; }
  #controls { position: absolute; top: 10px; left: 10px; z-index: 2; background: #171a21ee; border: 1px solid #2a2f3a; border-radius: 8px; padding: 10px 12px; max-width: 250px; }
  #controls input[type=search] { width: 100%; padding: 5px 7px; background: #0f1115; color: inherit; border: 1px solid #2a2f3a; border-radius: 5px; margin-bottom: 8px; }
  #controls h4 { margin: 8px 0 4px; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #8a90a0; }
  #controls label { display: flex; align-items: center; gap: 6px; cursor: pointer; }
  .swatch { width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex: none; }
  .line { width: 14px; height: 3px; display: inline-block; flex: none; }
  #side { width: 460px; overflow-y: auto; padding: 14px 18px 40px; background: #151820; border-left: 1px solid #2a2f3a; }
  #side h2 { margin: 0 0 2px; font-size: 18px; }
  #side h3 { margin: 18px 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: #8a90a0; }
  .meta { color: #8a90a0; margin-bottom: 8px; }
  .summary { margin: 8px 0; }
  table { border-collapse: collapse; width: 100%; font-size: 12px; }
  td, th { text-align: left; padding: 3px 6px 3px 0; border-bottom: 1px solid #222734; vertical-align: top; }
  code { font: 11.5px ui-monospace, monospace; color: #b9c2ff; }
  .rule { border: 1px solid #262b37; border-radius: 6px; padding: 8px 10px; margin: 8px 0; }
  .rule .id { font: 11px ui-monospace, monospace; color: #8a90a0; }
  .badge { display: inline-block; font-size: 10.5px; padding: 0 6px; border-radius: 9px; margin-left: 4px; border: 1px solid #3a4150; }
  .conflict { color: #ff7a7a; border-color: #6b2a2a; }
  .evidence { margin: 6px 0 0 0; padding-left: 16px; color: #9aa1b2; font-size: 12px; }
  a { color: #7fb4ff; }
  .link { cursor: pointer; color: #7fb4ff; }
  .empty { color: #6b7180; font-style: italic; }
  ol.steps { padding-left: 20px; margin: 4px 0; }
  ol.steps li { margin-bottom: 10px; }
  .full { color: #62d98b; border-color: #2a6b3f; } .partial { color: #ffcf5c; border-color: #6b5a2a; } .none { color: #ff7a7a; border-color: #6b2a2a; }
</style>
</head>
<body>
<div id="stage">
  <div id="graph"></div>
  <div id="controls">
    <input id="find" type="search" list="names" placeholder="Find a concept or guide">
    <datalist id="names"></datalist>
    <h4>Kinds</h4><div id="kinds"></div>
    <h4>Links</h4><div id="links"></div>
  </div>
</div>
<aside id="side"><p class="empty">Click a concept or guide. Hover to highlight its neighbours; scroll to zoom. Squares are guides.</p></aside>
<script>
const DATA = /*DATA*/null;

const KIND_COLORS = {
  platform: "#ffffff", resource: "#4f9dff", component: "#7fd1ff", catalog: "#62d98b",
  capability: "#c49bff", billing: "#ffcf5c", limit: "#ff7a7a", tool: "#ff9ad5", external: "#9aa1b2",
  infrastructure: "#b0875a", process: "#ff5ca8",
  skill: "#e8e8e8", reference: "#8f96a8", "golden-path": "#ffb347",
};
const GUIDE_KINDS = new Set(["skill", "reference", "golden-path"]);
const isGuide = (n) => GUIDE_KINDS.has(n.kind);
const LINK_COLORS = {
  is_a: "#ffffff", part_of: "#7fd1ff", requires: "#ff7a7a", uses: "#9aa1b2", located_in: "#62d98b",
  runs_on: "#c49bff", billed_by: "#ffcf5c", constrained_by: "#ff9f5c", field_ref: "#4a5060", involves: "#ff5ca8",
  example: "#ffb347", explains: "#8f96a8",
};

const byId = new Map(DATA.nodes.map((n) => [n.id, n]));
const neighbours = new Map(DATA.nodes.map((n) => [n.id, new Set()]));
for (const l of DATA.links) { neighbours.get(l.source).add(l.target); neighbours.get(l.target).add(l.source); }
const hiddenLinkTypes = new Set(["field_ref"]);
const hiddenKinds = new Set(["reference"]);
const shown = (id) => !hiddenKinds.has(byId.get(id).kind);
let hover = null, selected = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const idOf = (end) => (typeof end === "object" ? end.id : end);
const focus = () => hover ?? selected;
const active = (id) => { const f = focus(); return !f || f === id || neighbours.get(f).has(id); };

const stage = document.getElementById("stage");
const graph = ForceGraph()(document.getElementById("graph"))
  .width(stage.clientWidth)
  .height(stage.clientHeight)
  .graphData({ nodes: DATA.nodes.map((n) => ({ ...n })), links: DATA.links.map((l) => ({ ...l })) })
  .backgroundColor("#0f1115")
  .nodeId("id")
  .nodeVal((n) => (isGuide(n) ? 1.5 : 2 + n.rules.length / 3))
  .nodeVisibility((n) => shown(n.id))
  .nodeLabel((n) => esc(n.name) + " (" + n.kind + ")")
  .nodeColor((n) => (active(n.id) ? KIND_COLORS[n.kind] : "#2a2f3a"))
  .nodeCanvasObjectMode((n) => (isGuide(n) ? "replace" : "after"))
  .nodeCanvasObject((n, ctx, scale) => {
    const f = focus();
    if (isGuide(n)) {
      const size = 5;
      ctx.fillStyle = active(n.id) ? KIND_COLORS[n.kind] : "#2a2f3a";
      ctx.fillRect(n.x - size / 2, n.y - size / 2, size, size);
    }
    if (scale < 1.4 && !(f && active(n.id))) return;
    ctx.font = 12 / scale + "px system-ui";
    ctx.textAlign = "center";
    ctx.fillStyle = active(n.id) ? "#d8dbe2" : "#3a4050";
    ctx.fillText(n.name, n.x, n.y + (isGuide(n) ? 4 : Math.sqrt(2 + n.rules.length / 3) * 4) + 12 / scale);
  })
  .nodePointerAreaPaint((n, color, ctx) => { ctx.fillStyle = color; ctx.fillRect(n.x - 4, n.y - 4, 8, 8); })
  .linkVisibility((l) => !hiddenLinkTypes.has(l.type) && shown(idOf(l.source)) && shown(idOf(l.target)))
  .linkColor((l) => { const f = focus(); return !f || idOf(l.source) === f || idOf(l.target) === f ? LINK_COLORS[l.type] : "#1d2129"; })
  .linkWidth((l) => { const f = focus(); return f && (idOf(l.source) === f || idOf(l.target) === f) ? 2 : 1; })
  .linkDirectionalArrowLength(4)
  .linkDirectionalArrowRelPos(1)
  .linkLabel((l) => l.type)
  .autoPauseRedraw(false)
  .onNodeHover((n) => { hover = n ? n.id : null; document.body.style.cursor = n ? "pointer" : ""; })
  .onNodeClick((n) => select(n.id))
  .onBackgroundClick(() => { selected = null; });
window.addEventListener("resize", () => graph.width(stage.clientWidth).height(stage.clientHeight));

function select(id, center) {
  selected = id;
  render(byId.get(id));
  if (center) {
    const n = graph.graphData().nodes.find((x) => x.id === id);
    graph.centerAt(n.x, n.y, 600); graph.zoom(3, 600);
  }
}

function evidenceList(items) {
  if (!items || !items.length) return "";
  return '<ul class="evidence">' + items.map((e) => "<li>" + esc(e.source)
    + (e.ref ? " · <code>" + esc(e.ref) + "</code>" : "")
    + (e.url ? ' · <a href="' + esc(e.url) + '" target="_blank" rel="noopener">' + esc(e.url) + "</a>" : "")
    + (e.path ? " · <code>" + esc(e.path) + "</code>" : "")
    + (e.seen ? " · seen " + esc(e.seen) : "")
    + (e.note ? " — " + esc(e.note) : "") + "</li>").join("") + "</ul>";
}

const conceptLink = (id) => '<span class="link" data-id="' + esc(id) + '">' + esc(byId.get(id)?.name ?? id) + "</span>";
const mcpBadge = (level) => (level ? '<span class="badge ' + esc(level) + '">mcp: ' + esc(level) + "</span>" : "");

function renderGuide(g) {
  const concepts = DATA.links.filter((l) => l.source === g.id);
  document.getElementById("side").innerHTML =
    "<h2>" + esc(g.guide.title) + "</h2>"
    + '<div class="meta"><code>' + esc(g.id) + "</code> · " + esc(g.kind) + mcpBadge(g.guide.mcp) + "</div>"
    + '<div class="summary">' + esc(g.summary) + "</div>"
    + (g.guide.lanes.length ? '<div class="meta">Lanes: ' + g.guide.lanes.map((x) => "<code>" + esc(x) + "</code>").join(" ") + "</div>" : "")
    + '<div class="meta">Written with shell steps: ' + (g.guide.needs_shell ? "yes" : "no") + "</div>"
    + '<div class="meta">File: <code>' + esc(g.guide.path) + "</code></div>"
    + "<h3>Concepts (" + concepts.length + ")</h3>"
    + (concepts.length ? "<table>" + concepts.map((l) => "<tr><td>" + esc(l.type) + "</td><td>" + conceptLink(l.target) + "</td></tr>").join("") + "</table>" : '<p class="empty">none</p>');
}

function render(c) {
  if (isGuide(c)) return renderGuide(c);
  const guideLinks = DATA.links.filter((l) => l.target === c.id && isGuide(byId.get(l.source)));
  const rules = c.rules;
  const out = DATA.links.filter((l) => l.source === c.id);
  const into = DATA.links.filter((l) => l.target === c.id && !isGuide(byId.get(l.source)));
  const s = c.surfaces || {};
  const surfaceRows = [
    ["REST v2", [s.rest_v2?.schema, ...(s.rest_v2?.paths ?? [])].filter(Boolean)],
    ["GraphQL", [s.graphql?.type, ...(s.graphql?.queries ?? []), ...(s.graphql?.mutations ?? [])].filter(Boolean)],
    ["MCP", s.mcp ?? []], ["runpodctl", s.runpodctl ?? []], ["Console", s.console ? [s.console] : []],
  ].filter(([, v]) => v.length);

  document.getElementById("side").innerHTML =
    "<h2>" + esc(c.name) + "</h2>"
    + '<div class="meta"><code>' + esc(c.id) + "</code> · " + esc(c.kind) + (c.product ? " · " + esc(c.product) : "")
    + "</div>"
    + '<div class="summary">' + esc(c.summary) + "</div>"
    + (c.aliases.length ? '<div class="meta">Also: ' + c.aliases.map(esc).join(", ") + "</div>" : "")
    + (guideLinks.length ? "<h3>Guides (" + guideLinks.length + ")</h3><table>" + guideLinks.map((l) => {
        const g = byId.get(l.source);
        return "<tr><td>" + esc(g.kind) + "</td><td>" + conceptLink(g.id) + mcpBadge(g.guide.mcp) + "</td></tr>";
      }).join("") + "</table>" : "")
    + "<h3>Links</h3>"
    + (out.length || into.length
      ? "<table>" + out.map((l) => "<tr><td>→ " + esc(l.type) + "</td><td>" + conceptLink(l.target) + "</td></tr>").join("")
        + into.map((l) => "<tr><td>← " + esc(l.type) + "</td><td>" + conceptLink(l.source) + "</td></tr>").join("") + "</table>"
      : '<p class="empty">none</p>')
    + (surfaceRows.length ? "<h3>Surfaces</h3><table>" + surfaceRows.map(([k, v]) => "<tr><td>" + k + "</td><td>" + v.map((x) => "<code>" + esc(x) + "</code>").join("<br>") + "</td></tr>").join("") + "</table>" : "")
    + (c.fields.length ? "<h3>Fields</h3><table><tr><th>name</th><th>type</th><th>set</th></tr>" + c.fields.map((f) =>
        "<tr><td><code>" + esc(f.name) + "</code>" + (f.required ? " *" : "") + "</td><td>" + esc(f.type)
        + (f.values ? "<br><code>" + f.values.map(esc).join(" | ") + "</code>" : "") + (f.ref ? "<br>→ " + conceptLink(f.ref) : "")
        + "</td><td>" + esc(f.set) + "</td></tr>").join("") + "</table>" : "")
    + (c.states ? "<h3>States (" + esc(c.states.field) + ")</h3><table>" + Object.entries(c.states.values).map(([k, v]) => "<tr><td><code>" + esc(k) + "</code></td><td>" + esc(v) + "</td></tr>").join("") + "</table>"
        + (c.states.transitions.length ? "<table>" + c.states.transitions.map((t) => "<tr><td><code>" + esc(t.action) + "</code></td><td>" + t.from.map(esc).join(", ") + " → " + esc(t.to) + "</td></tr>").join("") + "</table>" : "") : "")
    + (c.steps && c.steps.length ? "<h3>Steps</h3><ol class=\"steps\">" + c.steps.map((st) => "<li><b>" + esc(st.title) + "</b><div>" + esc(st.description) + "</div>"
        + '<div class="meta">involves ' + st.concepts.map(conceptLink).join(", ") + "</div>"
        + (st.rules.length ? '<div class="meta">rules ' + st.rules.map((x) => conceptLink(x.split(".")[0]) + " <code>" + esc(x) + "</code>").join(", ") + "</div>" : "")
        + "</li>").join("") + "</ol>" : "")
    + "<h3>Rules (" + rules.length + ")</h3>"
    + (rules.length ? rules.map((r) => '<div class="rule"><div class="id">' + esc(r.id)
        + '<span class="badge">' + esc(r.status) + "</span>"
        + (r.conflict ? '<span class="badge conflict">conflict</span>' : "") + "</div>"
        + "<div>" + esc(r.statement) + "</div>"
        + (r.applies_to.length ? '<div class="meta">applies to ' + r.applies_to.map((a) => "<code>" + esc(a) + "</code>").join(" ") + "</div>" : "")
        + (r.on_violation !== undefined ? '<div class="meta">on violation: ' + esc(r.on_violation) + "</div>" : "")
        + (r.see.length ? '<div class="meta">see ' + r.see.map((x) => conceptLink(x.split(".")[0]) + " <code>" + esc(x) + "</code>").join(", ") + "</div>" : "")
        + evidenceList(r.evidence) + "</div>").join("") : '<p class="empty">none</p>');
}

document.getElementById("side").addEventListener("click", (e) => {
  const id = e.target.dataset?.id;
  if (id && byId.has(id)) select(id, true);
});

const kinds = [...new Set(DATA.nodes.map((n) => n.kind))];
document.getElementById("kinds").innerHTML = kinds.map((k) =>
  '<label><input type="checkbox" data-kind="' + k + '"' + (hiddenKinds.has(k) ? "" : " checked") + '><span class="swatch" style="background:' + KIND_COLORS[k] + (GUIDE_KINDS.has(k) ? ";border-radius:1px" : "") + '"></span>' + k + " (" + DATA.nodes.filter((n) => n.kind === k).length + ")</label>").join("");
document.getElementById("kinds").addEventListener("change", (e) => {
  const k = e.target.dataset.kind;
  e.target.checked ? hiddenKinds.delete(k) : hiddenKinds.add(k);
});

const linkTypes = [...new Set(DATA.links.map((l) => l.type))];
document.getElementById("links").innerHTML = linkTypes.map((t) =>
  '<label><input type="checkbox" data-type="' + t + '"' + (hiddenLinkTypes.has(t) ? "" : " checked") + '><span class="line" style="background:' + LINK_COLORS[t] + '"></span>' + t + "</label>").join("");
document.getElementById("links").addEventListener("change", (e) => {
  const t = e.target.dataset.type;
  e.target.checked ? hiddenLinkTypes.delete(t) : hiddenLinkTypes.add(t);
});

document.getElementById("names").innerHTML = DATA.nodes.map((n) => '<option value="' + esc(n.name) + '">').join("");
document.getElementById("find").addEventListener("change", (e) => {
  const q = e.target.value.trim().toLowerCase();
  const n = DATA.nodes.find((x) => x.name.toLowerCase() === q || x.id === q || x.aliases.some((a) => a.toLowerCase() === q));
  if (n) { hiddenKinds.delete(n.kind); document.querySelector('[data-kind="' + n.kind + '"]').checked = true; select(n.id, true); }
});
</script>
</body>
</html>
`;

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const out = resolve(process.argv[2] ?? DEFAULT_GRAPH_PATH);
  const { concepts, errors } = validate();
  const guides = errors.length ? { guides: [], links: [], errors: [] } : collectGuides(concepts);
  const all = [...errors, ...guides.errors];
  if (all.length) {
    for (const error of all) console.error(`error ${error}`);
    console.error(`not building: ${all.length} errors`);
    process.exit(1);
  }
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, renderGraph(concepts, guides.guides, guides.links));
  const { links } = graphData(concepts, guides.guides, guides.links);
  console.log(`wrote ${out} (${concepts.length} concepts, ${guides.guides.length} guides, ${links.length} links)`);
}
