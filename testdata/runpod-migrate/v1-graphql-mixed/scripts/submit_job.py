"""Submit inference jobs to our serverless endpoint.

NOTE: this talks to the serverless *job* API, not the control plane.
"""

import os
import time

import requests

ENDPOINT_ID = os.environ["RENDER_ENDPOINT_ID"]
KEY = os.environ["RUNPOD_API_KEY"]
HEADERS = {"Authorization": f"Bearer {KEY}"}


def submit(prompt: str) -> str:
    r = requests.post(
        f"https://api.runpod.ai/v2/{ENDPOINT_ID}/run",
        json={"input": {"prompt": prompt}},
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def wait(job_id: str) -> dict:
    while True:
        r = requests.get(
            f"https://api.runpod.ai/v2/{ENDPOINT_ID}/status/{job_id}",
            headers=HEADERS,
            timeout=30,
        )
        body = r.json()
        if body["status"] in ("COMPLETED", "FAILED"):
            return body
        time.sleep(2)
