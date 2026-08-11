# rp-migrate: ignore file
#
# File-scope `ignore`. Every hit below is a false positive: these are this
# service's own route names, not calls to the Runpod API. The `ignore` marker
# only worked at line scope until the two markers were tracked separately.

ROUTES = [
    "/pods",
    "/pods/{pod_id}/stop",
    "/endpoints",
    "/networkvolumes",
]

CACHE_DIR = "./data/pods"
