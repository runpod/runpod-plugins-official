#!/usr/bin/env bash
# Minimal pod startup that reproduces what runpod/pytorch's /start.sh does for SSH,
# then runs the workload. A compatible Runpod base may already provide SSH; inspect
# and preserve its startup hooks. This is the "from a non-Runpod base" pattern: without it, a pod
# that promises SSH would not provide that interface. App-only Pods can omit SSH.
set -e

# 1. SSH: install the injected public key, generate host keys, start sshd.
mkdir -p ~/.ssh && chmod 700 ~/.ssh
if [ -n "$PUBLIC_KEY" ]; then
  echo "$PUBLIC_KEY" >> ~/.ssh/authorized_keys
  chmod 600 ~/.ssh/authorized_keys
fi
ssh-keygen -A
service ssh start

# 2. Workload: a tiny HTTP server so the pod stays up and the proxy URL is testable.
echo "pod up: sshd started, serving http on :${PORT:-8000}"
exec python3 -u -m http.server "${PORT:-8000}"
