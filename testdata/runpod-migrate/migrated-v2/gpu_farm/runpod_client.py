"""Thin Runpod client. Migrated from REST v1 to REST v2.

Set RUNPOD_API_V1=1 to fall back to the old v1 code path during the rollout.
"""

import os
import time

import requests

USE_V1 = os.environ.get("RUNPOD_API_V1", "").lower() in ("1", "true", "yes")

V1_BASE = "https://rest.runpod.io/v1"  # rp-migrate: keep-v1
V2_BASE = "https://api.runpod.io/v2"
BASE = V1_BASE if USE_V1 else V2_BASE

API_KEY = os.environ["RUNPOD_API_KEY"]

SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {API_KEY}"})

# v2 takes a single GPU type, so the fallback list moved into our code.
GPU_PREFERENCE = [
    "NVIDIA GeForce RTX 4090",
    "NVIDIA RTX A5000",
    "NVIDIA L40S",
]
DATA_CENTERS = ["US-KS-2", "US-IL-1"]


def _available_gpus(count: int = 1) -> dict[str, str]:
    """Map GPU id -> availability level (NONE/LOW/MEDIUM/HIGH) for our DCs.

    v1 had no catalog: `gpuTypePriority: availability` made this decision
    server-side. v2 exposes it, so we can see the stock level before renting.
    """
    resp = SESSION.get(
        f"{V2_BASE}/catalog/gpus",
        params={"include": "AVAILABILITY", "product": "POD", "count": count, "cloud": "SECURE"},
        timeout=30,
    )
    resp.raise_for_status()
    levels = {}
    for gpu in resp.json()["gpus"]:
        in_our_dcs = [
            dc["availability"]
            for dc in gpu.get("dataCenters", [])
            if dc["id"] in DATA_CENTERS
        ]
        best = "NONE"
        for level in ("HIGH", "MEDIUM", "LOW"):
            if level in in_our_dcs:
                best = level
                break
        levels[gpu["id"]] = best
    return levels


def create_render_pod(name: str, image: str, volume_id: str | None = None) -> dict:
    if USE_V1:
        return _create_render_pod_v1(name, image, volume_id)

    body = {
        "name": name,
        "image": image,
        "cloud": "SECURE",
        "gpu": {"id": GPU_PREFERENCE[0], "count": 1},
        "disk": 60,
        "ports": ["8888/http", "22/tcp"],
        "env": {"RENDER_MODE": "batch"},
        "args": "bash -lc 'python /app/render.py'",
        "dataCenterIds": DATA_CENTERS,
    }
    if volume_id:
        # v2 requires an explicit mount path — there is no /workspace default.
        body["mounts"] = {"network": [{"volumeId": volume_id, "path": "/workspace"}]}
    else:
        body["mounts"] = {"persistent": {"size": 100, "path": "/workspace"}}

    # v1's gpuTypePriority=availability fallback is now ours to implement.
    stock = _available_gpus()
    ordered = sorted(
        GPU_PREFERENCE,
        key=lambda g: {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "NONE": 3}[stock.get(g, "NONE")],
    )
    last_error = None
    for gpu_id in ordered:
        body["gpu"] = {"id": gpu_id, "count": 1}
        resp = SESSION.post(f"{V2_BASE}/pods", json=body, timeout=60)
        if resp.status_code == 201:
            return resp.json()
        last_error = f"{gpu_id}: {resp.status_code} {resp.text[:300]}"
    raise RuntimeError(f"no GPU from {ordered} could be rented — last error: {last_error}")


def _create_render_pod_v1(name: str, image: str, volume_id: str | None) -> dict:
    # rp-migrate: keep-v1 start  (rollback path, delete with the RUNPOD_API_V1 flag)
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
        "dataCenterIds": DATA_CENTERS,
        "interruptible": False,
    }
    if volume_id:
        body["networkVolumeId"] = volume_id
        body.pop("volumeInGb", None)
    resp = SESSION.post(f"{V1_BASE}/pods", json=body, timeout=60)
    resp.raise_for_status()
    return resp.json()
    # rp-migrate: keep-v1 end


def wait_until_running(pod_id: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        pod = SESSION.get(f"{BASE}/pods/{pod_id}", timeout=30).json()
        if USE_V1:
            if pod["desiredStatus"] == "RUNNING" and pod.get("publicIp"):
                return pod
        else:
            # v2 reports real lifecycle states, so we can fail fast instead of
            # waiting out the timeout on a pod that will never come up.
            if pod["status"] == "RUNNING":
                return pod
            if pod["status"] == "ERROR":
                raise RuntimeError(f"pod {pod_id} entered ERROR")
        time.sleep(10)
    raise TimeoutError(f"pod {pod_id} never reached RUNNING")


def list_render_pods() -> list[dict]:
    if USE_V1:
        # rp-migrate: keep-v1 start
        resp = SESSION.get(
            f"{V1_BASE}/pods",
            params={"computeType": "GPU", "desiredStatus": "RUNNING"},
            timeout=30,
        )
        resp.raise_for_status()
        pods = resp.json()
        # rp-migrate: keep-v1 end
    else:
        resp = SESSION.get(f"{V2_BASE}/pods", timeout=30)
        resp.raise_for_status()
        # v2 wraps the list and has no server-side filters — filter here.
        pods = [p for p in resp.json()["pods"] if p["status"] == "RUNNING" and p.get("gpu")]
    return [p for p in pods if p["name"].startswith("render-")]


def hourly_cost() -> float:
    key = "costPerHr" if USE_V1 else "cost"
    return sum(p[key] for p in list_render_pods())


def _action(pod_id: str, action: str) -> None:
    if USE_V1:
        SESSION.post(f"{V1_BASE}/pods/{pod_id}/{action}", timeout=30).raise_for_status()  # rp-migrate: keep-v1
    else:
        SESSION.post(
            f"{V2_BASE}/pods/{pod_id}/action", json={"action": action}, timeout=30
        ).raise_for_status()


def stop_pod(pod_id: str) -> None:
    _action(pod_id, "stop")


def resume_pod(pod_id: str) -> None:
    _action(pod_id, "start" if not USE_V1 else "start")


def terminate_pod(pod_id: str) -> None:
    SESSION.delete(f"{BASE}/pods/{pod_id}", timeout=30).raise_for_status()


def ensure_volume(name: str, size_gb: int, data_center: str) -> dict:
    if USE_V1:
        # rp-migrate: keep-v1 start
        for vol in SESSION.get(f"{V1_BASE}/networkvolumes", timeout=30).json():
            if vol["name"] == name:
                return vol
        resp = SESSION.post(
            f"{V1_BASE}/networkvolumes",
            json={"name": name, "size": size_gb, "dataCenterId": data_center},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()
        # rp-migrate: keep-v1 end

    listing = SESSION.get(f"{V2_BASE}/network-volumes", timeout=30)
    listing.raise_for_status()
    for vol in listing.json()["networkVolumes"]:
        if vol["name"] == name:
            return vol
    resp = SESSION.post(
        f"{V2_BASE}/network-volumes",
        json={"name": name, "size": size_gb, "dataCenter": data_center},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()
