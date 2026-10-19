"""Bounded readiness and real-entrypoint smoke check for the HTTP example."""

import json
import time
from urllib.request import Request, urlopen


def wait_for_ready(url, attempts=30):
    for attempt in range(attempts):
        try:
            with urlopen(url, timeout=2) as response:
                assert json.load(response) == {"status": "ready"}
            return
        except OSError:
            # Includes URLError, ConnectionResetError and RemoteDisconnected.
            if attempt == attempts - 1:
                raise
            time.sleep(1)


if __name__ == "__main__":
    wait_for_ready("http://127.0.0.1:8080/ping")
    request = Request("http://127.0.0.1:8080/analyze?source=smoke",
                      data=b'{"text":"A a B"}',
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        assert json.load(response) == {"words": 3, "counts": {"a": 2, "b": 1}}
