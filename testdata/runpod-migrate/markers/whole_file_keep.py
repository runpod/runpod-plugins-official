# rp-migrate: keep-v1 file
#
# File-scope `keep-v1`. This module is the frozen v1 client kept for the
# rollback window; it is real legacy code and must be reported as retained on
# purpose, not as a false positive.

import requests

V1_BASE = "https://rest.runpod.io/v1"


def list_pods():
    return requests.get(f"{V1_BASE}/pods", timeout=30).json()


def stop_pod(pod_id: str):
    return requests.post(f"{V1_BASE}/pods/{pod_id}/stop", timeout=30)
