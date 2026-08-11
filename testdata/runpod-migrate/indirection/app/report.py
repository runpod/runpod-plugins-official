from .client import create

def spend(pods):
    return sum(p["costPerHr"] for p in pods)

def is_up(pod):
    return pod["desiredStatus"] == "RUNNING"
