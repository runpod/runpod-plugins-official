// Poke at the built SQLite file from a terminal.
//
//   node src/cli.ts concept <id|name|alias>
//   node src/cli.ts search "<text>" [--limit N]
//   node src/cli.ts neighbors <id>
//   node src/cli.ts tree [id|name|alias]   the concept hierarchy; with a concept, its subtree and linked guides
//   node src/cli.ts sql "<select ...>"

import { existsSync } from "node:fs";
import { DEFAULT_DB_PATH } from "./build-sqlite.ts";
import { getConcept, neighbors, openOntology, search, type TreeNode, tree } from "./query.ts";

const [command, argument = ""] = process.argv.slice(2).filter((arg) => !arg.startsWith("--"));
const flags = process.argv.slice(2);
const limitAt = flags.indexOf("--limit");
const limit = limitAt >= 0 ? Number(flags[limitAt + 1]) : 10;

if (!command || (!argument && command !== "tree")) {
  console.error(
    'usage: cli.ts concept <ref> | search "<text>" [--limit N] | neighbors <id> | tree [ref] | sql "<select>"',
  );
  process.exit(2);
}
if (!existsSync(DEFAULT_DB_PATH)) {
  console.error(`no database at ${DEFAULT_DB_PATH}; run pnpm build:sqlite first`);
  process.exit(1);
}

const db = openOntology(DEFAULT_DB_PATH);
const print = (value: unknown) => console.log(JSON.stringify(value, null, 2));

switch (command) {
  case "concept": {
    const record = getConcept(db, argument);
    if (!record) {
      console.error(`no concept matches "${argument}"`);
      process.exit(1);
    }
    print(record);
    break;
  }
  case "search":
    for (const hit of search(db, argument, { limit })) {
      console.log(
        `${hit.rank.toFixed(2).padStart(7)}  ${hit.rule.id}  [${hit.rule.status}${hit.rule.conflict ? ", conflict" : ""}]`,
      );
      console.log(`         ${hit.rule.statement}`);
    }
    break;
  case "neighbors":
    for (const edge of neighbors(db, argument)) {
      console.log(
        edge.direction === "out"
          ? `${argument} -${edge.type}-> ${edge.concept_id}`
          : `${edge.concept_id} -${edge.type}-> ${argument}`,
      );
    }
    break;
  case "tree": {
    const root = argument ? getConcept(db, argument)?.id : undefined;
    if (argument && !root) {
      console.error(`no concept matches "${argument}"`);
      process.exit(1);
    }
    // Without a concept: the whole hierarchy with guide counts. With one: its
    // subtree, with every linked golden path and doc listed under each concept.
    const expand = Boolean(root);
    const counts = (node: TreeNode) => {
      const examples = node.guides.filter((g) => g.kind === "golden-path").length;
      const docs = node.guides.length - examples;
      const parts = [
        examples && `${examples} example${examples > 1 ? "s" : ""}`,
        docs && `${docs} doc${docs > 1 ? "s" : ""}`,
      ].filter(Boolean);
      return parts.length ? `  (${parts.join(", ")})` : "";
    };
    const print = (node: TreeNode, prefix: string, last: boolean, top: boolean) => {
      const branch = top ? "" : last ? "└── " : "├── ";
      const relation = node.relation === "is_a" ? " (kind of)" : "";
      console.log(`${prefix}${branch}${node.name}${relation} [${node.id}]${expand ? "" : counts(node)}`);
      const inner = top ? "" : prefix + (last ? "    " : "│   ");
      const leaves = expand ? node.guides : [];
      const items = [...leaves.map((guide) => ({ guide })), ...node.children.map((child) => ({ child }))];
      items.forEach((item, index) => {
        const isLast = index === items.length - 1;
        if ("guide" in item) {
          const g = item.guide;
          const mark = g.kind === "golden-path" ? "◆" : "▪";
          const mcp = g.mcp ? `  mcp: ${g.mcp}` : "";
          console.log(`${inner}${isLast ? "└── " : "├── "}${mark} ${g.id}${mcp}`);
        } else print(item.child, inner, isLast, false);
      });
    };
    const roots = tree(db, root);
    const platform = root ? roots : roots.filter((node) => node.kind === "platform");
    const loose = root ? [] : roots.filter((node) => node.kind !== "platform");
    for (const node of platform) print(node, "", true, true);
    if (loose.length) {
      console.log(`${platform.length ? "\n" : ""}Not under the platform (no is_a or part_of):`);
      for (const [index, node] of loose.entries()) print(node, "", index === loose.length - 1, false);
    }
    if (expand) console.log("\n◆ golden path (example)  ▪ skill or reference doc");
    break;
  }
  case "sql":
    console.table(db.prepare(argument).all());
    break;
  default:
    console.error(`unknown command ${command}`);
    process.exit(2);
}
