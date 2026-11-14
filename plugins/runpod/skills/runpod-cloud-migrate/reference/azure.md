---
concepts: [pod, serverless-endpoint, serverless-handler, template, registry-credential, network-volume, runpod-secret, gpu-type]
---
# Migrate from Azure to Runpod

Scope: GPU and AI workloads on Microsoft Azure. GPU virtual machines, Azure Machine Learning
(online endpoints, batch endpoints, jobs, compute), Azure Container Apps serverless GPUs, AKS GPU
node pools, Azure Batch, CycleCloud Slurm, and open-weight model inference through Azure OpenAI or
Microsoft Foundry. The default plan is hybrid: move GPU compute to Runpod, keep data, identity and
the rest of the app on Azure. A full exit is the same steps plus data relocation.

Sources: Microsoft Learn, checked 2026-11-14:
[VM sizes](https://learn.microsoft.com/azure/virtual-machines/sizes/overview),
[VM states and billing](https://learn.microsoft.com/azure/virtual-machines/states-billing),
[online endpoints](https://learn.microsoft.com/azure/machine-learning/how-to-deploy-online-endpoints),
[custom containers](https://learn.microsoft.com/azure/machine-learning/how-to-deploy-custom-container),
[deployment YAML](https://learn.microsoft.com/azure/machine-learning/reference-yaml-deployment-managed-online),
[Container Apps serverless GPUs](https://learn.microsoft.com/azure/container-apps/gpu-serverless-overview),
[ACR authentication](https://learn.microsoft.com/azure/container-registry/container-registry-authentication),
[Azure OpenAI v1 API](https://learn.microsoft.com/azure/ai-foundry/openai/api-version-lifecycle),
[azurerm provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs).

## Detect

| Signal (grep) | What it means | Lands on |
| --- | --- | --- |
| `from azure.ai.ml import` | Azure Machine Learning SDK v2 control plane or invoke | REST v2, `runpodctl`, or `runpod.Endpoint` |
| `def init\(\)` and `def run\(` in one file, or `AZUREML_MODEL_DIR` | Online endpoint scoring script | Queue endpoint handler |
| `managedOnlineEndpoint.schema.json` / `managedOnlineDeployment.schema.json` | Endpoint and deployment YAML | Queue endpoint, or load-balancing endpoint when `inference_config` is present |
| `inference_config:` with `scoring_route` | Custom container deployment | Load-balancing endpoint |
| `az ml online-endpoint` / `az ml online-deployment` | Deploy or invoke automation | `runpodctl template create --serverless` + `runpodctl serverless create` |
| `az ml batch-endpoint` / `batch_endpoints.invoke` | Batch scoring | Queue endpoint, `/run` + webhook |
| `az ml job create` / `command:` + `compute: azureml:` | Training job | Pod, or SDK `@app.task` |
| `az ml compute` / `azurerm_machine_learning_compute_instance` | Notebook or cluster compute | Pod (JupyterLab) |
| `inference\.ml\.azure\.com` | Online endpoint scoring URI in client code | `https://api.runpod.ai/v2/ENDPOINT_ID/runsync` |
| `AzureOpenAI\(` / `azure_endpoint` / `openai\.azure\.com` / `services\.ai\.azure\.com` | Azure OpenAI or Foundry model client | Public Endpoint or vLLM endpoint, open-weight models only |
| `az containerapp` / `azurecontainerapps\.io` / `Consumption-GPU-` / `azurerm_container_app` | Container Apps app, GPU when on a GPU workload profile | Load-balancing endpoint |
| `az vm create` + `Standard_N[CD]` / `azurerm_linux_virtual_machine` with `size = "Standard_N` | GPU VM | Pod |
| `Standard_NV` / `Standard_NG` / `azurerm_windows_virtual_machine` | VDI, visualization, or Windows GPU | Stays on Azure |
| `az aks nodepool add` + `--node-vm-size Standard_N` / `nvidia.com/gpu` | AKS GPU node pool | Serverless or Pods per workload, or SkyPilot/dstack |
| `azurecr\.io/` | Image in Azure Container Registry | Keep in ACR + Runpod registry credential |
| `blob\.core\.windows\.net` / `azcopy` / `blobfuse` | Blob Storage data | Keep and read with SAS, or copy to a network volume |
| `DefaultAzureCredential` / `ManagedIdentityCredential` | Workload identity | Service principal env vars from Runpod secrets, or SAS |
| `azapi_resource` with `Microsoft.MachineLearningServices/workspaces/onlineEndpoints` | Online endpoint in Terraform | `runpod_template` + `runpod_serverless_endpoint` |
| `cyclecloud` / `sbatch` on Azure hosts | Slurm HPC | Instant Cluster with Slurm |
| `*.bicep` / ARM `deploymentTemplate.json` | Bicep or ARM IaC | Terraform (`runpod/runpod`) or REST v2 |

## Product map

| Azure | Runpod | Notes |
| --- | --- | --- |
| GPU VM (NC, ND) | Pod | Linux container. No cloud-init, systemd, or driver install. |
| NV, NG, Windows GPU VM | None | Keep on Azure. |
| VM scale set | Serverless endpoint | Pods do not autoscale. |
| Managed online endpoint, scoring script | Queue endpoint | `init()` becomes module scope, `run()` becomes `handler(job)`. |
| Managed online endpoint, custom container | Load-balancing endpoint | See [golden path 14](../../runpod/golden-paths/14-load-balancing-endpoint.md). |
| Batch endpoint, Azure Batch | Queue endpoint `/run` + webhook, or `@app.task` | Fan out one job per file or shard. |
| AML job, compute cluster | Pod or `@app.task` | Bring your own pipeline orchestrator. |
| AML compute instance | Pod with `startJupyter` and `8888/http` | Official Runpod images honor the Jupyter flag. |
| Azure OpenAI, Foundry serverless APIs | Public Endpoint (listed models) or vLLM endpoint | Open-weight models only. |
| Container Apps serverless GPU | Load-balancing endpoint | `/ping`, `PORT`, `PORT_HEALTH`. |
| Container Instances GPU | Pod or Serverless | Microsoft lists it as retired as of 2025-07-14. |
| CycleCloud Slurm | Instant Cluster (Slurm) | Check multi-node stock first. Never promise availability. |
| ACR | `runpod_registry` / `runpodctl registry create` | ACR token or service principal as username and password. |
| Managed Disk, Azure Files, NetApp Files, Managed Lustre | Network volume | Pinned to one data center. |
| Blob Storage | Keep, or network volume / global volume | See [storage](../../runpod-usage/reference/storage.md). |
| Key Vault secret | Runpod secret | See [secrets](../../runpod-usage/reference/secrets.md). |
| `azurerm` / `azapi` Terraform | `runpod/runpod` `~> 2.0` | Built on REST API v2. Run both providers in one configuration during transition. |

GPU map (Azure size: GPUs, then Runpod GPU type ID, then Serverless pool):

| Azure size | GPUs | Runpod `gpu.id` | Pool |
| --- | --- | --- | --- |
| `Standard_NC4as_T4_v3`, `NC8as`, `NC16as` | 1 x T4 16 GB | `NVIDIA RTX A4000`, `NVIDIA RTX 2000 Ada Generation`, or `NVIDIA L4` | `AMPERE_16`, `AMPERE_24` |
| `Standard_NC64as_T4_v3` | 4 x T4 | Count 4 of a 16 GB type, or fewer larger GPUs | `AMPERE_16` |
| `Standard_NC24ads_A100_v4`, `NC48ads`, `NC96ads` | 1, 2, 4 x A100 80 GB | `NVIDIA A100 80GB PCIe`, `NVIDIA A100-SXM4-80GB` | `AMPERE_80` |
| `Standard_NC40ads_H100_v5`, `NC80adis` | 1, 2 x H100 94 GB | `NVIDIA H100 NVL` | `ADA_80_PRO` |
| `Standard_ND96amsr_A100_v4` | 8 x A100 80 GB | `NVIDIA A100-SXM4-80GB` | `AMPERE_80` |
| `Standard_ND96isr_H100_v5` | 8 x H100 80 GB | `NVIDIA H100 80GB HBM3` | `ADA_80_PRO` |
| `Standard_ND96isr_H200_v5` | 8 x H200 141 GB | `NVIDIA H200` | `HOPPER_141` |
| `Standard_ND96isr_MI300X_v5` | 8 x MI300X | `AMD Instinct MI300X OAM` | Pods |
| NC RTX PRO 6000 BSE v6 | Full or fractional, 24/48/96 GB | `NVIDIA RTX PRO 6000 Blackwell Server Edition` and its MIG types | Pods |
| `Standard_NV*ads_A10_v5` | A10 24 GB, full or fractional | 24 GB type such as `NVIDIA L4` (Linux compute only) | `AMPERE_24`, `ADA_24` |

Runpod lists no T4 or A10, so those rows are memory matches. Read live stock with
`runpodctl gpu list` or `GET /v2/catalog/gpus` before choosing. Choose by fit, not price.

## Field map

| Azure field | REST v2 | `runpodctl` | Terraform |
| --- | --- | --- | --- |
| VM `size`, `instance_type` | `gpu.id` + `gpu.count` (Pod), `gpu.pools` + `gpu.count` (endpoint) | `--gpu-id`, `--gpu-count` | `gpu_type_id`, `gpu_count`, `gpu_pools` |
| `location` | `dataCenterIds` | `--data-center-ids` | `data_center_ids` |
| image, AML `environment` | `image` | `--image` | `image` |
| `custom_data`, job `command` | `cmd` / `entrypoint` / `args` | `--docker-args` | `args` |
| `environment_variables`, `--env-vars` | `env` | `--env` | `env` |
| OS disk | `disk` | `--container-disk-in-gb` | `disk` |
| Data disk | `mounts.network[]`, `mounts.persistent` | `--network-volume-id`, `--volume-in-gb` | `network_volumes`, `persistent_volume` |
| NSG rule, `--target-port`, `scoring_route.port` | `ports` (+ `PORT`, `PORT_HEALTH` env on load balancers) | `--ports` | `ports` |
| `instance_count`, `--min-replicas`, `--max-replicas` | `workers.min`, `workers.max` | `--workers-min`, `--workers-max` | `workers_min`, `workers_max` |
| Azure Monitor autoscale, HTTP scale rule | `scaling.type` `QUEUE_DELAY` or `REQUEST_COUNT` | `--scale-by`, `--scale-threshold` | `scaling_type`, `scaling_value` |
| `request_timeout_ms` (max 180000) | `timeout` (ms) | `--execution-timeout` (s) | `timeout` |
| `liveness_route`, `readiness_route` | `/ping` or `HEALTH_CHECK_PATH` env | n/a | `env` |
| ACR credentials | `registry` | `--registry-auth-id` | `registry` |
| endpoint kind | `type`: `QUEUE` or `LOAD_BALANCER` (required, fixed at create) | Queue only | `endpoint_type` |
| CUDA / driver version | `gpu.minCudaVersion` | `--min-cuda-version` | `min_cuda_version` |

`runpodctl serverless create` creates queue endpoints. Create load-balancing endpoints with
`POST /v2/serverless`, the MCP `create-endpoint` tool, Terraform, or the console. For exact flags,
check `runpodctl pod create --help` and `runpodctl serverless create --help`
([runpodctl skill](../../runpodctl/SKILL.md)).

## Code translation

Scoring script to handler:

```python
# Azure: score.py
import json, os, torch

def init():
    global model
    model = torch.jit.load(os.path.join(os.getenv("AZUREML_MODEL_DIR"), "model.pt"), map_location="cuda").eval()

def run(raw_data):
    data = json.loads(raw_data)["data"]
    with torch.no_grad():
        return model(torch.tensor(data, device="cuda")).tolist()
```

```python
# Runpod: handler.py
import os, runpod, torch

model = torch.jit.load(os.path.join(os.getenv("MODEL_DIR", "/models"), "model.pt"), map_location="cuda").eval()

def handler(job):
    data = job["input"]["data"]          # already parsed, no json.loads
    with torch.no_grad():
        return model(torch.tensor(data, device="cuda")).tolist()

runpod.serverless.start({"handler": handler})
```

```dockerfile
FROM runpod/pytorch:1.0.3-cu1281-torch291-ubuntu2404
RUN pip install --no-cache-dir --break-system-packages --ignore-installed cryptography runpod
COPY model/ /models/
COPY handler.py /handler.py
CMD ["python3", "-u", "/handler.py"]
```

Get the model files with `az ml model download --name NAME --version N --download-path ./model`.
Build with `docker build --platform linux/amd64`.

Custom container or Container Apps app to load-balancing endpoint: keep the server, then

- serve `GET /ping` (200 healthy, 204 initializing), or set env `HEALTH_CHECK_PATH` to the existing readiness path;
- set env `PORT` and `PORT_HEALTH` to the server port and list it in `ports` (`"8000/http"`);
- create with `"type": "LOAD_BALANCER"` and `"scaling": {"type": "REQUEST_COUNT", "requestCount": N}`.

GPU VM with cloud-init to Pod: package installs go in the Dockerfile, the final command goes in
`CMD` or `--docker-args`, the data disk becomes a network volume at `/workspace`.

AML command job to SDK task:

```python
import runpod
app = runpod.App("training")
ckpt = runpod.NetworkVolume("checkpoints", size=100)

@app.task(gpu="H100", mounts={"/checkpoints": ckpt}, dependencies=["torch"])
def train(epochs: int = 10):
    ...
    return {"epochs": epochs}
```

Terraform, Container Apps GPU app to endpoint:

```hcl
resource "runpod_registry" "acr" {
  name     = "acr-myregistry"
  username = var.acr_pull_username   # ACR token name or service principal app ID
  password = var.acr_pull_password
}

resource "runpod_template" "api" {
  name          = "gpu-api"
  image         = "myregistry.azurecr.io/gpu-api:v1"
  registry      = runpod_registry.acr.id
  serverless    = true
  disk          = 20
  ports         = ["8000/http"]
  start_ssh     = false
  start_jupyter = false
  env           = { PORT = "8000", PORT_HEALTH = "8000" }
}

resource "runpod_serverless_endpoint" "api" {
  name          = "gpu-api"
  template_id   = runpod_template.api.id
  endpoint_type = "LOAD_BALANCER"
  gpu_pools     = ["AMPERE_16"]
  scaling_type  = "REQUEST_COUNT"
  scaling_value = 4
  workers_min   = 0
  workers_max   = 3
}
```

GPU VM to `runpod_pod`: `size` becomes `gpu_type_id` + `gpu_count`, `custom_data` becomes `image` +
`args`, `admin_ssh_key` becomes `start_ssh = true`, `azurerm_managed_disk` becomes
`runpod_network_volume` + `network_volumes = [{ volume_id, path }]`. NIC, public IP, NSG, VNet and
subnet resources have no counterpart: use `ports`. Keep `provider "azurerm" { features {} }` and add
`provider "runpod" {}` (reads `RUNPOD_API_KEY`) in the same configuration. Confirm argument names
against the Terraform Registry docs for `runpod/runpod` before writing HCL.

## Data

| Source | Destination | Method |
| --- | --- | --- |
| Blob Storage, hybrid | Stay in Blob | SAS URL or service principal secret as a Runpod secret, env value `{{ RUNPOD_SECRET_<name> }}` |
| Blob Storage, moved | Network volume | `azcopy sync "https://ACCOUNT.blob.core.windows.net/CONTAINER/PATH?SAS" /workspace/PATH` inside a Pod |
| Blob Storage, moved | Network volume | Console Cloud Sync (Azure Blob: account name + account key) |
| Managed Disk, Azure Files, NetApp, Lustre | Network volume | From an Azure VM that mounts it: `runpodctl network-volume upload VOLUME_ID ./dir dir` (runpodctl v3.1.0+; check `runpodctl network-volume --help`; S3 API keys, S3-enabled data center), or `aws s3 sync` against `https://s3api-DC.runpod.io/` |
| BlobFuse mount, read-mostly, multi data center | Global volume | Copy from a Pod. Object-backed, limited POSIX. |
| AML registered model | Image, network volume, or cached model | `az ml model download`, then bake or copy |
| OS disk image | Container image | Rebuild as a Dockerfile |

Rules: create the network volume in the data center chosen from the GPU stock read, once. Network
volumes mount at `/workspace` on Pods and `/runpod-volume` on Serverless. Azure bills outbound data
transfer, so tell the user to budget for the one-time copy. Runpod does not charge ingress or
egress. Secret names cannot start with `runpod`. Rotated secrets apply at the next boot.

## Client and API call map

| Azure call | Runpod call |
| --- | --- |
| `POST SCORING_URI`, `Authorization: Bearer ENDPOINT_KEY`, body `{"data": ...}` | `POST https://api.runpod.ai/v2/ENDPOINT_ID/runsync`, `Authorization: Bearer RUNPOD_API_KEY`, body `{"input": {"data": ...}}`, result in `output` |
| `ml_client.online_endpoints.invoke(endpoint_name=, deployment_name=, request_file=)` | `runpod.Endpoint("ENDPOINT_ID").run_sync({...})` |
| `ml_client.batch_endpoints.invoke(...)` | `POST /v2/ENDPOINT_ID/run` with `"webhook"`, then `/status/JOB_ID` |
| Container Apps FQDN + own routes | `https://ENDPOINT_ID.api.runpod.ai/PATH` + `Authorization: Bearer RUNPOD_API_KEY` |
| `AzureOpenAI(azure_endpoint=, api_key=, api_version=)`, `model=DEPLOYMENT_NAME` | `OpenAI(base_url="https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1", api_key=RUNPOD_API_KEY)`, `model=MODEL_NAME` |
| `OpenAI(base_url="https://RESOURCE.openai.azure.com/openai/v1/")` | Same client, Runpod `base_url` and key |
| `az vm create` / `deallocate` / `delete` | `runpodctl pod create` / `stop` / `delete` |
| `az vm list -d` | `runpodctl pod list --all` |
| `az ml online-endpoint create` + `online-deployment create` | `runpodctl template create --serverless` + `runpodctl serverless create` |
| `az ml online-deployment get-logs`, `az containerapp logs show` | `runpodctl serverless logs ENDPOINT_ID` |
| `az ml online-endpoint update --traffic` | Two endpoints, client-side split |
| `az acr token create` / `az acr login` | `runpodctl registry create --password-stdin` |
| `azcopy sync` | `runpodctl network-volume upload` (v3.1.0+), or `azcopy` in a Pod |

Queue endpoint limits: `/run` payload 10 MB, `/runsync` 20 MB, `/runsync` waits 90 s by default.
Load-balancing limits: 30 MB payload, 5.5 min processing, 2 min wait for a worker. Check `status`
in the response body (`COMPLETED`, `FAILED`, `IN_QUEUE`, `IN_PROGRESS`, `CANCELLED`, `TIMED_OUT`).
vLLM routes: `/chat/completions`, `/completions`, `/models`. Code on the Responses API moves to
chat completions.

## Gaps: stop and ask the user

| Gap | Options |
| --- | --- |
| Model is a proprietary OpenAI GPT deployment | (a) keep the call on Azure, (b) move to an open-weight model on a Public Endpoint or vLLM and re-run evals |
| Workload reaches Azure resources over VNet, private endpoints, or NSG allow lists | (a) enable public endpoint + auth on the Azure resource, (b) keep that component on Azure behind an API, (c) user-run proxy |
| Code uses managed identity | (a) least-privilege service principal as Runpod secrets (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`), (b) scoped SAS token |
| ACR is private-endpoint only | (a) enable public access with a pull-only token, (b) mirror the image to another registry |
| Blue/green percentage split or mirror traffic | (a) rolling release on one endpoint, (b) two endpoints and a client or gateway split |
| Requests longer than the load-balancing 5.5 min limit, or must not drop | Use a queue endpoint |
| Spot VMs with eviction handling | (a) on-demand Pod, (b) Serverless. REST v2 and `runpodctl` create on-demand Pods |
| Windows, NV/NG VDI, Data Science VM on Windows | Stays on Azure |
| AKS workloads | (a) per-workload Pods or Serverless, (b) SkyPilot or dstack |
| Multi-node InfiniBand or Slurm jobs | Instant Cluster. Confirm stock with the user before planning dates |
| Compliance or residency requirement | Secure Cloud, `--country-code`, `--compliance`. Have the user confirm against Runpod's compliance page |
| Bicep or ARM as source of truth | (a) Terraform with the Runpod provider, (b) REST v2 from the pipeline |
| Azure Monitor alerts and dashboards on the endpoint | User ships logs and metrics to their own system |
| Large data move out of Azure | User approves the Azure outbound transfer cost and the target data center |

## Verify

1. Pod: `runpodctl pod get POD_ID` shows `runtimeStatus: running`. Run `nvidia-smi` and the real
   command. Read `runpodctl pod logs POD_ID`.
2. Queue endpoint: `POST /runsync` with a production-shaped payload returns `"status": "COMPLETED"`
   and an `output` matching the Azure response for the same input.
3. Load-balancing endpoint: poll `https://api.runpod.ai/v2/ENDPOINT_ID/health` until a worker is
   ready, then call the real route with the Bearer key. `GET /ping` returns 200.
4. OpenAI-compatible: `client.models.list()` then one chat completion against the Runpod base URL.
5. Private image: the worker starts. A pull failure shows in `runpodctl serverless logs ENDPOINT_ID`.
6. Data: file counts and sizes on the volume match the source before any Azure deletion.
7. Report cost: worker range, GPU pool, and that an idle Pod bills until stopped or deleted.

## Shut down Azure

Run only after the user explicitly approves each resource. Show the commands first.

```bash
az vm deallocate -g RG -n VM          # a stopped VM that is not deallocated still bills compute
az vm delete -g RG -n VM --yes
az ml online-endpoint delete --name ENDPOINT -g RG -w WS --yes     # deletes its deployments
az ml online-deployment delete --name DEPLOYMENT --endpoint-name ENDPOINT -g RG -w WS --yes
az ml compute stop --name INSTANCE -g RG -w WS
az ml compute delete --name COMPUTE -g RG -w WS --yes
az containerapp delete -g RG -n APP --yes
```

Then list what commonly remains and ask before deleting any of it: unattached managed disks
(``az disk list --query '[?managedBy==`null`].[id]' -o tsv``), snapshots (`az snapshot list`),
public IPs (`az network public-ip list`), dedicated GPU workload profiles, compute clusters with a
minimum node count above zero, ACR repositories (`az acr repository delete`), Log Analytics
workspaces (`az monitor log-analytics workspace list`), storage accounts, Azure OpenAI or Foundry
deployments, and reservations or savings plans (commitments that outlive the resources). Never
delete storage or rotate credentials that the Runpod side still reads.
