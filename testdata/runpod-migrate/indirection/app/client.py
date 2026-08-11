import os, yaml, requests

CFG = yaml.safe_load(open("config/settings.yaml"))["runpod"]

def _url(*parts):
    return "/".join([CFG["base_url"], *parts])

def create(spec):
    return requests.post(_url("pods"), json=spec).json()

def halt(pod_id):
    return requests.post(_url("pods", pod_id, "stop")).json()
