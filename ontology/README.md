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
pnpm serve               # http://localhost:8787: the graph page plus the JSON API below
```

The server is read-only: `GET /api/concepts`, `/api/concepts/<id|name|alias>`,
`/api/concepts/<ref>/neighbors` and `/api/search?q=<text>`. It also deploys to Vercel
with the project's root directory set to `ontology/tools`: `vercel.json` compiles the
tools, builds the SQLite file next to the function in `api/index.mjs`, and serves the
graph page statically.

- `sqlite/schema.sql` is the table layout. `tools/src/query.ts` is the query layer an agent tool would use.
- Fields and paths are checked against the REST v2 snapshot at
  `testdata/runpod-migrate/v2-openapi.json`, the same one the runpod-migrate checks use.
- Every `source: skill` evidence path must exist, so renaming or deleting a cited skill file fails the check.

To add or change a concept, follow `.claude/skills/add-concept/SKILL.md`.
