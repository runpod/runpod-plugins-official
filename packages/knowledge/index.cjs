// A static require, not a file read, so bundlers (Vercel, esbuild) include the data.
const knowledge = require("./knowledge.json");

/** The bundle. See index.d.ts for its shape. */
function loadKnowledge() {
  return knowledge;
}

module.exports = { loadKnowledge };
