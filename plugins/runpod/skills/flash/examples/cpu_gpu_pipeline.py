"""Two stages on different hardware, plus parallel fan-out.

    rp flash dev cpu_gpu_pipeline.py --once

The CPU stage cleans rows with pandas; the GPU stage scores them with
torch. .spawn() submits jobs without waiting, so several batches run on
separate workers at once.
"""

import runpod

app = runpod.App("pipeline")


@app.queue(cpu="cpu5c-4-8", dependencies=["pandas"])
def preprocess(rows: list[dict]) -> list[list[float]]:
    import pandas as pd

    df = pd.DataFrame(rows).dropna()
    return df.astype(float).values.tolist()


@app.queue(gpu="AMPERE_80", workers=(0, 5))
def score(matrix: list[list[float]]) -> list[float]:
    import torch

    return torch.tensor(matrix, dtype=torch.float32, device="cuda").mean(dim=1).tolist()


@runpod.local_entrypoint
def main():
    rows = [{"a": 1, "b": 3}, {"a": 2, "b": None}, {"a": 5, "b": 7}]
    print("one batch:", score.remote(preprocess.remote(rows)))

    batches = [[{"a": i, "b": i + 1}] for i in range(4)]
    pre = [preprocess.spawn(b) for b in batches]
    jobs = [score.spawn(j.result()) for j in pre]
    print("fan-out:", [job.result() for job in jobs])
