"""Serverless endpoint provisioning (REST v1)."""

import os

import requests

BASE = "https://rest.runpod.io/v1"
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"})


def upsert_template(name: str, image: str) -> str:
    body = {
        "name": name,
        "imageName": image,
        "containerDiskInGb": 20,
        "volumeInGb": 0,
        "isServerless": True,
        "isPublic": False,
        "env": {"MODEL_ID": "stabilityai/sdxl-turbo"},
        "dockerStartCmd": ["python", "-u", "handler.py"],
    }
    resp = SESSION.post(f"{BASE}/templates", json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()["id"]


def deploy_endpoint(name: str, template_id: str) -> dict:
    body = {
        "name": name,
        "templateId": template_id,
        "computeType": "GPU",
        "gpuTypeIds": ["NVIDIA GeForce RTX 4090"],
        "gpuCount": 1,
        "workersMin": 0,
        "workersMax": 5,
        "idleTimeout": 10,
        "scalerType": "QUEUE_DELAY",
        "scalerValue": 4,
        "executionTimeoutMs": 600000,
        "flashboot": True,
        "dataCenterIds": ["US-KS-2"],
    }
    resp = SESSION.post(f"{BASE}/endpoints", json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()


def scale_endpoint(endpoint_id: str, workers_max: int) -> dict:
    resp = SESSION.post(
        f"{BASE}/endpoints/{endpoint_id}/update",
        json={"workersMax": workers_max},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def endpoint_run_url(endpoint_id: str) -> str:
    # We build the job URL by hand because v1 doesn't return it.
    return f"https://api.runpod.ai/v2/{endpoint_id}/run"


def monthly_spend() -> float:
    resp = SESSION.get(
        f"{BASE}/billing/endpoints",
        params={"bucketSize": "month", "grouping": "endpointId"},
        timeout=30,
    )
    resp.raise_for_status()
    return sum(r["amount"] for r in resp.json())
