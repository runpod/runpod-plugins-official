"""Thin Runpod REST v1 client used by the batch renderer.

Written mid-2025 against https://rest.runpod.io/v1.
"""

import os
import time

import requests

BASE = os.environ.get("RUNPOD_API_BASE", "https://rest.runpod.io/v1")
API_KEY = os.environ["RUNPOD_API_KEY"]

SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {API_KEY}"})

# We rent whatever is cheapest that fits the model; the API walks this list.
GPU_PREFERENCE = [
    "NVIDIA GeForce RTX 4090",
    "NVIDIA RTX A5000",
    "NVIDIA L40S",
]


def create_render_pod(name: str, image: str, volume_id: str | None = None) -> dict:
    body = {
        "name": name,
        "imageName": image,
        "cloudType": "SECURE",
        "computeType": "GPU",
        "gpuTypeIds": GPU_PREFERENCE,
        "gpuTypePriority": "availability",
        "gpuCount": 1,
        "containerDiskInGb": 60,
        "volumeInGb": 100,
        "volumeMountPath": "/workspace",
        "ports": ["8888/http", "22/tcp"],
        "env": {"RENDER_MODE": "batch"},
        "dockerStartCmd": ["bash", "-lc", "python /app/render.py"],
        "minRAMPerGPU": 16,
        "minVCPUPerGPU": 4,
        "countryCodes": ["US", "CA"],
        "dataCenterIds": ["US-KS-2", "US-IL-1"],
        "interruptible": False,
    }
    if volume_id:
        body["networkVolumeId"] = volume_id
        body.pop("volumeInGb", None)

    resp = SESSION.post(f"{BASE}/pods", json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()


def wait_until_running(pod_id: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        pod = SESSION.get(f"{BASE}/pods/{pod_id}", timeout=30).json()
        if pod["desiredStatus"] == "RUNNING" and pod.get("publicIp"):
            return pod
        time.sleep(10)
    raise TimeoutError(f"pod {pod_id} never reached RUNNING")


def list_render_pods() -> list[dict]:
    resp = SESSION.get(f"{BASE}/pods", params={"computeType": "GPU", "desiredStatus": "RUNNING"}, timeout=30)
    resp.raise_for_status()
    # v1 returns a bare array
    return [p for p in resp.json() if p["name"].startswith("render-")]


def hourly_cost() -> float:
    return sum(p["costPerHr"] for p in list_render_pods())


def stop_pod(pod_id: str) -> None:
    SESSION.post(f"{BASE}/pods/{pod_id}/stop", timeout=30).raise_for_status()


def resume_pod(pod_id: str) -> None:
    SESSION.post(f"{BASE}/pods/{pod_id}/start", timeout=30).raise_for_status()


def terminate_pod(pod_id: str) -> None:
    SESSION.delete(f"{BASE}/pods/{pod_id}", timeout=30).raise_for_status()


def ensure_volume(name: str, size_gb: int, data_center: str) -> dict:
    for vol in SESSION.get(f"{BASE}/networkvolumes", timeout=30).json():
        if vol["name"] == name:
            return vol
    resp = SESSION.post(
        f"{BASE}/networkvolumes",
        json={"name": name, "size": size_gb, "dataCenterId": data_center},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
