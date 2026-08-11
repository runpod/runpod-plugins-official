"""Correct v2 code that trips the scanner's heuristics anyway.

Nothing here is legacy. Every marker is `ignore`, and the report must say
"false positive" rather than claiming v1 was deliberately retained.
"""

import os

import requests

BASE = "https://api.runpod.io/v2"
API_KEY = os.environ["RUNPOD_API_KEY"]

# A local directory that happens to be spelled like the v1 collection path.
METRICS_DIR = "./data/pods"  # rp-migrate: ignore (local directory, not an API path)


def stale_config_warning(configured: str) -> bool:
    """Detect a config file left pointing at the retired v1 host."""
    return "rest.runpod.io/v1" in configured  # rp-migrate: ignore (detects a stale URL)


def list_pods():
    # The v2 base lives in BASE, which the scanner cannot see from this line.
    resp = requests.get(
        f"{BASE}/pods",  # rp-migrate: ignore (joined to the v2 base above)
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["pods"]


# rp-migrate: ignore start
# This app exposes its own HTTP routes that mirror the Runpod resource names.
LOCAL_ROUTES = {
    "list": "/pods",
    "stop": "/pods/{pod_id}/stop",
    "endpoints": "/endpoints",
}
# rp-migrate: ignore end
