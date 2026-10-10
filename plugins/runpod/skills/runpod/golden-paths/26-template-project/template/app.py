"""HTTP text statistics app; /ping is ready when this dependency-free app listens."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from workload import analyze


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/ping":
            self.reply(200, {"status": "ready"})
        else:
            self.reply(404, {"error": "use POST /analyze"})

    def do_POST(self):
        if self.path != "/analyze":
            self.reply(404, {"error": "route not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 400_000:
                raise ValueError("provide a JSON body of at most 400000 bytes")
            self.connection.settimeout(10)
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("incomplete request body")
            result = analyze(json.loads(body))
        except (ValueError, UnicodeError, TimeoutError) as exc:
            self.reply(400, {"error": str(exc)})
            return
        self.reply(200, result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"text statistics ready on 0.0.0.0:{port}", flush=True)
    server.serve_forever()
