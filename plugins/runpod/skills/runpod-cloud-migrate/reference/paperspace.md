---
concepts: [pod, serverless-endpoint, template, container-image, network-volume, global-volume, exposed-port, public-endpoint]
---
# Migrate from Paperspace and DigitalOcean GPU to Runpod

Scope: Paperspace (part of DigitalOcean) Machines, Notebooks, Deployments, Workflows, shared drives and datasets, plus DigitalOcean GPU Droplets, Bare Metal GPUs, DOKS GPU node pools, Volumes, Spaces, and Inference (serverless inference, dedicated inference, 1-Click Models). Covers detection, target selection, field and code translation, data transfer, client changes, verification, and shutdown. Use the product names DigitalOcean's docs use: "Inference" for the model APIs, "Gradient" only for the Paperspace products and subscription plans.

Sources: DigitalOcean docs, checked 2026-11-14: [Paperspace](https://docs.digitalocean.com/products/paperspace/), [Paperspace API](https://docs.digitalocean.com/reference/paperspace/api-reference/), [`pspace` CLI](https://docs.digitalocean.com/reference/paperspace/pspace/), [Deployment spec](https://docs.digitalocean.com/products/paperspace/deployments/reference/deployment-spec/), [Workflow spec](https://docs.digitalocean.com/products/paperspace/workflows/reference/workflow-spec/), [GPU Droplets](https://docs.digitalocean.com/products/gpu-droplets/), [Droplet features](https://docs.digitalocean.com/products/droplets/details/features/), [Droplet pricing](https://docs.digitalocean.com/products/droplets/details/pricing/), [Inference](https://docs.digitalocean.com/products/inference/), [doctl](https://docs.digitalocean.com/reference/doctl/reference/), [Terraform provider](https://registry.terraform.io/providers/digitalocean/digitalocean/latest/docs).

Facts that shape the plan:

- The `gradient` CLI and SDK call API endpoints that DigitalOcean removed (15 July 2024). Treat `gradient ...` commands in a repo as dead automation to replace, and inventory with `pspace`, the Paperspace API (`https://api.paperspace.com/v1`), or the console.
- `pspace` manages machines, deployments, projects, secrets, shared drives, snapshots, templates, startup scripts, public IPs, and autoscaling groups. Notebooks, Workflows, and datasets are listed in the Paperspace console (datasets also at `GET /v1/datasets`).
- DigitalOcean's docs list no retirement date for Notebooks, Deployments, Workflows, or Machines. Do not tell the user these products are shutting down.
- Paperspace bills per hour, and machine compute bills only while powered on. GPU Droplets bill per second (60-second minimum) and keep billing while powered off until destroyed.

## Detect

| Signal | What it means | Lands on |
| --- | --- | --- |
| `pspace machine ` or `api.paperspace.com/v1/machines` | Paperspace Machine (VM) automation | Pod |
| `pspace deployment `, `pspace up`, `paperspace.(yaml\|yml\|json\|jsonc\|toml)`, `.paperspace/app.` | Paperspace Deployment config | Load-balancing or queue endpoint |
| `gradient deployments ` | Legacy Deployment automation (CLI no longer works) | Load-balancing or queue endpoint |
| `paperspacegradient.com` | Client calling a Deployment endpoint | Endpoint URL swap |
| `basicAuthKey` or `("paperspace",` basic auth | Protected Deployment endpoint | Bearer `RUNPOD_API_KEY` |
| `.gradient/workflows/` or `uses: (container\|script\|git-checkout\|s3-download\|create-model)@v1` | Gradient Workflow spec | `@app.task` or queue endpoint |
| `gradient workflows `, `gradient datasets `, `gradient notebooks ` | Legacy Gradient CLI automation | Replace per product |
| `instance-type: ` or `instanceType: ` or `machineType: ` with `P4000\|A4000\|A100-80G\|H100\|C5` | Paperspace machine type | GPU type ID or pool |
| `secret:[A-Za-z][A-Za-z0-9_]*` in YAML values | Paperspace secret reference | `{{ RUNPOD_SECRET_name }}` |
| `/notebooks`, `/storage/`, `/datasets/`, `/inputs/`, `/outputs/`, `/home/paperspace` | Paperspace runtime paths | `/workspace` or a volume mount path |
| `paperspace/gradient-base` | Notebook container image | PyTorch template or custom image |
| `PAPERSPACE_API_KEY` | Paperspace credential | `RUNPOD_API_KEY` |
| `doctl compute droplet ` with `--size gpu-` | GPU Droplet automation | Pod |
| `gpu-(h100\|h200\|l40s\|4000ada\|6000ada\|mi300\|mi325\|mi350\|mi355\|b300)x[18]-` | GPU Droplet or DOKS GPU size slug | GPU type ID or pool |
| `gpu-h100x1-base`, `gpu-h100x8-base`, `gpu-amd-base` | AI/ML-ready Droplet image | `runpod/pytorch` image |
| `digitalocean_droplet` with a `gpu-` size | Terraform GPU Droplet | `runpod_pod` |
| `digitalocean_volume`, `digitalocean_volume_attachment` | Terraform block storage | `runpod_network_volume` |
| `digitalocean_spaces_bucket`, `digitaloceanspaces.com` | Spaces object storage | Network volume S3 API, global volume, or keep |
| `digitalocean_kubernetes_node_pool` with a `gpu-` size, `doks.digitalocean.com/` | DOKS GPU node pool | Serverless, Pod, or Instant Cluster |
| `inference.do-ai.run` | DigitalOcean serverless inference | Public Endpoint or Serverless vLLM |
| `MODEL_ACCESS_KEY` | Serverless inference key | `RUNPOD_API_KEY` |
| `dedicated-inference.do-infra.ai` or `/v2/dedicated-inferences` | Dedicated inference | Serverless vLLM |
| `from pydo import` with `chat.completions` | PyDo inference client | OpenAI SDK or `runpod.Endpoint` |
| `api.digitalocean.com/v2/droplets`, `DIGITALOCEAN_TOKEN`, `DIGITALOCEAN_ACCESS_TOKEN` | DigitalOcean control-plane calls | REST v2 or `runpodctl` |
| `user_data`, `--user-data-file`, `pspace startup-script` | VM boot script | Dockerfile steps or start command |

Scan command:

```bash
grep -rnE "pspace |gradient (deployments|workflows|notebooks|datasets)|api\.paperspace\.com|paperspacegradient\.com|PAPERSPACE_API_KEY|\.gradient/workflows|doctl |api\.digitalocean\.com|digitaloceanspaces\.com|inference\.do-ai\.run|do-infra\.ai|DIGITALOCEAN_(ACCESS_)?TOKEN|MODEL_ACCESS_KEY|from pydo|digitalocean_(droplet|volume|spaces_bucket|kubernetes)" .
```

Live inventory (read-only, when the CLIs are authenticated):

```bash
pspace machine list --json; pspace deployment list --json; pspace shared-drive list --json
pspace project list --json; pspace snapshot list --json; pspace template list --json
pspace deployment get DEPLOYMENT_ID --json        # full spec and endpoint URL
doctl compute droplet list --gpus --output json   # GPU Droplets are hidden without --gpus
doctl compute volume list --output json; doctl compute snapshot list --output json
doctl kubernetes cluster list --output json
doctl kubernetes cluster node-pool list CLUSTER_ID --output json
curl -s -H "Authorization: Bearer $DIGITALOCEAN_TOKEN" https://api.digitalocean.com/v2/dedicated-inferences
```

## Product map

| Source | Runpod target | Key change |
| --- | --- | --- |
| Paperspace Machine (Linux), GPU Droplet | Pod | VM becomes a container. Installs move into a Dockerfile. |
| Paperspace Machine (Windows), desktop streaming | Stop and ask | Pods run Linux containers. |
| Paperspace Notebook | Pod from template `runpod-torch-v280` | Files move from `/notebooks` to `/workspace`. JupyterLab needs `JUPYTER_PASSWORD`. |
| Paperspace Deployment (HTTP server) | Load-balancing endpoint | Keep the server. Add a health path, set `PORT` and `PORT_HEALTH`. |
| Paperspace Deployment (long or batch requests) | Queue endpoint | Write a handler. Clients send `{"input": {...}}`. |
| Gradient Workflow job | `@app.task` | Job order moves into Python. `/inputs` and `/outputs` become a shared network volume. |
| Gradient Workflow fan-out | `@app.queue` or queue endpoint | Autoscaling workers pull from the queue. |
| Serverless inference, model Runpod hosts | Public Endpoint | Base URL and key swap. |
| Serverless or dedicated inference, 1-Click Model | Serverless vLLM | Hub vLLM worker with `MODEL_NAME`. |
| Bare Metal GPUs, multi-node contract Droplets | Instant Cluster | Slurm, PyTorch, or Ray. |
| DOKS GPU node pool | Endpoint, Pod, or `@app.task` by workload shape | No Kubernetes API. SkyPilot and dstack integrations exist. |
| OS template, custom template, snapshot, Droplet image | Docker image plus template | `linux/amd64` only. |
| Machine disk, Droplet boot disk | Volume disk at `/workspace` or network volume | Only the mount persists across a stop. |
| Droplet scratch disk | Container disk | Temporary on both sides. |
| Shared drive, Notebook `/storage`, Network File Storage, DigitalOcean Volume | Network volume | One data center. File system mount, not a block device. |
| Paperspace dataset, Spaces bucket | Network volume (S3-compatible API), global volume, or keep in Spaces | No dataset versioning or bucket service. |
| Paperspace secret | Runpod secret | `{{ RUNPOD_SECRET_name }}`, SDK `Secret("name")`. |
| Paperspace private network, DigitalOcean VPC | Global networking | `POD_ID.runpod.internal`, NVIDIA GPU Pods. |
| Static or dynamic public IP | HTTP proxy URL or mapped TCP port | Runpod assigns the IP and external port. |

GPU map (Runpod IDs from the docs GPU reference; always confirm with `runpodctl gpu list`):

| Source | Pod GPU type ID | Serverless pool |
| --- | --- | --- |
| GPU+, P4000, RTX4000 (8 GB), P5000, RTX5000, A4000, V100 (16 GB) | `NVIDIA RTX A4000` | `AMPERE_16` |
| P6000, A5000 (24 GB) | `NVIDIA RTX A5000` | `AMPERE_24` |
| `gpu-4000adax1-20gb` | `NVIDIA RTX 4000 Ada Generation` | `AMPERE_16` |
| V100-32G, A100 (40 GB), A6000 | `NVIDIA RTX A6000` or `NVIDIA A40` | `AMPERE_48` |
| `gpu-6000adax1-48gb`, `gpu-l40sx1-48gb` | `NVIDIA RTX 6000 Ada Generation`, `NVIDIA L40S` | `ADA_48_PRO` |
| A100-80G | `NVIDIA A100 80GB PCIe` | `AMPERE_80` |
| H100, `gpu-h100x1-80gb`, `gpu-h100x8-640gb` | `NVIDIA H100 80GB HBM3` | `ADA_80_PRO` |
| `gpu-h200x1-141gb`, `gpu-h200x8-1128gb` | `NVIDIA H200` | `HOPPER_141` |
| `gpu-mi300x*` | `AMD Instinct MI300X OAM` | Check `GET /v2/catalog/gpus` |
| B300, MI325X, MI350X, MI355X plans | `NVIDIA B300 SXM6 AC` or check the catalog | Check `GET /v2/catalog/gpus` |

## Field map

Deployment spec to endpoint (`apiVersion` `v0alpha1`, `v1`, and `latest` use `resources.ports` and `resources.machineType`; `v0alpha0` uses `port`, `resources.instanceType`, and `models`; accept both):

| Paperspace Deployment field | REST v2 `POST /v2/serverless` | Other surfaces |
| --- | --- | --- |
| `name`, `image` | `name`, `image` | Terraform `name`, `image` |
| `containerRegistry` | `registry` (credential ID) | `runpodctl registry create`, SDK `registry_auth` |
| `command` | `entrypoint`, `cmd` | `runpodctl template create --docker-start-cmd` |
| `port`, `resources.ports` | `ports: ["8000/http"]` plus env `PORT`, `PORT_HEALTH` | Terraform `ports` |
| `env[].name`, `env[].value` | `env` object | SDK `env={}` |
| `value: secret:NAME` | `{{ RUNPOD_SECRET_name }}` | SDK `Secret("name")` |
| `resources.instanceType`, `machineType` | `gpu.pools`, `gpu.count` | `runpodctl serverless create --gpu-id`, Terraform `gpu_pools` |
| `resources.replicas` | `workers.min` | `--workers-min`, Terraform `workers_min` |
| `resources.autoscaling.maxReplicas` | `workers.max` | `--workers-max`, Terraform `workers_max` |
| `resources.autoscaling.metrics` (`cpu`, `memory`, `requestDuration`) | `scaling.type` `REQUEST_COUNT` or `QUEUE_DELAY` | `--scale-by`, `--scale-threshold` |
| `enabled: false` | `workers.max: 0` or delete | |
| `healthChecks.readiness.path` | env `HEALTH_CHECK_PATH` | `200` healthy, `204` initializing |
| `healthChecks.liveness`, `healthChecks.startup` | Fold into the health path | |
| `basicAuthKey` | Bearer API key is always required | |
| `region` (`ny2`, `ca1`, `ams1`) | `dataCenterIds` | `--data-center-ids` |
| `integrations[].type: git-lfs` (Hugging Face URL), `models` | Cached model | `--model-reference URL:REVISION`, SDK `Model()` |
| `integrations[].type: s3` | `mounts.network` or S3 client code | |

Machine or Droplet to Pod:

| Source field | `runpodctl pod create` | REST v2 `POST /v2/pods` | Terraform `runpod_pod` |
| --- | --- | --- | --- |
| `machineType`, Droplet `size` | `--gpu-id`, `--gpu-count` | `gpu.id`, `gpu.count` | `gpu_type_id`, `gpu_count` |
| `templateId`, Droplet `image` | `--image` or `--template-id` | `image` or `templateId` | `image` or `template_id` |
| `region` | `--data-center-ids` | `dataCenterIds` | `data_center_ids` |
| `diskSize`, boot disk | `--volume-in-gb` or `--network-volume-id` | `mounts.persistent` or `mounts.network` | `persistent_volume` or `network_volumes` |
| root file system outside data paths | `--container-disk-in-gb` | `disk` | `disk` |
| Droplet `volumes`, `volume_ids` | `--network-volume-id` | `mounts.network[].volumeId`, `.path` | `network_volumes` |
| `publicIpType`, firewall rules | `--ports "8888/http,22/tcp"` | `ports` | `ports` |
| `networkId`, `vpc_uuid` | `--global-networking` | `globalNetworking` | `global_networking` |
| `startupScriptId`, `user_data` | `--docker-args` or bake into the image | `cmd`, `entrypoint` | `args` |
| Droplet `ssh_keys` | account keys via `runpodctl ssh add-key` | `startSsh` | `start_ssh`, `runpod_account_ssh_keys` |
| CUDA and driver in the VM image | `--min-cuda-version` | `gpu.minCudaVersion` | `min_cuda_version` |
| `autoShutdownTimeout` | In-job `runpodctl pod stop $RUNPOD_POD_ID` | | |

Terraform resources: `digitalocean_droplet` to `runpod_pod`; `digitalocean_volume` and `digitalocean_volume_attachment` to `runpod_network_volume` plus `network_volumes` on the Pod; `digitalocean_spaces_bucket` to `runpod_network_volume` or `runpod_global_volume` (or keep); `digitalocean_container_registry` to `runpod_registry` (pull credentials only); `digitalocean_kubernetes_node_pool` to `runpod_serverless_endpoint`, `runpod_pod`, or `runpod_cluster`. Provider is `runpod/runpod` `~> 2.0`, built on REST API v2, reads `RUNPOD_API_KEY`. Fetch argument names from the Terraform Registry before writing HCL.

For exact flags, check `runpodctl pod create --help`, `runpodctl serverless create --help`, and `runpodctl template create --help`. See [`runpodctl` command reference](../../runpodctl/reference/command-reference.md).

## Code translation

Deployment HTTP server to load-balancing worker (bodies and paths stay the same):

```python
# Before: Paperspace Deployment (readiness probe at /readiness/, port from the spec)
@app.get("/readiness/")
def readiness(response: Response):
    if not model_loaded:
        response.status_code = 503
    return "ok"
```

```python
# After: Runpod load-balancing worker
@app.get("/ping")
def ping():
    return Response(status_code=204) if not model_loaded else {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "80")))
```

Deployment to queue handler (when requests are long, bursty, or batch):

```python
import runpod

def handler(job):
    return {"prediction": predict(job["input"]["prompt"])}

runpod.serverless.start({"handler": handler})
```

Workflow job graph to SDK tasks:

```yaml
# Before: .gradient/workflows/train.yaml
jobs:
  train:
    resources: { instance-type: A100-80G }
    outputs: { model: { type: dataset, with: { ref: my-model } } }
    uses: container@v1
    with: { image: my-org/trainer:v1, args: [python, train.py, --out, /outputs/model] }
  evaluate:
    needs: [train]
    inputs: { model: train.outputs.model }
    uses: container@v1
    with: { image: my-org/trainer:v1, args: [python, evaluate.py, --model, /inputs/model] }
```

```python
# After: main.py, run with `rp flash dev main.py --once`
import subprocess
import runpod
from runpod import App, NetworkVolume

app = App("train-pipeline")
artifacts = NetworkVolume("pipeline-artifacts", size=100)

@app.task(gpu="A100", image="my-org/trainer:v1", mounts={"/artifacts": artifacts})
def train():
    subprocess.run(["python", "train.py", "--out", str(artifacts.path / "model")], check=True)
    return "model"

@app.task(gpu="A100", image="my-org/trainer:v1", mounts={"/artifacts": artifacts})
def evaluate(model_dir: str):
    subprocess.run(["python", "evaluate.py", "--model", str(artifacts.path / model_dir)], check=True)

@runpod.local_entrypoint
def main():
    evaluate.remote(train.remote())
```

VM to image: start `FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404`, add the `apt` and `pip` installs from the VM (`pip install --break-system-packages` on the Ubuntu 24.04 image), copy the code, build with `docker buildx build --platform linux/amd64`. Leave NVIDIA driver installs out of the image. `docker run` flags on a Droplet map to template fields (`-p` to ports, `-e` to env, `-v` to a volume mount). Runpod runs Docker for the Pod, so Docker Compose stacks split into one Pod per service or one image with a process supervisor. See [building images](../../runpod-usage/reference/building-images.md) and [Docker](../../runpod-usage/reference/docker.md). SDK details: [Runpod SDK API](../../runpod-flash/reference/api.md).

## Data

| Source | Destination | Transfer |
| --- | --- | --- |
| Machine disk, Droplet boot disk, DigitalOcean Volume | Network volume | On the VM: `aws s3 sync DIR s3://NETWORK_VOLUME_ID/DIR --region DC --endpoint-url https://s3api-DC.runpod.io/` |
| Same, data center without the S3-compatible API | Network volume | Pod with the volume attached and `22/tcp` exposed (official Runpod image, `rsync` installed), then `rsync -avz -e "ssh -p PORT" DIR root@POD_IP:/workspace/DIR` from the VM |
| Notebook `/notebooks`, `/storage`, mounted `/datasets` | Network volume | Notebook terminal: `pip install awscli`, then `aws s3 cp` or `sync` to the volume |
| Spaces bucket | Network volume | Inside a Pod: `aws s3 sync s3://BUCKET/ /workspace/DIR --endpoint-url https://REGION.digitaloceanspaces.com` |
| Hugging Face model (Deployment `git-lfs` integration) | Cached model | `--model-reference https://huggingface.co/ORG/NAME:main`; path `/runpod-volume/huggingface-cache/hub/` |
| Small ad hoc files | Pod | `runpodctl send FILE`, `runpodctl receive CODE` |

Rules:

- Create the volume first: `runpodctl network-volume create --name NAME --size GB --data-center-id DC`. Size is 10 to 4096 GB and grows only.
- A network volume pins every Pod and worker that mounts it to its data center. Pick a data center with stock for the chosen GPU, and one that supports the S3-compatible API.
- The S3-compatible API uses an S3 API key from the console (separate from `RUNPOD_API_KEY`). Bucket is the volume ID. Keys are file paths. It works with network volumes only.
- `aws s3 sync` is unreliable past about 10,000 files. Tar small files first.
- Mount paths: `/workspace` on Pods, `/runpod-volume` on Serverless.
- SSH keys are injected at Pod creation. Register a source VM's key before creating the transfer Pod.
- Global volumes are in beta, mount in any data center, bill by usage, and suit read-heavy shared weights.

See [storage](../../runpod-usage/reference/storage.md).

## Client and API call map

| Before | After |
| --- | --- |
| `https://HOST.paperspacegradient.com/PATH` with basic auth user `paperspace` | `https://ENDPOINT_ID.api.runpod.ai/PATH` with `Authorization: Bearer RUNPOD_API_KEY` |
| Same, moved to a queue endpoint | `POST https://api.runpod.ai/v2/ENDPOINT_ID/runsync` or `/run` with `{"input": {...}}`, then `/status/JOB_ID` |
| `OpenAI(base_url="https://inference.do-ai.run/v1", api_key=MODEL_ACCESS_KEY)` | `OpenAI(base_url="https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1", api_key=RUNPOD_API_KEY)` |
| Dedicated inference URL on `do-infra.ai` with its access token | Same vLLM base URL and `RUNPOD_API_KEY` |
| `pydo.Client(...).chat.completions.create` | OpenAI SDK against the vLLM or Public Endpoint base URL |
| TGI routes on a 1-Click Model Droplet | OpenAI-compatible routes on vLLM |
| `GET/POST api.paperspace.com/v1/machines`, `api.digitalocean.com/v2/droplets` | `GET/POST https://api.runpod.io/v2/pods` |
| `PATCH /v1/machines/ID/start\|stop\|restart`, `POST /v2/droplets/ID/actions` | `POST /v2/pods/POD_ID/action` with `{"action": "start"}`, `"stop"`, `"restart"`, `"terminate"` |
| `POST /v1/deployments`, `POST /v2/dedicated-inferences` | `POST /v2/serverless` |
| `POST /v1/shared-drives`, `POST /v2/volumes` | `POST /v2/network-volumes` |
| `pspace machine list`, `doctl compute droplet list --gpus` | `runpodctl pod list --all` |
| `pspace machine create`, `doctl compute droplet create` | `runpodctl pod create` |
| `pspace deployment up`, `pspace up` | `runpodctl serverless create` (queue), REST v2 with `"type": "LOAD_BALANCER"` (load balancing) |
| `pspace secret create` | `rp secret add NAME` |
| `doctl compute size list`, `doctl compute region list` | `runpodctl gpu list`, `runpodctl datacenter list` |

Load-balancing creation needs REST v2, Terraform (`endpoint_type = "LOAD_BALANCER"`), the SDK (`@app.api`), or the console. `runpodctl serverless create` creates queue endpoints. Load-balancing endpoints scale on `REQUEST_COUNT`. vLLM endpoints serve `/chat/completions`, `/completions`, and `/models`. Each Runpod model has its own base URL because the endpoint ID or Public Endpoint slug is in the path. See [endpoint workflows](../../runpod-usage/reference/endpoint-workflows.md) and [pod workflows](../../runpod-usage/reference/pod-workflows.md).

## Gaps: stop and ask the user

| Gap | Options to offer |
| --- | --- |
| Windows machine or desktop streaming | Keep it on Paperspace; port the workload to Linux and use JupyterLab, SSH, or an IDE connection. |
| DOKS workloads that need the Kubernetes API (operators, CRDs, Helm charts) | Keep DOKS for those; re-shape each workload onto endpoints, Pods, or tasks; use the SkyPilot or dstack integration. |
| Docker Compose or `systemd` multi-service VM | One Pod per service with global networking; one image with a process supervisor. |
| Workflow engine features (GitHub push triggers, typed inputs and outputs, DAG UI) | Python entrypoint run from CI with `rp flash dev main.py --once`; an external orchestrator calling queue endpoints. |
| Versioned datasets with tags | Versioned directory names on a network volume; keep datasets in an object store with versioning. |
| Spaces buckets serving public assets or using the CDN | Keep Spaces; move only private training data to a network volume. |
| Requests over 5.5 minutes or 30 MB on a Deployment | Queue endpoint with async jobs and webhooks; a Pod with a TCP port. |
| UDP services on a VM | Rework to TCP; keep on the VM. |
| Deployment that must stay warm (`replicas` of 2 for availability) | `workers.min` of 1 or more (billed while running); scale to zero and accept cold starts. |
| Autoscaling on CPU, memory, or request duration | Request count or queue delay with a tuned threshold. |
| Private dedicated inference endpoint reached over a VPC | Public HTTPS endpoint with API key auth; ask whether that meets the user's network policy. |
| Commercial third-party models, Inference Router, Agent Platform, Knowledge Bases | Keep on DigitalOcean; call the model provider directly; replace with an open model on vLLM. |
| Model not hosted as a Public Endpoint | Serverless vLLM with the Hugging Face model; choose the GPU pool by model size. |
| AMD GPU Droplets (ROCm stack) | Runpod AMD GPU type with a ROCm image if stock exists; rebuild on a CUDA image for NVIDIA GPUs. |
| Spot or contract GPU Droplets, Bare Metal GPUs | On-demand Pods; Instant Clusters for multi-node; ask the user to contact Runpod sales for committed capacity. |
| 8-GPU plans | `--gpu-count 8` if stock allows; fewer larger GPUs; an Instant Cluster. |
| Static public IP that clients allowlist | Proxy URL or assigned IP and port (read from `runpodctl pod get`); ask how clients should reach the service. |
| VM snapshots used as backups | Docker image for the environment plus a network volume for data. |
| Region or compliance requirement | `runpodctl datacenter list`, `--country-code`, `--compliance` on `runpodctl pod create` (Secure Cloud). |

Always get approval before creating billable Runpod resources, and show the GPU, storage, and worker settings with a cost estimate from live pricing first.

## Verify

1. Pod: `runpodctl pod get POD_ID` shows `runtimeStatus: running`; `runpodctl ssh info POD_ID`; run `nvidia-smi`; open `https://POD_ID-PORT.proxy.runpod.net`.
2. Load-balancing endpoint: `curl https://ENDPOINT_ID.api.runpod.ai/ping -H "Authorization: Bearer $RUNPOD_API_KEY"` returns `200`, then call a real path with a production-shaped body. Retry through the cold start (first call can time out).
3. Queue endpoint: `GET https://api.runpod.ai/v2/ENDPOINT_ID/health`, then `POST /runsync` with `{"input": {...}}` and compare `output` with the old deployment's response.
4. vLLM or Public Endpoint: `GET BASE_URL/models`, then one chat completion with the OpenAI SDK.
5. Data: compare file counts and checksums between the source and `/workspace` (or `/runpod-volume`).
6. Report the request sent, the response, and cold and warm latency. Leave traffic shifting to the user.

Common failures: JupyterLab 502 (set `JUPYTER_PASSWORD`), `exec format error` (image built for `arm64`), CUDA driver errors (set a CUDA floor), unhealthy load-balancing workers (`PORT` and `PORT_HEALTH` mismatch, or the health path returns `503` instead of `204` while loading), `401` (basic auth or model access key left in the client), no capacity (GPU out of stock in the volume's data center). See [gotchas](../../runpod-usage/reference/gotchas.md).

## Shut down Paperspace and DigitalOcean

Run these only after the user explicitly approves each resource. Confirm data is copied first: deleting a Paperspace machine also deletes its files and snapshots.

```bash
# Paperspace: powering off stops compute billing; storage, IPs, snapshots, templates still bill
pspace deployment delete DEPLOYMENT_ID
pspace machine stop MACHINE_ID
pspace machine delete MACHINE_ID          # the machine must be off first
pspace shared-drive delete SHARED_DRIVE_ID
pspace snapshot delete SNAPSHOT_ID        # check `pspace snapshot delete --help` for arguments
pspace template delete TEMPLATE_ID
pspace public-ip release PUBLIC_IP        # check `pspace public-ip release --help`
```

Notebooks, Workflows, datasets, and the Gradient subscription plan are managed in the Paperspace console. Ask the user to remove them there.

```bash
# DigitalOcean: a powered-off GPU Droplet still bills; destroy it
doctl compute droplet delete DROPLET_ID
doctl compute volume delete VOLUME_ID     # volumes and snapshots survive a Droplet delete
doctl compute snapshot list
doctl kubernetes cluster node-pool delete CLUSTER_ID POOL_ID
curl -X DELETE -H "Authorization: Bearer $DIGITALOCEAN_TOKEN" \
  https://api.digitalocean.com/v2/dedicated-inferences/DEDICATED_INFERENCE_ID
```

Droplet backups remain until their retention period ends. Spaces buckets and model access keys are removed in the DigitalOcean Control Panel. Afterward, remind the user to revoke the Paperspace API keys and DigitalOcean tokens used for the migration, and to delete any transfer Pods on Runpod.
