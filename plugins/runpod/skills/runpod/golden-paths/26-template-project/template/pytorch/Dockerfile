# Supply a verified compatible official Runpod PyTorch image by tag/digest.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ENV PYTHONUNBUFFERED=1
WORKDIR /opt/template-probe
# PyTorch stays in the base; no reinstall or virtualenv copy to /workspace.
COPY verify.py ./
# Retain the selected Runpod base's service initialization and long-lived command.
# Run the finite probe explicitly with docker exec / SSH after startup; a Pod's
# default command must not exit after the check and enter a restart loop.
CMD ["/start.sh"]
