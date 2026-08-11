import requests
BASE = "https://api.runpod.io/v2"
S = requests.Session()

def list_pods():
    return S.get(f"{BASE}/pods").json()["pods"]          # fully migrated v2 code

def create(spec):
    spec = {"image": spec["img"],  # was imageName
            "disk": spec["gb"]}    # was containerDiskInGb
    return S.post(f"{BASE}/pods", json=spec).json()

def spend():
    r = S.get(f"{BASE}/billing/serverless", params={"lastN": 1}).json()
    return r["metadata"]["totals"]["totalAmount"]
