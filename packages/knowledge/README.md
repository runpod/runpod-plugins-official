# @runpod/knowledge

The Runpod plugin's skills, reference docs, golden paths and concept graph as one
JSON file, for programs that serve them, such as the Runpod MCP server.

```js
import { loadKnowledge } from "@runpod/knowledge";
const { version, guides, concepts } = loadKnowledge();
```

`knowledge.json` is built from this repo by `ontology/tools/src/build-bundle.ts`
when the package is packed. The shape is in `index.d.ts`; `format` changes when
it changes incompatibly.
