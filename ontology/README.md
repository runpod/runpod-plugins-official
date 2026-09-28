# Concept graph tooling

The concept files live in
[`plugins/runpod/skills/runpod-usage/concepts/`](../plugins/runpod/skills/runpod-usage/concepts/README.md),
so they ship with the plugin and agents can read them directly. This directory holds
the tooling that checks them and builds them into other forms. It needs Node 24 or later.

```bash
cd ontology/tools
pnpm install
pnpm validate --strict   # schema, cross-file, spec and public-only checks (CI runs this)
pnpm test
pnpm build:sqlite        # build/ontology.sqlite
pnpm build:graph         # build/graph.html, a force-directed graph with a panel per concept
pnpm query concept pod   # or: search "<text>", neighbors <id>, sql "<query>"
pnpm query tree          # the concept hierarchy with guide counts; tree <concept> lists its guides
pnpm serve               # http://localhost:8787: the graph page plus the JSON API below
```

The server is read-only: `GET /api/concepts`, `/api/concepts/<id|name|alias>`,
`/api/concepts/<ref>/neighbors`, `/api/search?q=<text>` and `/api/tree?root=<ref>`. It also deploys to Vercel
with the project's root directory set to `ontology/tools`: `vercel.json` compiles the
tools, builds the SQLite file next to the function in `api/index.mjs`, and serves the
graph page statically.

- `sqlite/schema.sql` is the table layout. `tools/src/query.ts` is the query layer an agent tool would use.
- Fields and paths are checked against the REST v2 snapshot at
  `testdata/runpod-migrate/v2-openapi.json`, the same one the runpod-migrate checks use.
- Every `source: skill` evidence path must exist, so renaming or deleting a cited skill file fails the check.

To add or change a concept, follow `.claude/skills/add-concept/SKILL.md`.

## Guides, examples and concepts in one package

`pnpm build:bundle` writes `packages/knowledge/knowledge.json`, the `@runpod/knowledge`
package. It holds every skill, reference doc and golden path, the concept files, and
the links between them:

```
concept ──rules──▶ facts with public evidence
   ▲  ▲
   │  └── explains ── skill / reference doc   (a rule cites the doc as evidence, or the doc
   │                                           lists the concept in its frontmatter)
   └───── uses ────── golden path             (the path's frontmatter lists the concept,
                                               or a rule cites the path as evidence)
```

- Golden-path frontmatter declares `lanes`, `mcp` and `concepts`, each `SKILL.md` lists
  `metadata.concepts`, and a reference doc lists `concepts:` unless a rule already cites it.
  `pnpm check:guides` rejects a guide that links to no concept, a missing tag, or an unknown
  lane, level or concept id, and CI runs it.
- Every doc and golden path also records its parent (its skill, its parent path, or the
  `runpod` router for a top-level golden path), so nothing in the graph stands alone.
- The graph page shows guides as squares linked to their concepts (golden paths and skills
  by default; reference docs can be switched on), and `pnpm query tree` prints the same
  links as a tree.
- `pnpm build:bundle --suggest` lists the concepts each golden path mentions but does not
  declare, as candidates to review.
- The build prints coverage: how many concepts have a guide and how many have an example.
  A concept with no example, or a path with no concepts, is a gap to fill.
- The Runpod MCP server can depend on the package and serve the guides and concepts as
  tools, and the same file can be ingested by other assistants.

