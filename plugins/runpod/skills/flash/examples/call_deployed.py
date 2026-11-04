"""Call deployed resources from any Python code (no rp flash dev needed).

    python call_deployed.py

Assumes `rp flash deploy queue_gpu.py` and `rp flash deploy
api_model_service.py` have run. Set ENDPOINT_ID to call any queue
endpoint by id, including ones the SDK did not create.
"""

import os

import runpod

# a resource in a deployed app, by app and resource name (default environment)
gpu_sum = runpod.Queue(app="gpu-sum", name="gpu_sum")
print(gpu_sum.remote(values=[1.0, 2.0, 3.0]))   # keyword arguments only

job = gpu_sum.spawn(values=[4.0, 5.0])
print(job.id, job.result())

text_gen = runpod.Api(app="text-gen", name="TextGen")
print(text_gen.post("/generate", {"prompt": "Hello"}))

# any queue endpoint by id
endpoint_id = os.environ.get("ENDPOINT_ID")
if endpoint_id:
    ep = runpod.Endpoint(endpoint_id)
    print(ep.run_sync({"prompt": "hello"}, timeout=120))   # sent as {"input": {...}}
