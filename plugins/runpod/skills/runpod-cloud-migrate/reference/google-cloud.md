---
concepts: [pod, serverless-endpoint, template, network-volume, global-volume, registry-credential, runpod-secret, gpu-pool]
---
# Migrate from Google Cloud to Runpod

Scope: GPU and AI workloads on Compute Engine, Vertex AI (named "Gemini Enterprise Agent Platform" in Google's docs; `gcloud ai`, the `aiplatform` SDK and API, and `google_vertex_ai_*` keep their names), Cloud Run with GPUs, GKE GPU node pools, Batch, and Cluster Toolkit Slurm. The default plan is hybrid: move GPU compute to Runpod, keep Cloud Storage, IAM, and the rest of the app on Google Cloud. A full exit is the same steps plus data relocation. Terraform is a first-class path (`runpod/runpod` `~> 2.0`, built on REST API v2).

Sources: Google Cloud docs, checked 2026-11-14:
[GPU machine types](https://docs.cloud.google.com/compute/docs/gpus),
[custom container requirements](https://docs.cloud.google.com/vertex-ai/docs/predictions/custom-container-requirements),
[online inference](https://docs.cloud.google.com/vertex-ai/docs/predictions/get-online-predictions),
[endpoint types](https://docs.cloud.google.com/vertex-ai/docs/predictions/choose-endpoint-type),
[`gcloud ai endpoints deploy-model`](https://docs.cloud.google.com/sdk/gcloud/reference/ai/endpoints/deploy-model),
[Cloud Run GPU](https://docs.cloud.google.com/run/docs/configuring/services/gpu),
[Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract),
[Artifact Registry Docker auth](https://docs.cloud.google.com/artifact-registry/docs/docker/authentication),
[OpenAI-compatible endpoint](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/openai),
[instance lifecycle](https://docs.cloud.google.com/compute/docs/instances/instance-lifecycle).

## Detect

| Signal (grep) | What it means | Lands on |
| --- | --- | --- |
| `from google\.cloud import aiplatform` or `import vertexai` | Vertex AI SDK: deploy, predict, or training calls | Serverless endpoint client, or `@app.task` |
| `aiplatform\.Endpoint\(` and `\.predict\(instances=` | Vertex AI online inference call | Bearer HTTPS call to a Serverless endpoint |
| `aiplatform\.googleapis\.com/.+:predict` or `:rawPredict` | Vertex AI REST inference | Queue `/runsync` or load-balancing path |
| `endpoints/openapi` | Google OpenAI-compatible Chat Completions | Public Endpoint or vLLM `/openai/v1` |
| `batch_predict\(` or `batchPredictionJobs` | Vertex AI batch inference | Queue endpoint `/run` plus webhook |
| `CustomJob`, `CustomContainerTrainingJob`, `gcloud ai custom-jobs` | Vertex AI custom training | Pod or `@app.task` |
| `AIP_HTTP_PORT`, `AIP_HEALTH_ROUTE`, `AIP_PREDICT_ROUTE` | Vertex AI custom serving container | Load-balancing worker, or queue handler |
| `AIP_STORAGE_URI`, `AIP_MODEL_DIR`, `AIP_CHECKPOINT_DIR`, `/gcs/` | Vertex AI managed artifact paths | Volume paths |
| `gcloud run deploy` with `--gpu`, or `nvidia.com/gpu` in a Knative `Service` YAML | Cloud Run GPU service | Load-balancing endpoint |
| `K_SERVICE`, `K_REVISION` | Code running on a Cloud Run service | Load-balancing endpoint |
| `CLOUD_RUN_TASK_INDEX`, `gcloud run jobs` | Cloud Run job | Queue endpoint or `@app.task` |
| `fetch_id_token\(` or `print-identity-token` | Caller of a private Cloud Run service | Bearer API key call |
| `gcloud compute instances create` with `--accelerator` or `a2-`, `a3-`, `a4-`, `g2-`, `g4-` machine types | Compute Engine GPU VM | Pod |
| `startup-script` or `metadata_startup_script` | VM boot script | Pod start command or image build step |
| `deeplearning-platform-release` | Deep Learning VM image | Runpod PyTorch image |
| `cloud.google.com/gke-accelerator` or `nvidia.com/gpu` in a Kubernetes manifest | GKE GPU workload | Serverless endpoint, Pod, SkyPilot, or dstack |
| `gcluster ` or a Cluster Toolkit blueprint with Slurm modules | Slurm HPC cluster | Instant Cluster (Slurm) |
| `[a-z0-9-]+-docker\.pkg\.dev/` or `gcr\.io/` | Image in Artifact Registry | Registry credential (`_json_key`) |
| `gs://`, `gcsfuse`, `google\.cloud import storage` | Cloud Storage data | Keep with a key in a secret, or copy to a volume |
| `metadata\.google\.internal`, `google\.auth\.default\(` | Relies on attached service account | Service account key in a Runpod secret |
| `resource "google_compute_instance"` with `guest_accelerator` or a GPU `machine_type` | Terraform GPU VM | `runpod_pod` |
| `resource "google_cloud_run_v2_service"` with `"nvidia.com/gpu"` | Terraform Cloud Run GPU | `runpod_template` + `runpod_serverless_endpoint` |
| `resource "google_vertex_ai_endpoint` | Terraform Vertex AI endpoint | `runpod_serverless_endpoint` |
| `resource "google_filestore_instance"` | Terraform Filestore | `runpod_network_volume` |

Live inventory (read-only): `gcloud asset search-all-resources --scope=projects/PROJECT_ID`, `gcloud compute instances list`, `gcloud ai endpoints list --region=R`, `gcloud ai endpoints describe ID --region=R --format=json`, `gcloud run services list`, `gcloud run services describe S --region=R --format=export`, `gcloud run jobs list`, `gcloud container clusters list`, `gcloud artifacts repositories list`, `gcloud filestore instances list`, `gcloud workbench instances list --location=ZONE`.

## Product map

| Google Cloud | Runpod | Notes |
| --- | --- | --- |
| Compute Engine GPU VM | Pod | Container, not VM. `linux/amd64` only. Host supplies the NVIDIA driver. |
| Spot VM, flex-start, reservations | On-demand Pod | REST v2 `queue` on `POST /v2/pods` waits for capacity. |
| Managed instance group | Serverless endpoint | Workers autoscale between `workers.min` and `workers.max`. |
| Vertex AI endpoint (short sync requests) | Load-balancing endpoint | Keeps the HTTP server and body shape. |
| Vertex AI endpoint (long or must-not-drop requests) | Queue endpoint | `/run`, `/runsync`, retries, webhooks. |
| Vertex AI batch inference | Queue endpoint | One `/run` per input or chunk. |
| Vertex AI custom training job | Pod or `@app.task` | `@app.task` is one ephemeral Pod per call. |
| Workbench, Colab Enterprise | Pod with JupyterLab | Official PyTorch images start JupyterLab. |
| Model Garden open model APIs | Public Endpoint (listed models only) or vLLM endpoint | vLLM route: `/v2/ENDPOINT_ID/openai/v1`. |
| Cloud Run GPU service | Load-balancing endpoint | See contract table below. |
| Cloud Run job, Batch job | Queue endpoint or `@app.task` | |
| GKE GPU node pool | Serverless endpoint, Pod, SkyPilot, dstack | Runpod has containers, not a Kubernetes API. |
| Cluster Toolkit Slurm | Instant Cluster (Slurm) | Stock varies by GPU type and region. State this to the user. |
| Artifact Registry | Registry credential | Images can stay in Artifact Registry. |
| Persistent Disk, Hyperdisk | Container disk, volume disk | |
| Filestore, Managed Lustre | Network volume (standard or high-performance) | One data center. |
| Cloud Storage, Cloud Storage FUSE | Keep, or network volume, or global volume | |
| Secret Manager | Runpod secret | `{{ RUNPOD_SECRET_name }}` in `env`. |
| IAM, service accounts | API key, organization roles | |
| VPC, firewall, Private Service Connect | Exposed ports, global networking | Gap. See below. |

GPU map (Pod `gpu.id` / Serverless pool). Confirm live stock with `runpodctl gpu list` or `GET /v2/catalog/gpus` (the `pool` field gives the pool ID).

| Google accelerator type (family) | Runpod GPU type ID | Pool |
| --- | --- | --- |
| `nvidia-tesla-t4` (N1), 16 GB | `NVIDIA RTX A4000`, `NVIDIA RTX 2000 Ada Generation` | `AMPERE_16` |
| `nvidia-tesla-v100` (N1), 16 GB | `Tesla V100-PCIE-16GB`, `Tesla V100-SXM2-16GB` | read from catalog |
| `nvidia-l4` (G2), 24 GB | `NVIDIA L4` | `AMPERE_24` |
| `nvidia-tesla-a100` (A2 Standard), 40 GB | `NVIDIA A40`, `NVIDIA RTX A6000` (48 GB) | `AMPERE_48` |
| `nvidia-a100-80gb` (A2 Ultra) | `NVIDIA A100 80GB PCIe`, `NVIDIA A100-SXM4-80GB` | `AMPERE_80` |
| `nvidia-h100-80gb`, `nvidia-h100-mega-80gb` (A3) | `NVIDIA H100 80GB HBM3`, `NVIDIA H100 PCIe` | `ADA_80_PRO` |
| `nvidia-h200-141gb` (A3 Ultra) | `NVIDIA H200` | `HOPPER_141` |
| `nvidia-b200` (A4), `nvidia-gb200` (A4X) | `NVIDIA B200` | read from catalog |
| `nvidia-gb300` (A4X Max) | `NVIDIA B300 SXM6 AC` | read from catalog |
| `nvidia-rtx-pro-6000` (G4), 96 GB | `NVIDIA RTX PRO 6000 Blackwell Server Edition` | read from catalog |

Multi-GPU machine types (`a3-highgpu-8g`) map to `gpu.count`. Pick by VRAM and generation fit, not by price.

## Field map

| Google field | REST v2 | runpodctl | Terraform |
| --- | --- | --- | --- |
| VM `machineType` + `guestAccelerators` | `gpu.id`, `gpu.count` | `--gpu-id`, `--gpu-count` | `gpu_type_id`, `gpu_count` |
| Vertex AI `--accelerator`, Cloud Run `--gpu-type` | `gpu.pools`, `gpu.count` | `--gpu-id POOL_ID` | `gpu_pools`, `gpu_count` |
| Image URI | `image` | `--image` | `image` |
| Container command and args, VM startup script | `entrypoint`, `cmd`, or `args` | `--docker-args` (Pod), `--docker-start-cmd` (template) | `args` |
| Env vars | `env` | `--env` | `env` |
| `--container-ports`, Cloud Run `--port` | `ports` + `env.PORT` + `env.PORT_HEALTH` | `--ports` on template | `ports`, `env` |
| `--container-health-route` | `env.HEALTH_CHECK_PATH` | template `--env` | `env` |
| `--min-replica-count`, `--min-instances` | `workers.min` | `--workers-min` | `workers_min` |
| `--max-replica-count`, `--max-instances` | `workers.max` | `--workers-max` | `workers_max` |
| Cloud Run `--concurrency` | `scaling: {type: REQUEST_COUNT, requestCount}` | `--scale-by requests --scale-threshold` | `scaling_type`, `scaling_value` |
| Cloud Run `--timeout` (seconds) | `timeout` (milliseconds) | `--execution-timeout` (seconds) | `timeout` |
| Boot disk size | `disk` | `--container-disk-in-gb` | `disk` |
| Data disk, Filestore share | `mounts.persistent`, `mounts.network` | `--volume-in-gb`, `--network-volume-id` | `persistent_volume`, `network_volumes` |
| Region, zone | `dataCenterIds` | `--data-center-ids` | `data_center_ids` |
| Attached service account | key in a secret, referenced in `env` | same | same |
| Artifact Registry access | `registry` | `--registry-auth-id` | `registry` |
| CUDA and driver (Deep Learning VM image family) | `gpu.minCudaVersion` | `--min-cuda-version` | `min_cuda_version` |

Load-balancing endpoints: create with `POST /v2/serverless` and `"type": "LOAD_BALANCER"`, the Runpod MCP `create-endpoint` tool, Terraform `endpoint_type = "LOAD_BALANCER"`, or the console. `type` and `scaling` are required on create, `type` is fixed afterwards, and the scaler is `REQUEST_COUNT`. `runpodctl serverless create` makes queue endpoints. Check `runpodctl serverless create --help` for the flags in the installed version. Walkthrough: [golden path 14](../../runpod/golden-paths/14-load-balancing-endpoint.md).

Contract differences for serving containers:

| | Vertex AI custom container | Cloud Run service | Runpod load balancing | Runpod queue |
| --- | --- | --- | --- | --- |
| Port | `AIP_HTTP_PORT`, default 8080 | `PORT`, default 8080 | `PORT` and `PORT_HEALTH`, default 80 | none |
| Health | `GET AIP_HEALTH_ROUTE` returns 200 | listen on the port (optional startup probe) | `GET /ping` or `HEALTH_CHECK_PATH`: 200 ready, 204 initializing | none |
| Request body | `{"instances": [...], "parameters": {...}}` | any | any | `{"input": {...}}` |
| Response body | `{"predictions": [...]}` | any | any | handler return under `output` |
| Limits | shared endpoint 1.5 MB and 60 s; dedicated 10 MB and up to 1 h | 5 min default, 60 min max | 30 MB, 5.5 min processing, 2 min wait for a worker | execution timeout up to 7 days |
| Auth | Google access token | ID token or public | `Authorization: Bearer RUNPOD_API_KEY` | same |
| Scale to zero | opt in (`--min-replica-count=0`, Preview) | yes | default | default |

## Code translation

Vertex AI custom container to a load-balancing worker. Zero-code path: run the same image with `PORT=8080`, `PORT_HEALTH=8080`, `HEALTH_CHECK_PATH` set to the existing health route, and `8080/http` exposed. Code path:

```python
# before (Vertex AI)
@app.get(os.environ.get("AIP_HEALTH_ROUTE", "/health"))
def health(): return {"status": "ok"}

@app.post(os.environ.get("AIP_PREDICT_ROUTE", "/predict"))
async def predict(request: Request):
    body = await request.json()
    return {"predictions": run(body["instances"], body.get("parameters", {}))}

uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AIP_HTTP_PORT", "8080")))
```

```python
# after (Runpod load balancing)
@app.get("/ping")
def ping():
    return Response(status_code=204) if model is None else {"status": "healthy"}

@app.post("/predict")
async def predict(request: Request):
    body = await request.json()
    return {"predictions": run(body["instances"], body.get("parameters", {}))}

uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "80")))
```

Vertex AI custom container to a queue handler:

```python
import runpod

def handler(job):
    body = job["input"]  # {"instances": [...], "parameters": {...}}
    return {"predictions": run(body["instances"], body.get("parameters", {}))}

runpod.serverless.start({"handler": handler})
```

Cloud Run service: keep the server. Add `/ping` (or set `HEALTH_CHECK_PATH`), set `PORT` and `PORT_HEALTH`, replace metadata-server credentials with a key from a secret, and move requests over 5.5 minutes to a queue endpoint.

Cloud Run job or Batch task: wrap per-task work in a handler and submit one `/run` per shard with the index in `input` (replaces `CLOUD_RUN_TASK_INDEX`).

Compute Engine startup script: one-time setup goes in the image, per-boot work goes in the start command. On official Runpod PyTorch images end with `/start.sh` so SSH and JupyterLab start: `bash -c 'bash /workspace/startup.sh && /start.sh'`. Drop GPU driver install steps.

Vertex AI custom job to `@app.task`:

```python
import runpod
from runpod import App, NetworkVolume

app = App("training")
data = NetworkVolume("training-data", size=200)

@app.task(gpu="H100", mounts={"/data": data})
def train(epochs: int = 3):
    ...  # read /data, write checkpoints to /data/checkpoints
```

Run with `rp flash dev train.py`. `AIP_MODEL_DIR`, `AIP_CHECKPOINT_DIR`, and `/gcs/BUCKET` paths become paths under the mount.

Terraform: add `runpod/runpod` `~> 2.0` next to `hashicorp/google`. `google_compute_instance` becomes `runpod_pod` (`gpu_type_id`, `gpu_count`, `image`, `disk`, `ports`, `env`, `args`, `network_volumes`, `min_cuda_version`). `google_cloud_run_v2_service` becomes `runpod_template` (`serverless = true`, `image`, `ports`, `env`, `registry`) plus `runpod_serverless_endpoint` (`template_id`, `endpoint_type`, `gpu_pools`, `scaling_type`, `scaling_value`, `workers_min`, `workers_max`, `timeout`). Read argument names from the [provider reference](https://registry.terraform.io/providers/runpod/runpod/latest/docs) before writing HCL.

## Data

| Source | Target | How |
| --- | --- | --- |
| Cloud Storage that stays | none | Service account key (or HMAC key for S3-style clients at `https://storage.googleapis.com`) in a Runpod secret |
| Cloud Storage to network volume | `/workspace` on a Pod | On a Pod: `gcloud auth activate-service-account --key-file=KEY` then `gcloud storage rsync gs://BUCKET/path /workspace/path --recursive`; or rclone; or console Cloud Sync (Google Cloud Storage provider, service account JSON) |
| Local copy to network volume | volume root | `runpodctl network-volume upload VOLUME_ID ./dir dir` (runpodctl v3.1.0+; check `runpodctl network-volume --help`; S3 API keys, S3-enabled data center), or `aws s3 sync ./dir s3://VOLUME_ID/dir --region DC --endpoint-url https://s3api-DC.runpod.io/` |
| Filestore, Lustre, Persistent Disk | network volume | Copy to Cloud Storage or a VM first, then as above |
| Model weights from Hugging Face | cached model | `--model-reference` on `runpodctl serverless create` |
| Read-heavy weights for many data centers | global volume | Attach to a Pod and copy in |

Rules:

- A network volume lives in one data center. Check GPU stock there before creating it. Mount path: `/workspace` on Pods, `/runpod-volume` on Serverless.
- The network volume S3-compatible API accepts S3 clients (`aws s3`, Boto3) at `https://s3api-DC.runpod.io/` with bucket = volume ID. `gcloud storage` targets Cloud Storage, so use S3 clients for this API.
- Google Cloud bills network usage for data leaving Cloud Storage. Tell the user to budget the one-time transfer. Runpod has no ingress or egress fees.
- Artifact Registry credential: `runpodctl registry create --name artifact-registry --username _json_key --password-stdin < key.json`. The service account needs `roles/artifactregistry.reader`. In Terraform use username `_json_key_base64` with `google_service_account_key.private_key`. `oauth2accesstoken` tokens last 60 minutes, so skip them for stored credentials.
- More on storage tiers: [storage reference](../../runpod-usage/reference/storage.md). Secrets: [secrets reference](../../runpod-usage/reference/secrets.md).

## Client and API call map

| Google call | Runpod call |
| --- | --- |
| `aiplatform.Endpoint(ID).predict(instances=[...], parameters={...})` | `POST https://ENDPOINT_ID.api.runpod.ai/predict` with the same body (load balancing), or `POST https://api.runpod.ai/v2/ENDPOINT_ID/runsync` with `{"input": {"instances": [...], "parameters": {...}}}` (queue) |
| `gcloud ai endpoints predict ID --region=R --json-request=request.json` | `curl` to the URLs above, or `runpodctl serverless run` |
| `.../endpoints/ID:predict` with `Bearer $(gcloud auth print-access-token)` | Same URLs with `Authorization: Bearer $RUNPOD_API_KEY` |
| `prediction.predictions` | `response.json()["predictions"]` (load balancing) or `["output"]["predictions"]` (queue) |
| `model.batch_predict(gcs_source=..., gcs_destination_prefix=...)` | Loop: `POST /run` per input with `webhook`, or poll `GET /status/JOB_ID` |
| `fetch_id_token(request, SERVICE_URL)` + `Authorization: Bearer ID_TOKEN` | `Authorization: Bearer RUNPOD_API_KEY` |
| `openai.OpenAI(base_url=".../endpoints/openapi", api_key=credentials.token)` | `openai.OpenAI(base_url="https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1", api_key=RUNPOD_API_KEY)` |
| `gcloud compute instances create / list / stop / delete` | `runpodctl pod create / list / stop / delete` |
| `gcloud ai endpoints list / delete`, `gcloud run services list / delete` | `runpodctl serverless list / delete` |
| `gcloud run deploy` | `POST /v2/serverless` (`LOAD_BALANCER`) |
| `gcloud logging read` | `runpodctl pod logs POD_ID`, `runpodctl serverless logs ENDPOINT_ID` |
| `gcloud secrets create` | `POST /v2/account/secrets` |

Queue job statuses: `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`. Pod statuses: `PROVISIONING`, `STARTING`, `RUNNING`, `EXITED`, `ERROR`, `TERMINATED`. Compute Engine `TERMINATED` means stopped, which is Pod `EXITED`. CLI details: [runpodctl command reference](../../runpodctl/reference/command-reference.md).

## Gaps: stop and ask the user

| Gap | Options to offer |
| --- | --- |
| VPC, firewall rules, Private Service Connect, private endpoints | (a) Public HTTPS with API key auth; (b) global networking between Pods (`POD_ID.runpod.internal`); (c) user-managed VPN or proxy; (d) keep the workload on Google Cloud |
| Attached service account, Workload Identity, metadata server | (a) Least-privilege service account key in a Runpod secret; (b) signed URLs for single objects; (c) keep the caller on Google Cloud |
| CMEK | (a) Encrypted volume disk with a Runpod-managed key; (b) encrypt at the application layer; (c) keep the data on Google Cloud |
| Spot VMs in the cost model | (a) On-demand Pods with checkpointing; (b) Serverless scale to zero; (c) ask sales about pricing |
| Reservations, flex-start, guaranteed capacity | (a) Queued Pod create (`queue` on `POST /v2/pods`); (b) several GPU pools on an endpoint; (c) contact sales. Never promise availability |
| Traffic split across model versions | (a) Two endpoints with client-side or gateway split; (b) rolling release on one endpoint |
| Requests over 5.5 minutes or 30 MB on load balancing | (a) Queue endpoint with `/run`; (b) pass object references through Cloud Storage or a volume |
| Unauthenticated public Cloud Run service | (a) Proxy that holds the Runpod API key; (b) Pod with an exposed HTTP port and app-level auth |
| Batch inference with BigQuery or Cloud Storage I/O | (a) Driver script that reads inputs and submits `/run`; (b) handler that reads and writes Cloud Storage itself |
| Sidecars, multi-container Cloud Run or GKE Pods | (a) Merge into one image; (b) separate endpoints |
| Gemini or other Google-hosted models | (a) Keep on Google Cloud; (b) a listed Public Endpoint; (c) open model on vLLM |
| Kubernetes-native tooling (operators, Helm) | (a) SkyPilot or dstack on Runpod; (b) keep GKE for control, Runpod for GPU jobs |
| Compliance requirements | Read the Runpod security and compliance page with the user; use Secure Cloud and `--compliance` placement filters |

## Verify

1. Pod: `runpodctl pod get POD_ID --output json` shows `runtimeStatus: running`; run `nvidia-smi` and the workload over SSH.
2. Endpoint readiness: `GET https://api.runpod.ai/v2/ENDPOINT_ID/health` shows a ready worker.
3. Real request from outside Runpod with a production-shaped input. Load balancing: the same body the Vertex AI or Cloud Run client sent. Queue: the body wrapped in `input`.
4. Compare output and warm and cold latency with the Google Cloud deployment on identical inputs.
5. Callback path: from the worker, read one object from Cloud Storage with the secret-held key.
6. Private image: a fresh worker pulls from Artifact Registry (check `runpodctl serverless logs ENDPOINT_ID` for pull errors).
7. Cost guard: `workers.max` set deliberately, `workers.min` at 0 unless requested, test Pods stopped or deleted.

Common failures: worker running but never ready (set `PORT` and `PORT_HEALTH`, expose the port, health path returns 200); `not allowed for QB API` (endpoint is queue type, recreate as `LOAD_BALANCER`); `no workers available` (cold start, retry); default credentials error (load the key from the secret); handler missing `instances` (wrap body in `input`).

## Shut down Google Cloud

Run only after explicit user approval, and show the commands first. Keep what Runpod still uses (buckets, the pull service account, Artifact Registry).

```bash
# Vertex AI: deployed models bill while deployed
gcloud ai endpoints describe ENDPOINT_ID --region=LOCATION_ID
gcloud ai endpoints undeploy-model ENDPOINT_ID --region=LOCATION_ID --deployed-model-id=DEPLOYED_MODEL_ID
gcloud ai endpoints delete ENDPOINT_ID --region=LOCATION_ID

# Cloud Run
gcloud run services delete SERVICE --region=REGION
gcloud run jobs delete JOB --region=REGION

# Compute Engine VMs, then leftovers
gcloud compute instances delete VM_NAME --zone=ZONE
gcloud compute disks list
gcloud compute disks delete DISK_NAME --zone=ZONE
gcloud compute snapshots list
gcloud compute snapshots delete SNAPSHOT_NAME
gcloud compute addresses list
gcloud compute addresses delete ADDRESS_NAME --region=REGION
gcloud compute routers nats delete NAT_NAME --router=ROUTER_NAME --region=REGION

# Notebooks, file shares, images
gcloud workbench instances delete INSTANCE_NAME --location=ZONE
gcloud filestore instances delete INSTANCE_NAME --zone=ZONE
gcloud artifacts repositories delete REPO --location=LOCATION
```

Checklist of items that keep billing: persistent disks and snapshots (disks and external IPs bill in every VM state, including stopped), static external IPs, Cloud NAT, Vertex AI endpoints with deployed models, Workbench instances, Filestore instances, Artifact Registry storage, Cloud Run minimum instances, GKE GPU node pools, managed instance groups (delete the group), reservations and commitments. In Terraform, remove the `google_*` blocks that were replaced and apply; set `deletion_protection = false` first where it is enabled.
