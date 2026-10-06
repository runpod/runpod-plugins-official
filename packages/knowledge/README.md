# runpod-official-plugin-knowledge

The Runpod plugin's knowledge as one JSON file, for programs that serve it to agents,
such as the Runpod MCP server. It is built from
[runpod-plugins-official](https://github.com/runpod/runpod-plugins-official) and
published at the plugin's version on every release.

This package is not how you install the plugin. Plugin and skills.sh users install from
the repo as described in its README.

```js
import { loadKnowledge } from "runpod-official-plugin-knowledge"; // or require("runpod-official-plugin-knowledge")

const { version, commit, guides, concepts, links } = loadKnowledge();
```

## What is inside

| Field | Contents |
|---|---|
| `guides` | Every skill, reference doc and golden path: id, kind, title, description, markdown body, parent guide, the concepts it covers, and for golden paths the `lanes` it drives and its `mcp` level (`full`, `partial` or `none`: can an agent with only the Runpod MCP tools finish it). |
| `concepts` | The concept graph: one entry per concept with fields, states, relations and rules, each rule with its public evidence. |
| `links` | Guide-to-concept links: a golden path `uses` a concept, a doc `explains` it. |
| `version`, `commit` | The plugin release and commit the bundle was built from. |

Guide ids follow the file layout: `runpod-usage` (a skill), `runpod-usage/storage` (a
reference doc), `golden-path/06-dev-pod` (a golden path). The full shape is in
`index.d.ts`. `format` changes when the shape changes incompatibly.

The data is loaded with a static import, so bundlers such as Vercel and esbuild include
it without extra configuration. Requires Node 20.10 or later.
