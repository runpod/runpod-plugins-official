"""Volume housekeeping. An agent wrote this last month against REST v2."""

import os

import requests

BASE = "https://api.runpod.io/v2"
HEADERS = {"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"}


def list_volumes():
    r = requests.get(f"{BASE}/network-volumes", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()["networkVolumes"]


def grow(volume_id: str, size_gb: int):
    r = requests.patch(
        f"{BASE}/network-volumes/{volume_id}",
        json={"size": size_gb},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
