# The only real source file in this corpus. Deliberately already on v2.
BASE = "https://api.runpod.io/v2"


def list_pods(session):
    return session.get(f"{BASE}/pods").json()["pods"]
