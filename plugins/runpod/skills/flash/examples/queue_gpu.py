"""A GPU function behind an autoscaling queue endpoint.

    rp flash dev queue_gpu.py --once     # run main() once against a temporary endpoint
    rp flash deploy queue_gpu.py         # persistent endpoint in app "gpu-sum"

Any of the listed GPUs is acceptable, and a max of 5 workers lets the
platform switch between them by supply.
"""

import runpod

app = runpod.App("gpu-sum")


@app.queue(gpu=["4090", "L4", "A5000"], workers=(0, 5), dependencies=["numpy"])
def gpu_sum(values: list[float]) -> dict:
    # torch ships on the built-in GPU image; import heavy packages inside the function
    import torch

    t = torch.tensor(values, device="cuda")
    return {"gpu": torch.cuda.get_device_name(0), "sum": t.sum().item()}


@runpod.local_entrypoint
def main():
    out = gpu_sum.remote([1.0, 2.0, 3.0])
    print(out)
    assert out["sum"] == 6.0, out
