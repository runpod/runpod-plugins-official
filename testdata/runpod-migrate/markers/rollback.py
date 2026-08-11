"""Genuine v1 code retained on purpose behind a rollback flag.

Contrast with false_positive.py: this really is legacy, so the report must
list it as kept on purpose rather than as a false positive.
"""

import os

import requests

USE_V1 = os.environ.get("RUNPOD_API_V1", "").lower() in ("1", "true", "yes")

V1_BASE = "https://rest.runpod.io/v1"  # rp-migrate: keep-v1
V2_BASE = "https://api.runpod.io/v2"
BASE = V1_BASE if USE_V1 else V2_BASE


def stop_pod(pod_id: str):
    if USE_V1:
        # rp-migrate: keep-v1 start
        return requests.post(f"{V1_BASE}/pods/{pod_id}/stop", timeout=30)
        # rp-migrate: keep-v1 end
    return requests.post(
        f"{V2_BASE}/pods/{pod_id}/action", json={"action": "stop"}, timeout=30
    )


def whoami():
    """No REST v2 equivalent, so this stays on GraphQL permanently."""
    query = "query { myself { id email clientBalance } }"  # rp-migrate: keep-v1
    return requests.post(
        "https://api.runpod.io/graphql",  # rp-migrate: keep-v1
        json={"query": query},
        timeout=30,
    )
