// Poke at the built SQLite file from a terminal.
//
//   node src/cli.ts concept <id|name|alias>
//   node src/cli.ts search "<text>" [--limit N]
//   node src/cli.ts neighbors <id>
//   node src/cli.ts sql "<select ...>"

import { existsSync } from "node:fs";
import { DEFAULT_DB_PATH } from "./build-sqlite.ts";
import { getConcept, neighbors, openOntology, search } from "./query.ts";

const [command, argument] = process.argv.slice(2).filter((arg) => !arg.startsWith("--"));
const flags = process.argv.slice(2);
const limitAt = flags.indexOf("--limit");
const limit = limitAt >= 0 ? Number(flags[limitAt + 1]) : 10;

if (!command || !argument) {
  console.error('usage: cli.ts concept <ref> | search "<text>" [--limit N] | neighbors <id> | sql "<select>"');
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
      console.log(`${hit.rank.toFixed(2).padStart(7)}  ${hit.rule.id}  [${hit.rule.status}${hit.rule.conflict ? ", conflict" : ""}]`);
      console.log(`         ${hit.rule.statement}`);
    }
    break;
  case "neighbors":
    for (const edge of neighbors(db, argument)) {
      console.log(edge.direction === "out" ? `${argument} -${edge.type}-> ${edge.concept_id}` : `${edge.concept_id} -${edge.type}-> ${argument}`);
    }
    break;
  case "sql":
    console.table(db.prepare(argument).all());
    break;
  default:
    console.error(`unknown command ${command}`);
    process.exit(2);
}
