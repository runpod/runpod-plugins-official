"""HTTP text statistics app; /ping is ready when this dependency-free app listens."""

import json
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

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
        if urlsplit(self.path).path == "/ping":
            self.reply(200, {"status": "ready"})
        else:
            self.reply(404, {"error": "use POST /analyze"})

    def do_POST(self):
        if urlsplit(self.path).path != "/analyze":
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
        except (ValueError, UnicodeError, TimeoutError, RecursionError) as exc:
            self.reply(400, {"error": str(exc)})
            return
        self.reply(200, result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    with ThreadingHTTPServer(("0.0.0.0", port), Handler) as server:
        server.daemon_threads = False  # Wait for in-flight requests on shutdown.

        def stop(signum, frame):
            # shutdown() must run outside the serve_forever() thread.
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, stop)
        print(f"text statistics ready on 0.0.0.0:{server.server_port}", flush=True)
        server.serve_forever()
