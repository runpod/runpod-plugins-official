---
concepts: [pod, network-volume, exposed-port, ssh-key, pod-ssh-access, gpu-type, template, instant-cluster]
---
# Migrate from Lambda to Runpod

Scope: Lambda the GPU cloud (lambda.ai, formerly Lambda Labs), not AWS Lambda. Covers
On-Demand Cloud (ODC) instances, filesystems, firewall rules and rulesets, SSH keys,
Lambda Stack images, the Lambda Cloud API, and 1-Click Clusters (1CC). Lambda instances
are full VMs; Runpod Pods are containers, so the core work is turning a hand-configured
VM into an image plus a network volume. Lambda sunset its hosted Inference API
(shutdown date September 25, 2025), so inference here means a server the user hosts on
an instance.

Sources: Lambda docs, checked 2026-11-14:
[On-Demand Cloud](https://docs.lambda.com/public-cloud/on-demand/),
[creating and managing instances](https://docs.lambda.com/public-cloud/on-demand/creating-managing-instances/),
[filesystems](https://docs.lambda.com/public-cloud/filesystems/),
[Filesystem S3 Adapter](https://docs.lambda.com/public-cloud/s3-adapter-filesystems/),
[firewalls](https://docs.lambda.com/public-cloud/firewalls/),
[billing](https://docs.lambda.com/public-cloud/billing/),
[importing and exporting data](https://docs.lambda.com/public-cloud/importing-exporting-data/),
[1-Click Clusters](https://docs.lambda.com/public-cloud/1-click-clusters/),
[Cloud API browser](https://docs.lambda.com/api/cloud) and its
[OpenAPI spec](https://docs.lambda.com/api/cloud/spec.json) (version 1.10.0).

## Detect

| Signal | What it means | Lands on |
| --- | --- | --- |
| `cloud.lambda.com/api/v1` | Lambda Cloud API call (primary host) | REST v2 `https://api.runpod.io/v2` |
| `cloud.lambda.ai/api/v1` | Same API, deprecated host | REST v2 |
| `cloud.lambdalabs.com/api/v1` | Same API, deprecated host | REST v2 |
| `LAMBDA_API_KEY` | Lambda API key in env or CI secrets | `RUNPOD_API_KEY` |
| `instance-operations/launch` | Instance create | `POST /v2/pods`, `runpodctl pod create` |
| `instance-operations/terminate` | Instance delete | `DELETE /v2/pods/{id}`, `runpodctl pod delete` |
| `instance-operations/restart` | Instance restart | `POST /v2/pods/{id}/action` |
| `instance_type_name` | Launch payload; value like `gpu_1x_a10`, `gpu_8x_h100_sxm5gdr` | `gpu.id` + `gpu.count` |
| regex `gpu_[0-9]+x_[a-z0-9_]+` | Lambda instance type name | GPU type ID + count (see GPU map) |
| `file_system_names` or `file_system_mounts` | Filesystem attached at launch | `mounts.network`, `--network-volume-id` |
| `/lambda/nfs/` | Filesystem mount path in code or scripts | `/workspace` |
| regex `files\.[a-z0-9-]+\.lambda\.com` | Filesystem S3 Adapter endpoint | Network volume S3 API `s3api-DC.runpod.io`, or copy from a Pod |
| `lambda-stack-24-04`, `lambda-stack-22-04`, `lambda-stack-legacy-22-04` | Lambda Stack image family | `runpod/pytorch` image or template |
| `gpu-base-24-04`, `gpu-base-22-04`, `ubuntu-24-04`, `ubuntu-22-04` in a launch payload | Minimal image family | Any `linux/amd64` image |
| `firewall-rules` or `firewall-rulesets` | Firewall management through the API | `ports` on the Pod |
| `user_data` in a launch payload | cloud-init at boot | Dockerfile, start command, `env` |
| `lambdaspaces.com` | JupyterLab URL of an instance | `https://POD_ID-8888.proxy.runpod.net` |
| `ubuntu@` plus an IP in SSH config or CI | SSH to an instance | `root@POD_IP -p PORT` from `runpodctl ssh info` |
| `lambda-guest-agent` | Lambda metrics agent install | Drop; use Pod telemetry and logs |
| `sudo docker run --gpus all` in runbooks | Container run on the VM | Image becomes the Pod image |
| `docker compose` or `docker-compose.yml` used on an instance | Multi-container VM | Gap: one Pod per service |
| Terraform `source` of `squat/lambda` or `elct9620/lambdalabs` | Community Lambda provider | `runpod/runpod` `~> 2.0` |

AWS Lambda signals (`aws lambda`, `lambda_handler`, `AWS::Lambda::Function`,
`aws_lambda_function`) are a different platform. Do not apply this reference to them.

## Product map

| Lambda | Runpod | Key difference |
| --- | --- | --- |
| ODC instance (VM, user `ubuntu`, `sudo`) | Pod (container, user `root`) | Runpod runs Docker for the user; Docker and Docker Compose do not run inside a Pod |
| Launch, restart, terminate | Create, restart, stop, start, terminate | Stop keeps the volume disk and bills storage |
| Root volume (512 GiB to 22 TiB, lost on terminate) | Container disk (ephemeral) + volume disk or network volume at `/workspace` | Only `/workspace` persists across stop and restart |
| Filesystem (usage-billed, region-bound, attach at launch, `/lambda/nfs/NAME`) | Network volume (provisioned 10 to 4096 GB, one data center, `/workspace`) | Size is chosen up front; grows, never shrinks |
| Filesystem S3 Adapter (us-east-2, us-east-3, us-midwest-2) | Network volume S3-compatible API (select data centers) | Separate S3 API key on Runpod |
| Firewall rules (TCP, UDP, ICMP, source CIDR) | `ports`: `PORT/http`, `PORT/tcp` | TCP and HTTP only; exposed ports are public |
| Public IPv4, same port | HTTPS proxy URL, or public IP + mapped external port | Request a port above 70000 for a symmetric mapping |
| Private IP between instances | Global networking, `POD_ID.runpod.internal` | NVIDIA GPU Pods in supported data centers |
| SSH key per workspace, one key per launch | Account SSH keys, all injected | `PUT /v2/account/ssh-keys` replaces the full set |
| Lambda Stack image | `runpod-torch-v280` and other official PyTorch templates | See [pytorch.md](../../runpod-templates/reference/pytorch.md) |
| JupyterLab (console Launch link) | Port 8888 on official PyTorch templates | Needs `JUPYTER_PASSWORD` or `startJupyter` |
| 1CC (16 to 512 H100 or B200 GPUs, weekly reservation, 3 head nodes) | Instant Cluster (2 to 8 nodes, 16 to 64 GPUs, on demand) | Larger sizes through sales; primary node is a GPU node |
| Managed or unmanaged Slurm on 1CC | Instant Cluster type `SLURM` | Needs an official Runpod PyTorch image |
| Managed Kubernetes on 1CC | Cluster types `SLURM`, `RAY`, `TRAINING`, `APPLICATION` | Gap: see below |
| Self-hosted inference on an instance | Pod, Serverless load-balancing endpoint, or Serverless vLLM | Serverless scales to zero |
| Per-minute billing, weekly invoice | Per-second billing, prepaid credits | Pods stop at a \$0 balance |
| Regions (`us-east-1`, `us-west-2`, ...) | Data centers (`US-KS-2`, `EU-RO-1`, ...) | `runpodctl datacenter list` |
| Workspaces, IAM roles, SSO | Teams, Organizations (roles, groups) | |
| Private Cloud | Runpod sales | |

### GPU map

Lambda encodes count and model in the type name. Read exact names from
`GET /api/v1/instance-types` or the inventory. Runpod IDs come from
`GET /v2/catalog/gpus` and `runpodctl gpu list`. Check live stock before choosing;
see [gpu-selection.md](../../runpod-usage/reference/gpu-selection.md).

| Lambda GPU (VRAM per GPU) | Runpod `gpu.id` |
| --- | --- |
| B200 (180 GB) | `NVIDIA B200` |
| H100 SXM (80 GB) | `NVIDIA H100 80GB HBM3` |
| H100 PCIe (80 GB) | `NVIDIA H100 PCIe` |
| A100 SXM (80 GB) | `NVIDIA A100-SXM4-80GB` |
| A100 SXM or PCIe (40 GB) | `NVIDIA A100 80GB PCIe`; 48 GB options `NVIDIA A40`, `NVIDIA RTX A6000`, `NVIDIA L40S` |
| A6000 (48 GB) | `NVIDIA RTX A6000` |
| A10 (24 GB) | 24 GB class: `NVIDIA RTX A5000`, `NVIDIA L4`, `NVIDIA GeForce RTX 4090` |
| RTX 6000 (24 GB) | 24 GB class: `NVIDIA RTX A5000` |
| Tesla V100 (16 GB) | `Tesla V100-PCIE-16GB`, `Tesla V100-SXM2-16GB` |
| GH200 (96 GB, ARM) | `NVIDIA H100 NVL` (94 GB) or `NVIDIA RTX PRO 6000 Blackwell Server Edition` (96 GB); rebuild for `linux/amd64` |

GPU count per Pod is capped by `maxCount` in the catalog. Lambda fixes vCPU and RAM per
instance type; on Runpod set `gpu.minVcpuCountPerGpu` and `gpu.minRamPerGpu` when the
job needs a floor.

## Field map

| Lambda launch field | REST v2 `POST /v2/pods` | `runpodctl pod create` | Terraform `runpod_pod` |
| --- | --- | --- | --- |
| `name` | `name` | `--name` | `name` |
| `region_name` | `dataCenterIds` | `--data-center-ids` | `data_center_ids` |
| `instance_type_name` | `gpu.id`, `gpu.count` | `--gpu-id`, `--gpu-count` | `gpu_type_id`, `gpu_count` |
| `image.family` / `image.id` | `image` or `templateId` | `--image` or `--template-id` | `image` or `template_id` |
| `ssh_key_names` | `startSsh: true` | `--ssh` (default true) | `start_ssh` |
| `file_system_names`, `file_system_mounts` | `mounts.network[{volumeId, path}]` | `--network-volume-id` | `network_volumes` |
| `firewall_rulesets` | `ports` (`"8000/http"`, `"22/tcp"`) | `--ports` | `ports` |
| `user_data` | `args`, `entrypoint`, `cmd`, `env` | `--docker-args`, `--env` (JSON object) | `args`, `env` |
| root volume (fixed) | `disk`, `mounts.persistent.size` | `--container-disk-in-gb`, `--volume-in-gb` | `disk`, `persistent_volume` |
| driver in the VM | `gpu.minCudaVersion` | `--min-cuda-version` | `min_cuda_version` |
| `hostname`, `tags`, `workspace_id` | Not set at Pod create | | |

`mounts.persistent` and `mounts.network` are mutually exclusive. A Pod with a network
volume runs in the volume's data center. For exact flags, check
`runpodctl pod create --help`; see [runpodctl](../../runpodctl/SKILL.md).

Filesystem create: `{"name", "region"}` becomes
`POST /v2/network-volumes {"name", "size", "dataCenter"}` or
`runpodctl network-volume create --name N --size GB --data-center-id DC`.

## Code translation

### Launch an instance → create a Pod

```bash
# Before (Lambda)
curl -X POST https://cloud.lambda.com/api/v1/instance-operations/launch \
  -H "Authorization: Bearer $LAMBDA_API_KEY" -H 'Content-Type: application/json' \
  -d '{"region_name":"us-east-1","instance_type_name":"gpu_1x_a10",
       "ssh_key_names":["my-key"],"file_system_names":["training-data"],"name":"worker"}'
# Response: {"data": {"instance_ids": ["..."]}}; poll GET /instances/{id} until status == "active"
```

```bash
# After (Runpod)
curl -X POST https://api.runpod.io/v2/pods \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
  -d '{"name":"worker","templateId":"runpod-torch-v280",
       "gpu":{"id":"NVIDIA RTX A5000","count":1},"dataCenterIds":["US-KS-2"],
       "mounts":{"network":[{"volumeId":"NETWORK_VOLUME_ID","path":"/workspace"}]},
       "ports":["22/tcp"],"startSsh":true}'
# Response: the Pod object (top-level "id"); poll GET /v2/pods/{id} until status == "RUNNING"
# SSH: pod.ssh.direct.command (needs 22/tcp), or pod.ssh.proxy.command (shell only)
```

### `docker run` on the VM → Pod image

```bash
# Before (on the Lambda instance)
sudo docker run --gpus all --ipc=host -p 8000:8000 \
  -v "$HOME/.cache/huggingface":/root/.cache/huggingface \
  --env "HUGGING_FACE_HUB_TOKEN=$HF_TOKEN" \
  vllm/vllm-openai --model meta-llama/Meta-Llama-3.1-8B-Instruct
```

```bash
# After
runpodctl pod create --name llama-server --image "vllm/vllm-openai:latest" \
  --gpu-id "NVIDIA A100 80GB PCIe" --volume-in-gb 100 --ports "8000/http" \
  --env '{"HUGGING_FACE_HUB_TOKEN":"YOUR_HF_TOKEN","HF_HOME":"/workspace/huggingface"}' \
  --docker-args "--model meta-llama/Meta-Llama-3.1-8B-Instruct --api-key YOUR_SERVER_KEY"
# URL: https://POD_ID-8000.proxy.runpod.net (public; keep --api-key)
```

Flag map: `--gpus all` → `--gpu-id` + `--gpu-count`; `-p P:P` → `--ports "P/http"` or
`"P/tcp"`; `-e` → `--env` JSON; `-v host:container` → network volume or volume disk at
`/workspace`; arguments after the image → `--docker-args`. For `--ipc=host`,
`--privileged`, and `--network host`, check `runpodctl pod create --help` and test the
workload without them.

### Lambda Stack VM → image

| Lambda image | Python | Runpod template | Image |
| --- | --- | --- | --- |
| `lambda-stack-24-04` | 3.12 | `runpod-torch-v280` | `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` |
| `lambda-stack-22-04` | 3.10 | `runpod-torch-v220` | `runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04` |

```dockerfile
FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404
ENV PYTHONUNBUFFERED=1 HF_HOME=/workspace/huggingface
RUN apt-get update --yes && DEBIAN_FRONTEND=noninteractive apt-get install --yes \
    --no-install-recommends git tmux rsync && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt
WORKDIR /workspace
```

Build with `docker build --platform linux/amd64`. Strip `torch`, `torchvision`, and
`nvidia-*` from the instance's `pip freeze` before installing. Lambda Stack also ships
TensorFlow and JAX; add them to `requirements.txt` when the workload imports them.
The base image's `/start.sh` starts sshd and, when `JUPYTER_PASSWORD` is set, JupyterLab.

### VM habits → container equivalents

| On the Lambda VM | On a Pod |
| --- | --- |
| `/home/ubuntu`, `sudo` | `/root`, already root |
| `systemctl enable/start SERVICE` | Start the process from the image start command or a start script |
| cron on the VM | Start `cron` from the start script, or schedule from outside |
| cloud-init `user_data` | Dockerfile `RUN` steps; runtime config in `env` |
| `apt install` over SSH | Dockerfile; reinstall after every container reset otherwise |
| Driver or kernel module install | Choose a host with `--min-cuda-version` |
| `~/.bashrc` exports | Pod `env` (reaches the main process; export again for SSH shells) |
| `ssh -L` tunnel to a closed port | Same over the direct SSH connection |

## Data

1. Read `bytes_used` from `GET /api/v1/filesystems` (updated every few hours); size the
   network volume with headroom.
2. Create the volume in the target data center, then a transfer Pod with the volume and
   `22/tcp`. See [storage.md](../../runpod-usage/reference/storage.md) and
   [golden path 07](../../runpod/golden-paths/07-network-volume-handoff.md).
3. Copy with one of:

| Source state | Method |
| --- | --- |
| Filesystem mounted on a running instance (any region) | From the instance: `rsync -avP --inplace -e "ssh -p POD_SSH_PORT" /lambda/nfs/NAME/ root@POD_IP:/workspace/` with `ssh -A` agent forwarding; install rsync on the Pod first |
| Filesystem in an S3 Adapter region, created March 2025 or later | From the Pod: `S3_ENDPOINT_URL=https://files.REGION.lambda.com s5cmd cp "s3://BUCKET/*" /workspace/` with Lambda S3 adapter keys |
| Filesystem not mounted, no S3 Adapter | Launch an instance with the filesystem attached (attach happens only at launch), then rsync |
| Data also in external object storage | `rclone copy` or Cloud Sync from the Pod |
| Hub-hosted model weights | Download again on the Pod with `HF_HOME=/workspace/huggingface` |
| A few files | `runpodctl send` / `runpodctl receive` |

4. Verify: compare `find DIR -type f | wc -l` and `du -sb DIR` on both sides.
5. Delete the transfer Pod; the volume keeps the data.

rsync, scp, and port forwarding need the direct SSH connection (public IP + `22/tcp`),
not the `ssh.runpod.io` proxy. Remove `.Trash-*` directories on the Lambda side first.

## Client and API call map

Lambda base: `https://cloud.lambda.com/api/v1`. Runpod base: `https://api.runpod.io`.
Both use `Authorization: Bearer KEY`. Lambda wraps results in `{"data": ...}` and errors
in `{"error": {"code": ...}}`; REST v2 returns the resource at the top level.

| Lambda | Runpod REST v2 | runpodctl |
| --- | --- | --- |
| `GET /instances` | `GET /v2/pods` | `pod list` |
| `GET /instances/{id}` | `GET /v2/pods/{id}` | `pod get` |
| `POST /instances/{id}` | `PATCH /v2/pods/{id}` | `pod update` |
| `POST /instance-operations/launch` | `POST /v2/pods` | `pod create` |
| `POST /instance-operations/restart` (list of IDs) | `POST /v2/pods/{id}/action` `{"action":"restart"}` (one Pod) | `pod restart` |
| `POST /instance-operations/terminate` (list of IDs) | `DELETE /v2/pods/{id}` (one Pod) | `pod delete` |
| (none) | `POST /v2/pods/{id}/action` `{"action":"stop"}` / `"start"` | `pod stop`, `pod start` |
| `GET /instance-types` | `GET /v2/catalog/gpus?include=AVAILABILITY&product=POD` | `gpu list` |
| `GET /regions` | `GET /v2/catalog/datacenters` | `datacenter list` |
| `GET /images` | `GET /v2/catalog/templates` | `template list` |
| `GET /ssh-keys` | `GET /v2/account/ssh-keys` | `ssh list-keys` |
| `POST /ssh-keys`, `DELETE /ssh-keys/{id}` | `PUT /v2/account/ssh-keys` (full replacement) | `ssh add-key`, `ssh remove-key` |
| `GET/POST /filesystems`, `DELETE /filesystems/{id}` | `GET/POST /v2/network-volumes`, `DELETE /v2/network-volumes/{id}` | `network-volume list/create/delete` |
| `PUT /firewall-rules`, `/firewall-rulesets` | `ports` on Pod create or `PATCH` | `--ports` |
| 1CC reservation (console) | `POST /v2/clusters` | |

Status: `booting` → `PROVISIONING`/`STARTING`; `active` → `RUNNING`; `unhealthy` →
`ERROR`; `terminating`/`terminated` → `TERMINATED`, then not found; Runpod adds `EXITED`
(stopped). Lambda `preempted` has no on-demand Pod counterpart.

Service addresses: `http://INSTANCE_IP:PORT` → `https://POD_ID-PORT.proxy.runpod.net`
(HTTPS, 100 s response timeout) or `POD_IP:EXTERNAL_PORT` for `PORT/tcp`. Addresses
change when a Pod is recreated; put them behind config or DNS. See
[networking.md](../../runpod-usage/reference/networking.md).

`runpodctl pod update --ports` replaces the whole port list; include existing ports.

## Gaps: stop and ask the user

| Gap | Options to offer |
| --- | --- |
| Instance runs Docker Compose or several containers | (a) one Pod per service joined by global networking; (b) one combined image with a start script; (c) move stateless services to Serverless |
| Firewall rule with a source CIDR other than `0.0.0.0/0` | (a) add authentication in the service; (b) keep the port unexposed and use global networking or an SSH tunnel; (c) put the user's own gateway in front |
| UDP firewall rule in use | (a) switch the protocol to TCP; (b) keep that service off Runpod |
| GH200 (ARM) instance or arm64 image | Rebuild for `linux/amd64` and retest; confirm with the user that every dependency has an x86-64 build |
| More than one filesystem mounted on an instance | (a) merge into one network volume with subdirectories; (b) one network volume plus one global volume; (c) REST v2 `mounts.network` with up to 4 network volumes in the Pod's data center (`runpodctl pod create` attaches one) |
| Filesystem larger than 4 TB | (a) split across volumes or move cold data to object storage; (b) contact Runpod support for a larger volume |
| Workload depends on `systemd`, kernel modules, or a specific driver | (a) start script as main process; (b) pick hosts by `--min-cuda-version`; (c) leave that workload on a VM |
| 1CC with more than 8 nodes, or Managed Kubernetes | (a) fit within an Instant Cluster (2 to 8 nodes); (b) contact Runpod sales for larger clusters; (c) port Kubernetes workloads to Slurm, Ray, Pods, or Serverless |
| Always-on inference server | (a) Pod, same shape; (b) Serverless vLLM or load-balancing endpoint that scales to zero (changes URL and cold-start behavior); see [runpod-vllm](../../runpod-vllm/SKILL.md) |
| Target GPU has no stock in the volume's data center | (a) another GPU that fits the VRAM need; (b) a different data center, chosen before the data copy |
| Invoiced billing expected | Runpod bills from prepaid credits; Organizations are post-paid. Ask which account type the user has |

Never promise stock or cluster availability. Show a cost estimate from live catalog
prices and get approval before any billable create.

## Verify

1. `runpodctl pod get POD_ID --output json` shows `runtimeStatus: running`.
2. `POST /v2/pods/{id}/exec` with
   `["sh","-c","nvidia-smi && python -c 'import torch; print(torch.cuda.is_available())' && df -h /workspace"]`
   returns the expected GPU count, `True`, and the volume.
3. A real request from outside: `curl https://POD_ID-PORT.proxy.runpod.net/...` returns the
   same result as the Lambda instance for the same input.
4. Direct SSH works with the command from `runpodctl ssh info POD_ID`.
5. Stop and start the Pod once; confirm the service comes back and data under
   `/workspace` is intact. See [pod-workflows.md](../../runpod-usage/reference/pod-workflows.md).
6. File counts and sizes on the network volume match the Lambda filesystem.

## Shut down Lambda

Run only after explicit user approval. Terminating an instance destroys its root volume
and deleting a filesystem destroys its data; Lambda cannot recover either.

```bash
API=https://cloud.lambda.com/api/v1; H="Authorization: Bearer $LAMBDA_API_KEY"

# 1. Terminate instances (in-VM shutdown does not stop billing)
curl -X POST "$API/instance-operations/terminate" -H "$H" -H 'Content-Type: application/json' \
  -d '{"instance_ids":["INSTANCE_ID"]}'

# 2. Delete filesystems (must not be mounted; billed while they exist)
curl -X DELETE "$API/filesystems/FILESYSTEM_ID" -H "$H"

# 3. Confirm
curl -s "$API/instances" -H "$H" | jq '.data | length'
curl -s "$API/filesystems" -H "$H" | jq '.data | length'
```

Lambda rate limits: one request per second; one launch per 12 seconds. 1CC reservations
run for their reserved term; tell the user to time the cluster cutover to the reservation
end. Leave SSH keys, firewall rulesets, and API keys for the user to remove in the Lambda
console (`DELETE /ssh-keys/{id}`, `DELETE /firewall-rulesets/{id}`, `DELETE /api-keys/{key_id}`).
