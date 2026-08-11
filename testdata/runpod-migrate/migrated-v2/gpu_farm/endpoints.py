"""Serverless endpoint provisioning. Migrated from REST v1 to REST v2."""

import os

import requests

BASE = "https://api.runpod.io/v2"
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"})

CONTAINER = {
    "image": "runpod/worker-sdxl:latest",
    "disk": 20,
    "env": {"MODEL_ID": "stabilityai/sdxl-turbo"},
    "args": "python -u handler.py",
}


def upsert_template(name: str) -> dict:
    """Templates are still useful as a config preset — but v2 endpoints do not
    reference one by ID, so we return the whole template and spread it later."""
    body = {**CONTAINER, "name": name, "serverless": True, "public": False, "category": "NVIDIA"}
    resp = SESSION.post(f"{BASE}/templates", json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _pool_for(gpu_type_id: str) -> str:
    """v1 named individual GPU types; v2 serverless takes GPU *pool* IDs."""
    resp = SESSION.get(f"{BASE}/catalog/gpus", params={"include": "AVAILABILITY"}, timeout=30)
    resp.raise_for_status()
    for gpu in resp.json()["gpus"]:
        if gpu["id"] == gpu_type_id:
            if not gpu["pool"]:
                raise ValueError(f"{gpu_type_id} is not in any serverless pool")
            return gpu["pool"]
    raise ValueError(f"unknown GPU type {gpu_type_id}")


def deploy_endpoint(name: str, template: dict) -> dict:
    container = {k: template[k] for k in ("image", "disk", "env", "args") if template.get(k)}
    body = {
        **container,
        "name": name,
        "type": "QUEUE",
        "gpu": {"pools": [_pool_for("NVIDIA GeForce RTX 4090")], "count": 1},
        "workers": {"min": 0, "max": 5, "idleTimeout": 10},
        "scaling": {"type": "QUEUE_DELAY", "queueDelay": 4},
        "timeout": 600000,
        "flashboot": "FLASHBOOT",
        "dataCenterIds": ["US-KS-2"],
    }
    resp = SESSION.post(f"{BASE}/serverless", json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()


def scale_endpoint(endpoint_id: str, workers_max: int) -> dict:
    resp = SESSION.patch(
        f"{BASE}/serverless/{endpoint_id}",
        json={"workers": {"max": workers_max}},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def endpoint_run_url(endpoint: dict) -> str:
    # v2 hands us the job URLs, so we no longer build them by hand.
    return endpoint["requestUrls"]["run"]


def worker_health(endpoint_id: str) -> dict:
    """New in v2: per-worker status plus a stale-config flag during rollouts."""
    resp = SESSION.get(f"{BASE}/serverless/{endpoint_id}/workers", timeout=30)
    resp.raise_for_status()
    body = resp.json()
    return {
        "summary": body["summary"],
        "stale": [w["id"] for w in body["workers"] if w["isStale"]],
    }


def monthly_spend() -> float:
    # v1 /billing/endpoints meant *serverless*; in v2 that is /billing/serverless
    # (v2 /billing/endpoints is Runpod public endpoints, a different product).
    resp = SESSION.get(
        f"{BASE}/billing/serverless",
        params={"bucketSize": "month", "lastN": 1},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["metadata"]["totals"]["totalAmount"]
