// A static import, not a file read, so bundlers (Vercel, esbuild) include the data.
import knowledge from "./knowledge.json" with { type: "json" };

/** The bundle. See index.d.ts for its shape. */
export function loadKnowledge() {
  return knowledge;
}
