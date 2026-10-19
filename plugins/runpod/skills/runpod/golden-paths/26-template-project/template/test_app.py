"""Meaningful adapter tests: useful output, invalid input and request isolation."""

import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import RemoteDisconnected
from http.server import ThreadingHTTPServer
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import Handler
from check_http import wait_for_ready
from handler import handler


class WorkloadTests(unittest.TestCase):
    def test_readiness_retries_transport_failures_and_remains_bounded(self):
        failures = [ConnectionResetError("reset"), RemoteDisconnected("closed")]
        with patch("check_http.time.sleep"), patch("check_http.urlopen") as open_url:
            open_url.side_effect = failures + [BytesIO(b'{"status":"ready"}')]
            wait_for_ready("http://example.invalid/ping", attempts=3)
            self.assertEqual(open_url.call_count, 3)
            open_url.side_effect = ConnectionResetError("still resetting")
            with self.assertRaisesRegex(ConnectionResetError, "still resetting"):
                wait_for_ready("http://example.invalid/ping", attempts=2)
            self.assertEqual(open_url.call_count, 5)
            open_url.side_effect = [BytesIO(b'{"status":"wrong"}')]
            with self.assertRaises(AssertionError):
                wait_for_ready("http://example.invalid/ping", attempts=2)
            self.assertEqual(open_url.call_count, 6)

    def test_queue_and_failure_recovery(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            handler({"input": {"text": ""}})
        self.assertEqual(
            handler({"input": {"text": "Runpod runpod works"}}),
            {"words": 3, "counts": {"runpod": 2, "works": 1}},
        )
        with self.assertRaises(ValueError):
            handler({"input": {"text": "x" * 100_001}})
        with self.assertRaises(ValueError):
            handler({})

    def test_http_output_readiness_errors_and_isolation(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post(payload):
            request = Request(
                base + "/analyze?source=test",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request, timeout=5) as response:
                return json.load(response)

        try:
            with urlopen(base + "/ping?source=test", timeout=5) as response:
                self.assertEqual(json.load(response), {"status": "ready"})
            with self.assertRaises(HTTPError) as failure:
                post({"text": ""})
            self.assertEqual(failure.exception.code, 400)
            failure.exception.close()
            request = Request(base + "/analyze", data=b"[" * 2000 + b"]" * 2000,
                              headers={"Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as nested_failure:
                urlopen(request, timeout=5)
            self.assertEqual(nested_failure.exception.code, 400)
            nested_failure.exception.close()
            self.assertEqual(post({"text": "A a B"}), {"words": 3, "counts": {"a": 2, "b": 1}})
            inputs = [{"text": str(n)} for n in range(20)]
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(post, inputs))
            self.assertEqual(results, [{"words": 1, "counts": {str(n): 1}} for n in range(20)])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
