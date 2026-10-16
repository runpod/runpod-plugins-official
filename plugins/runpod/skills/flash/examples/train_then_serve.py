"""Train on a Pod, then serve the result from a queue endpoint.

    rp flash dev train_then_serve.py --once

train() is a task: one Pod per call, terminated when it returns. predict()
is a queue endpoint. The weights are small, so the task returns them as
JSON and main() passes them on. For checkpoints too big for a 10 MB
payload, share a NetworkVolume instead (golden path 07 shows the handoff).
"""

import runpod

app = runpod.App("train-serve")


@app.task(gpu="4090")
def train(steps: int = 200) -> dict:
    import torch

    x = torch.randn(1024, 1, device="cuda")
    y = 3 * x + 1
    model = torch.nn.Linear(1, 1).cuda()
    opt = torch.optim.SGD(model.parameters(), lr=0.05)
    for _ in range(steps):
        loss = ((model(x) - y) ** 2).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
    return {"weight": model.weight.item(), "bias": model.bias.item()}


@app.queue(cpu="cpu3c-1-2")
def predict(params: dict, x: float) -> float:
    # whole-number floats can arrive as ints, so cast before use
    return float(params["weight"]) * float(x) + float(params["bias"])


@runpod.local_entrypoint
def main():
    params = train.remote()
    print("trained:", params)
    y = predict.remote(params, 2.0)
    print(f"f(2.0) = {y:.2f}")
    assert abs(y - 7.0) < 0.5, y
