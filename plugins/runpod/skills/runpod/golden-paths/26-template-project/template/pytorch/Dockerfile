# Supply a verified compatible official Runpod PyTorch image by tag/digest.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ENV PYTHONUNBUFFERED=1
WORKDIR /opt/template-probe
# PyTorch stays in the base; no reinstall or virtualenv copy to /workspace.
COPY verify.py ./
# This is a GPU batch/probe Pod. It does not promise SSH or Jupyter.
CMD ["python", "verify.py", "--device", "cuda", "--output", "/workspace/probe.json"]
