"""Check the selected image's real torch/device and preserve existing user data."""

import argparse
import json
from pathlib import Path

import torch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("output exists; choose a new path to preserve the previous result")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA is not available; GPU validation failed, no CPU fallback")
    data = torch.arange(9, dtype=torch.float32, device=args.device).reshape(3, 3)
    result = (data @ data.T).cpu().tolist()
    expected = [[5.0, 14.0, 23.0], [14.0, 50.0, 86.0], [23.0, 86.0, 149.0]]
    if result != expected:
        raise SystemExit(f"unexpected matrix result: {result}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {"torch": torch.__version__, "torch_path": torch.__file__,
              "device": args.device, "result": result}
    # Exclusive creation also protects a result created since the existence check.
    # A result is complete only after this process exits successfully.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
