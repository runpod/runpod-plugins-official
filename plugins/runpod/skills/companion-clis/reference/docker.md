---
concepts: [container-image, template]
---

# Docker

Docker is used to build and validate container images locally before pushing to Docker Hub. Runpod uses Docker Hub as its default image registry — serverless endpoints, pods, and templates all reference images by their Docker Hub tag. Once an image is pushed, Runpod workers pull it automatically when the endpoint or pod is started.

> **Not installed?** One-time install lives in [`docker-setup.md`](docker-setup.md) — skip if `docker --version` already works.

## Credentials

Docker Hub authentication uses a personal access token (PAT), not your account password.

1. Go to https://app.docker.com → Avatar (top right) → Account Settings → Personal Access Tokens
2. Click **Generate new token** — give it a descriptive name, set an expiration, and choose **Read & Write** access
3. Copy the token immediately — it is shown only once

```bash
docker login -u DOCKERHUB_USERNAME
# When prompted for a password, paste your personal access token
```

Credentials are saved to `~/.docker/config.json` after a successful login.

## Tagging

> **Always use explicit semantic version tags. Never rely on `latest`.**
> Full rationale (why `latest` is mutable/unreliable, digest pinning, and the x86
> `--platform` rule) lives in the canonical
> [runpod-usage Docker reference](../../runpod-usage/reference/docker.md) — don't restate it here.

Use a tag that uniquely identifies the build: `v1.0.0`, `v1.0.1`, etc.

```bash
# Correct: explicit semantic version tag
docker build --platform=linux/amd64 -t myorg/myimage:v1.0.0 .
docker push myorg/myimage:v1.0.0

# Wrong: latest tag is ambiguous and unreliable
docker build -t myorg/myimage:latest .
```

## Docker Hub

Docker Hub is the registry Runpod pulls images from. After pushing, images are visible at https://hub.docker.com/repositories/ and referenceable in Runpod as `username/image:tag`.

Images on Docker Hub can be public (anyone can pull) or private (requires credentials). For private images, register your Docker Hub credentials in Runpod once and they become available to any template:

1. Go to https://console.runpod.io/user/settings → **Container Registry Settings**
2. Add your Docker Hub username and personal access token (the same PAT used for `docker login`)
3. When creating or editing a template, select the saved credential from the dropdown

> Runpod currently only supports `docker login` type credentials for container registry authentication.

## Key Commands

```bash
# Build for Runpod (always --platform=linux/amd64 — pods run on x86 Linux)
docker build --platform=linux/amd64 -t myorg/myimage:v1.0.0 .
docker build --platform=linux/amd64 -t myorg/myimage:v1.0.0 -f Dockerfile.prod .  # specify Dockerfile

# Tag an existing image before pushing (does not duplicate image data)
docker tag myorg/myimage:v1.0.0 myorg/myimage:v1.0.1

# Push to Docker Hub (image becomes available to Runpod as myorg/myimage:v1.0.0)
docker push myorg/myimage:v1.0.0

# Run locally for validation
docker run --rm -it myorg/myimage:v1.0.0 bash
docker run --rm --gpus all myorg/myimage:v1.0.0 bash   # with GPU (requires nvidia-container-toolkit)
docker run --rm -p 8080:80 -e API_KEY=secret myorg/myimage:v1.0.0  # port mapping + env vars

# Debug a running container
docker exec -it CONTAINER_ID /bin/bash

# Inspect
docker images                          # list local images
docker ps -a                           # list all containers (including stopped)
docker logs CONTAINER_ID             # view container output
docker logs -f CONTAINER_ID          # follow logs in real time

# Cleanup
docker rmi myorg/myimage:v1.0.0        # remove an image
docker rm CONTAINER_ID               # remove a stopped container
```
