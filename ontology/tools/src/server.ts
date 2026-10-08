// Serves the concept graph over HTTP: a read-only JSON API, and the graph page
// at / when one is given.
//
//   node src/server.ts [--port 8787]
//
//   GET /api                          routes and build metadata
//   GET /api/concepts                 every concept: id, name, kind, product, summary
//   GET /api/concepts/<ref>           one concept by id, name or alias, with its rules
//   GET /api/concepts/<ref>/neighbors the concepts it links to and from
//   GET /api/search?q=<text>&limit=N  rules ranked by full-text match
//   GET /api/tree?root=<ref>          the concept hierarchy with linked guides

import { existsSync, readFileSync } from "node:fs";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import { DEFAULT_GRAPH_PATH } from "./build-graph.ts";
import { DEFAULT_DB_PATH } from "./build-sqlite.ts";
import { getConcept, neighbors, openOntology, search, tree } from "./query.ts";

export interface Reply {
  status: number;
  body: unknown;
}

const ROUTES = [
  "GET /api/concepts",
  "GET /api/concepts/<id|name|alias>",
  "GET /api/concepts/<id|name|alias>/neighbors",
  "GET /api/search?q=<text>&limit=<1-50>",
  "GET /api/tree?root=<id|name|alias>",
];

const notFound = (message: string): Reply => ({ status: 404, body: { error: message } });

/** Answers one API request. Pure apart from reading the database. */
export function route(db: DatabaseSync, url: URL): Reply {
  const parts = url.pathname.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] !== "api") return notFound(`no route for ${url.pathname}`);
  const [, resource, ref, sub, ...rest] = parts;
  if (rest.length) return notFound(`no route for ${url.pathname}`);

  if (!resource) {
    const meta = Object.fromEntries(
      db
        .prepare("SELECT key, value FROM meta")
        .all()
        .map((row) => [row.key, row.value]),
    );
    return { status: 200, body: { routes: ROUTES, meta } };
  }

  if (resource === "concepts") {
    if (!ref) {
      const rows = db.prepare("SELECT id, name, kind, product, summary FROM concepts ORDER BY id").all();
      return { status: 200, body: rows.map((row) => ({ ...row })) };
    }
    const concept = getConcept(db, ref);
    if (!concept) return notFound(`no concept matches "${ref}"`);
    if (!sub) return { status: 200, body: concept };
    if (sub === "neighbors") return { status: 200, body: neighbors(db, concept.id) };
    return notFound(`no route for ${url.pathname}`);
  }

  if (resource === "search" && !ref) {
    const query = url.searchParams.get("q")?.trim();
    if (!query) return { status: 400, body: { error: "q is required" } };
    const limit = Math.min(Math.max(Number(url.searchParams.get("limit")) || 10, 1), 50);
    return { status: 200, body: search(db, query, { limit }) };
  }

  if (resource === "tree" && !ref) {
    const rootRef = url.searchParams.get("root")?.trim();
    const root = rootRef ? getConcept(db, rootRef)?.id : undefined;
    if (rootRef && !root) return notFound(`no concept matches "${rootRef}"`);
    return { status: 200, body: tree(db, root) };
  }

  return notFound(`no route for ${url.pathname}`);
}

/** A Node request listener for the API, and for the graph page at / when given. */
export function listener(db: DatabaseSync, graphHtml?: string) {
  return (req: IncomingMessage, res: ServerResponse) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.writeHead(405, { allow: "GET, HEAD" }).end();
      return;
    }
    if (graphHtml && (url.pathname === "/" || url.pathname === "/index.html")) {
      res.writeHead(200, { "content-type": "text/html; charset=utf-8" }).end(graphHtml);
      return;
    }
    let reply: Reply;
    try {
      reply = route(db, url);
    } catch (error) {
      // FTS5 rejects some query syntax; report it as a bad request, not a crash.
      reply = { status: 400, body: { error: (error as Error).message } };
    }
    res
      .writeHead(reply.status, {
        "content-type": "application/json; charset=utf-8",
        "access-control-allow-origin": "*",
        "cache-control": reply.status === 200 ? "public, max-age=300" : "no-store",
      })
      .end(JSON.stringify(reply.body, null, 2));
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const portAt = process.argv.indexOf("--port");
  const port = portAt >= 0 ? Number(process.argv[portAt + 1]) : 8787;
  if (!existsSync(DEFAULT_DB_PATH)) {
    console.error(`no database at ${DEFAULT_DB_PATH}; run pnpm build:sqlite first`);
    process.exit(1);
  }
  const graph = existsSync(DEFAULT_GRAPH_PATH) ? readFileSync(DEFAULT_GRAPH_PATH, "utf8") : undefined;
  createServer(listener(openOntology(DEFAULT_DB_PATH), graph)).listen(port, () => {
    console.log(`http://localhost:${port}/${graph ? "" : " (API only; run pnpm build:graph for the page)"}`);
  });
}
