# Not the user's source. If the scanner reports this file, its traversal filter is
# broken and every finding in a real repo is inflated by however many copies exist.
BASE = "https://rest.runpod.io/v1"
body = {"imageName": "org/img:tag", "containerDiskInGb": 60, "gpuTypeIds": ["A"]}
r = requests.post(f"{BASE}/pods", json=body)
vols = requests.get(f"{BASE}/networkvolumes").json()
