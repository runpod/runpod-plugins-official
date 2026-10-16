"""Train on a Pod, then serve the checkpoint from a queue endpoint.

    rp flash dev train_then_serve.py --once

train() is a task: one Pod per call, terminated when it returns. predict()
is a queue endpoint. Both mount the same network volume, so the endpoint
reads the checkpoint the task wrote. The volume outlives the session and
keeps billing; delete it when you are done.
"""

import runpod

app = runpod.App("train-serve")

ckpts = runpod.NetworkVolume("train-serve-ckpts", size=10)


@app.task(gpu="4090", mounts={"/ckpts": ckpts})
def train(steps: int = 200) -> str:
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
    path = "/ckpts/linear.pt"                # literal mount path (SKILL gotcha 14)
    torch.save(model.state_dict(), path)
    return "linear.pt"


@app.queue(cpu="cpu3c-2-4", mounts={"/runpod-volume": ckpts}, dependencies=["torch"])
def predict(name: str, x: float) -> float:
    import torch

    model = torch.nn.Linear(1, 1)
    model.load_state_dict(torch.load(f"/runpod-volume/{name}", map_location="cpu"))
    return model(torch.tensor([[x]])).item()


@runpod.local_entrypoint
def main():
    name = train.remote()
    y = predict.remote(name, 2.0)
    print(f"f(2.0) = {y:.2f}")
    assert abs(y - 7.0) < 0.5, y
