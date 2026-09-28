// Vercel function for /api/*. vercel.json compiles src/ to dist/ (Vercel would
// otherwise rename the .ts imports), builds ontology.sqlite next to this file and
// rewrites every /api path here. The graph page is served statically.
import { fileURLToPath } from "node:url";
import { openOntology } from "../dist/query.js";
import { listener } from "../dist/server.js";

const db = openOntology(fileURLToPath(new URL("./ontology.sqlite", import.meta.url)));

export default listener(db);
