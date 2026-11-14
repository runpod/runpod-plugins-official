---
concepts: [serverless-endpoint, pod, network-volume, global-volume, instant-cluster, runpod-secret, endpoint-autoscaling, gpu-pool]
---
# Migrate from CoreWeave to Runpod

Scope: move workloads from CoreWeave Kubernetes Service (CKS), SUNK (Slurm on Kubernetes),
AI Object Storage, Distributed File Storage and CoreWeave Inference to Runpod Pods, Serverless
endpoints, Instant Clusters and network volumes. Runpod has no Kubernetes API: every
Kubernetes object is translated into a Runpod resource created through REST v2, `runpodctl`,
the Runpod SDK or Terraform. The customer-facing guide is `migrate/coreweave` in the docs.

Sources: CoreWeave docs, checked 2026-11-14:
[CKS](https://docs.coreweave.com/products/cks), [Node Pool reference](https://docs.coreweave.com/products/cks/reference/node-pool),
[GPU instances](https://docs.coreweave.com/platform/instances/gpu-instances), [AI Object Storage](https://docs.coreweave.com/products/storage/object-storage/get-started-caios),
[Distributed File Storage](https://docs.coreweave.com/products/storage/distributed-file-storage/manage-volumes), [Expose a Service](https://docs.coreweave.com/products/networking/ingress-service/expose-service-dns),
[SUNK](https://docs.coreweave.com/products/sunk), [Inference](https://docs.coreweave.com/products/inference),
[Terraform provider](https://docs.coreweave.com/platform/terraform), [cwic](https://github.com/coreweave/cwic).

## Detect

| Signal | What it means | Lands on |
| --- | --- | --- |
| `apiVersion: compute.coreweave.com/v1alpha1` with `kind: NodePool` | CKS Node Pool (whole bare-metal nodes) | GPU type and count on each Pod or endpoint |
| `node.coreweave.cloud/type` in `nodeSelector` or `nodeAffinity` | Workload pinned to a CoreWeave instance type | `gpu.id` (Pod) or `gpu.pools` (Serverless) |
| `gpu.nvidia.com/class`, `gpu.nvidia.com/model` in a manifest | GPU selection by label | Same as above |
| `gd-8x[a-z0-9]+-i128`, `b200-8x`, `b300-8x`, `rtxp6000-8x`, `gb[23]00-4x` | CoreWeave instance type ID | GPU map below |
| `storageClassName: shared-vast` | Distributed File Storage PVC (`ReadWriteMany`) | Network volume |
| `service.beta.kubernetes.io/coreweave-load-balancer-type` | Public or private `LoadBalancer` Service | Endpoint URL or Pod port |
| `service.beta.kubernetes.io/external-hostname`, `\.coreweave\.app` | Public DNS name for a Service | Endpoint URL or Pod proxy URL |
| `kind: HorizontalPodAutoscaler`, `kind: ScaledObject`, `serving.knative.dev` | Autoscaled inference | Serverless endpoint |
| `kind: Job`, `kind: CronJob` with `nvidia.com/gpu` | GPU batch work | Queue endpoint or `@app.task` |
| `apiVersion: sunk.coreweave.com/v1alpha1`, `kind: SunkCluster`, `kind: NodeSet`, `kind: SlurmCluster` | SUNK Slurm cluster | Instant Cluster, `type: SLURM` |
| `cwobject\.com`, `cwlota\.com` | AI Object Storage endpoint (LOTA is in-cluster only) | Network volume (S3-compatible API) or global volume |
| `cwinference\.com`, `api.coreweave.com/v1alpha1/inference` | Dedicated Inference gateway or API | Load-balancing endpoint or vLLM worker |
| `api\.inference\.wandb\.ai` | CoreWeave Serverless Inference (per-token) | Public Endpoint |
| `CW-SECRET-`, `COREWEAVE_API_TOKEN` | CoreWeave API token | `RUNPOD_API_KEY` |
| `cwic ` in scripts or CI | CoreWeave Intelligent CLI | `runpodctl` |
| `source = "coreweave/coreweave"`, `resource "coreweave_` | CoreWeave Terraform provider | `runpod/runpod` `~> 2.0` |
| `\.k8s\.[a-z0-9-]+\.coreweave\.com` in a kubeconfig | CKS API server | No equivalent: remove |
| `svc\.cluster\.local`, `KUBERNETES_SERVICE_HOST`, `load_incluster_config` | In-cluster addressing or Kubernetes API use | Rewrite: endpoint URL, `POD_ID.runpod.internal`, or Runpod API |
| `kind: DaemonSet`, `kind: CustomResourceDefinition`, operator charts | Cluster-level components | Gap: stop and ask |

## Product map

| CoreWeave | Runpod | Notes |
| --- | --- | --- |
| CKS cluster, VPC | None | Resources are created directly. |
| Node Pool | GPU type and count per Pod or worker | CoreWeave nodes are typically 8 GPUs; request only what the container used. |
| Deployment + Service + HPA/KEDA/Knative | Serverless endpoint | `LOAD_BALANCER` keeps the HTTP server; `QUEUE` needs a handler. |
| Deployment or StatefulSet, one replica | Pod | One container per Pod. |
| Job, CronJob | Queue endpoint, or `@app.task` (ephemeral Pod per call) | The schedule stays in the user's scheduler. |
| Dedicated Inference | Load-balancing endpoint, or vLLM worker (`/openai/v1`) | Dedicated Inference has `min >= 1`; Serverless scales to zero. |
| Serverless Inference | Public Endpoints | Check the model is in the catalog. |
| SUNK | Instant Cluster with Slurm | Managed Slurm runs on official Runpod PyTorch images. |
| AI Object Storage | Network volume + S3-compatible API, or global volume | Bucket policies, versioning and lifecycle rules do not carry over. |
| Distributed File Storage (`shared-vast`) | Network volume | Pinned to one data center. |
| `emptyDir`, Local Storage | Container disk | Ephemeral. |
| `LoadBalancer` Service, Ingress | `https://ENDPOINT_ID.api.runpod.ai`, `https://POD_ID-PORT.proxy.runpod.net`, or a TCP port | Proxy URL is public, unauthenticated, 100 s timeout. |
| Private Services, cluster DNS | Global networking, `POD_ID.runpod.internal` | NVIDIA GPU Pods, supported data centers, 100 Mbps. |
| Kubernetes Secret | Runpod secret, `{{ RUNPOD_SECRET_name }}` | `POST /v2/account/secrets`. |
| ConfigMap | `env`, or files on a volume | |
| Availability Zone (`US-EAST-04A`) | Data center ID (`US-KS-2`) | |
| Reserved, On-Demand, Spot plans | On-demand, per-second | Reserved or committed capacity: Runpod sales. |

GPU map (instance type to Runpod GPU type ID, Serverless pool):

| CoreWeave | Runpod GPU type ID | Pool |
| --- | --- | --- |
| `gd-8xh100ib-i128` | `NVIDIA H100 80GB HBM3`, `NVIDIA H100 PCIe` | `ADA_80_PRO` |
| `gd-8xh200ib-i128` | `NVIDIA H200` | `HOPPER_141` |
| `b200-8x` | `NVIDIA B200` | read `pool` from `GET /v2/catalog/gpus` |
| `b300-8x` | `NVIDIA B300 SXM6 AC` | read `pool` from `GET /v2/catalog/gpus` |
| `gd-8xl40s-i128`, `gd-8xl40-i128` | `NVIDIA L40S`, `NVIDIA L40` | `ADA_48_PRO` |
| `gd-8xa100-i128` | `NVIDIA A100-SXM4-80GB`, `NVIDIA A100 80GB PCIe` | `AMPERE_80` |
| `rtxp6000-8x`, `rtxp6000-8x-v2` | `NVIDIA RTX PRO 6000 Blackwell Server Edition` | read `pool` from `GET /v2/catalog/gpus` |
| `gb200-4x`, `gb300-4x`, `gb300-4x-e`, `gd-1xgh200` | Pick by VRAM; ask the user | |

Choose by fit for the workload (VRAM, throughput). Check live stock before proposing a type:
`runpodctl gpu list`, or `GET /v2/catalog/gpus?include=AVAILABILITY&product=SERVERLESS`
(`POD`, `CLUSTER`). Stock varies by data center; never state that capacity is guaranteed. See
[gpu-selection](../../runpod-usage/reference/gpu-selection.md).

## Field map

Container spec to REST v2 (`POST /v2/pods`, `POST /v2/serverless`, `POST /v2/templates`):

| Kubernetes field | REST v2 | `runpodctl` | Terraform |
| --- | --- | --- | --- |
| `image` | `image` | `--image` | `image` |
| `imagePullSecrets` | `registry` (ID from `/v2/registries`) | `--registry-auth-id` | `registry` |
| `command` | `entrypoint` (array) | `template create --docker-entrypoint` | `runpod_template.docker_entrypoint` |
| `args` | `cmd` (array) | `template create --docker-start-cmd` | `runpod_template.args` (string) |
| `env[].value`, `envFrom.configMapRef` | `env` (object) | `--env` (JSON on Pods and templates) | `env` |
| `env[].valueFrom.secretKeyRef` | `env` value `{{ RUNPOD_SECRET_name }}` | same | same |
| `ports[].containerPort` | `ports` (`"8000/http"`, `"22/tcp"`) | `--ports` | `ports` |
| `resources.limits["nvidia.com/gpu"]` | `gpu.count` | `--gpu-count` | `gpu_count` |
| `nodeSelector` instance type | `gpu.id` (Pod), `gpu.pools` (endpoint) | `--gpu-id` | `gpu_type_id`, `gpu_pools` |
| PVC `volumeMounts` | Pod: `mounts.network[{volumeId, path}]`. Endpoint: `mounts.network[{volumeId}]` | `--network-volume-id` | `network_volumes` |
| `emptyDir` | `disk` (GB) | `--container-disk-in-gb` | `disk` |
| `readinessProbe.httpGet.path` | env `HEALTH_CHECK_PATH` (load-balancing) | | |
| Service `targetPort` | `ports` + env `PORT` and `PORT_HEALTH` (load-balancing) | | `ports` |
| HPA `minReplicas`, `maxReplicas` | `workers.min`, `workers.max` | `--workers-min`, `--workers-max` | `workers_min`, `workers_max` |
| HPA or KEDA target | `scaling: {type: REQUEST_COUNT, requestCount}` or `{type: QUEUE_DELAY, queueDelay}` | `--scale-by`, `--scale-threshold` | `scaling_type`, `scaling_value` |
| KEDA `cooldownPeriod` | `workers.idleTimeout` (seconds) | `--idle-timeout` | `idle_timeout` |
| Job `activeDeadlineSeconds` | `timeout` (ms), or per request `policy.executionTimeout` | `--execution-timeout` (seconds) | `timeout` |
| Job `parallelism` | `workers.max` | `--workers-max` | `workers_max` |
| Zone, topology constraints | `dataCenterIds` | `--data-center-ids` | `data_center_ids` |
| GPU driver version on the Node Pool | `gpu.minCudaVersion` | `--min-cuda-version` | `min_cuda_version` |

Rules:
- Endpoint `type` is required and fixed at creation: `QUEUE` or `LOAD_BALANCER`.
  `runpodctl serverless create` creates queue endpoints; create load-balancing endpoints with
  `POST /v2/serverless`, the MCP `create-endpoint` tool, or Terraform `endpoint_type`.
- `LOAD_BALANCER` endpoints scale on `REQUEST_COUNT`.
- Volume paths: `/workspace` on Pods by default (REST `path` is explicit), `/runpod-volume`
  on every Serverless worker. Rewrite paths that pointed at the PVC `mountPath`.
- Images are `linux/amd64`.
- For exact flags, check `runpodctl pod create --help`, `runpodctl serverless create --help`
  and `runpodctl template create --help`.

Terraform resource map:

| CoreWeave / Kubernetes provider | Runpod provider |
| --- | --- |
| `coreweave_networking_vpc`, `coreweave_cks_cluster` | None |
| `kubernetes_deployment` + `kubernetes_service` + HPA | `runpod_serverless_endpoint` (+ `runpod_template` for the command) |
| `kubernetes_deployment` / `kubernetes_stateful_set`, one replica | `runpod_pod` |
| `kubernetes_persistent_volume_claim` | `runpod_network_volume` |
| `coreweave_object_storage_bucket` | `runpod_network_volume` or `runpod_global_volume` |
| `coreweave_object_storage_bucket_policy`, `_versioning`, `_lifecycle_configuration`, `_settings` | None |
| `coreweave_inference_gateway`, `coreweave_inference_deployment`, `coreweave_inference_capacity_claim` | `runpod_serverless_endpoint` |
| `coreweave_container_registry_*` | `runpod_registry` (pull credential for an external registry) |
| `kubernetes_secret` | Runpod secret through REST, referenced in `env` |
| `SunkCluster` manifest | `runpod_cluster`, `type = "SLURM"` |

Argument names come from the
[Runpod provider docs](https://registry.terraform.io/providers/runpod/runpod/latest/docs).
Apply the Runpod configuration next to the CoreWeave one; do not move state between providers.

## Code translation

### HTTP inference Deployment to a load-balancing endpoint

Before (Deployment container, Service on port 80 to 8000, PVC at `/models`):

```yaml
containers:
  - name: vllm-server
    image: registry.example.com/acme/llm-server:1.4.2
    command: ["vllm", "serve"]
    args: ["meta-llama/Llama-3.1-8B-Instruct", "--host", "0.0.0.0", "--port", "8000", "--download-dir", "/models"]
    env:
      - name: HF_TOKEN
        valueFrom: { secretKeyRef: { name: hf-token-secret, key: api_token } }
    ports: [{ containerPort: 8000 }]
    readinessProbe: { httpGet: { path: /health, port: 8000 } }
    resources: { limits: { nvidia.com/gpu: 1 } }
nodeSelector: { node.coreweave.cloud/type: gd-8xh100ib-i128 }
```

After:

```bash
curl -s -X POST https://api.runpod.io/v2/serverless \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"llama-3-1-8b","type":"LOAD_BALANCER",
       "image":"registry.example.com/acme/llm-server:1.4.2","registry":"REGISTRY_AUTH_ID",
       "entrypoint":["vllm","serve"],
       "cmd":["meta-llama/Llama-3.1-8B-Instruct","--host","0.0.0.0","--port","8000","--download-dir","/runpod-volume/models"],
       "ports":["8000/http"],"disk":40,
       "env":{"PORT":"8000","PORT_HEALTH":"8000","HEALTH_CHECK_PATH":"/health","HF_TOKEN":"{{ RUNPOD_SECRET_hf_token }}"},
       "gpu":{"pools":["ADA_80_PRO"],"count":1,"minCudaVersion":"12.8"},
       "mounts":{"network":[{"volumeId":"NETWORK_VOLUME_ID"}]},
       "workers":{"min":0,"max":4,"idleTimeout":60},
       "scaling":{"type":"REQUEST_COUNT","requestCount":4},"timeout":300000}'
```

Read the invoke URL from `requestUrls.base` in the response. Set `ports`, `PORT` and
`PORT_HEALTH` to the same port. The health path returns `200` when ready and `204` while
initializing. Limits: 5.5 min processing per request, 30 MB payload, requests are dropped when
all workers are busy. See
[golden path 14](../../runpod/golden-paths/14-load-balancing-endpoint.md).

### Same Deployment to a Pod

`POST /v2/pods` with the same `image`, `registry`, `entrypoint`, `cmd`, `env` and `disk`, plus
`"ports":["8000/http","22/tcp"]`, `"gpu":{"id":"NVIDIA H100 80GB HBM3","count":1,"minCudaVersion":"12.8"}`,
`"dataCenterIds":["US-KS-2"]` and `"mounts":{"network":[{"volumeId":"NETWORK_VOLUME_ID","path":"/models"}]}`.
The explicit mount `path` keeps `--download-dir /models` unchanged. Reach it at
`https://POD_ID-8000.proxy.runpod.net`. Poll `runtimeStatus` until `running`.

### Job to a queue endpoint

Before: `command: ["python", "embed.py"]`, `args: ["--input", "...", "--output", "..."]`.

After (`handler.py`, added to the same image with `CMD ["python", "-u", "handler.py"]`):

```python
import subprocess
import runpod

def handler(job):
    args = job["input"]
    result = subprocess.run(
        ["python", "embed.py", "--input", args["input"], "--output", args["output"]],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])
    return {"output": args["output"]}

runpod.serverless.start({"handler": handler})
```

```bash
runpodctl template create --name embedder-worker --serverless \
  --image registry.example.com/acme/embedder-worker:2.1.0 --container-disk-in-gb 20
runpodctl serverless create --name embedder --template-id TEMPLATE_ID \
  --gpu-id ADA_48_PRO --workers-min 0 --workers-max 8 --execution-timeout 3600
curl -s -X POST https://api.runpod.ai/v2/ENDPOINT_ID/run \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"input":{"input":"/runpod-volume/shards/0001.jsonl","output":"/runpod-volume/embeddings/0001.parquet"}}'
```

### Job to an SDK task

`@app.task(gpu="L40S", image="IMAGE", mounts={"/data": runpod.NetworkVolume("datasets", size=200)})`
on a function that runs the same command provisions one Pod per call and terminates it on
return. Call it with `.remote(...)` from a `@runpod.local_entrypoint` and run
`rp flash dev main.py`. See [runpod-flash](../../runpod-flash/SKILL.md).

### SUNK to a Slurm cluster

```bash
curl -s -X POST https://api.runpod.io/v2/clusters \
  -H "Authorization: Bearer $RUNPOD_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"slurm-train","type":"SLURM",
       "image":"runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04",
       "compute":{"gpuTypeId":"NVIDIA H100 80GB HBM3","gpuCountPerPod":8,"podCount":4},
       "mounts":{"network":[{"volumeId":"NETWORK_VOLUME_ID","path":"/workspace"}]},"startSsh":true}'
```

`sbatch`, `squeue` and `sinfo` run on the controller node. Slurm config lives in
`/etc/slurm/slurm.conf` and `/etc/slurm/gres.conf`. Check Instant Cluster stock for the GPU
type before proposing dates; clusters above 8 nodes go through Runpod sales.

## Data

| Source | Destination | Method |
| --- | --- | --- |
| AI Object Storage bucket | Network volume | Pod with the volume mounted: `aws s3 sync s3://BUCKET /workspace/DIR --profile cw` |
| AI Object Storage bucket | Network volume, no Pod | Stage locally, then `runpodctl network-volume upload VOLUME_ID ./stage DIR` (runpodctl v3.1.0+; check `runpodctl network-volume --help`) or `aws s3 sync` to the S3-compatible API |
| AI Object Storage bucket | Global volume | Pod with the global volume mounted, then sync to the mount (the S3-compatible API covers network volumes only) |
| `shared-vast` PVC | Network volume | Kubernetes Job in CKS that mounts the PVC and runs `aws s3 sync /data s3://VOLUME_ID/DIR` against the Runpod S3-compatible API, or `rsync` over SSH to a Pod |
| Hugging Face model pulled at startup | Cached model on the endpoint | `--model-reference`; see [model caching](../../runpodctl/reference/model-caching.md) |

CoreWeave side (from its docs): endpoint `https://cwobject.com` outside the cluster,
`http://cwlota.com` inside a CKS cluster only; virtual-hosted addressing is required.

```bash
aws configure --profile cw
aws configure set endpoint_url https://cwobject.com --profile cw
aws configure set s3.addressing_style virtual --profile cw
```

Runpod side: `https://s3api-DATACENTER.runpod.io/`, bucket = network volume ID,
`--region` = data center ID, credentials = S3 API key (separate from the API key).

```bash
aws s3 sync ./stage s3://NETWORK_VOLUME_ID/models --profile runpod \
  --region US-KS-2 --endpoint-url https://s3api-us-ks-2.runpod.io/
```

- Create the network volume in a data center that has the target GPU and the S3-compatible
  API: `runpodctl network-volume create --name models --size 200 --data-center-id US-KS-2`.
- `aws s3 sync` to the Runpod S3-compatible API is limited above 10,000 files: batch it or
  sync inside a Pod.
- A network volume has a fixed size (10 to 4096 GB, grow only). Size it from
  `aws s3 ls s3://BUCKET --recursive --summarize --profile cw`.
- Path equivalence: `/workspace/x` (Pod) = `/runpod-volume/x` (Serverless) =
  `s3://VOLUME_ID/x`.

See [storage](../../runpod-usage/reference/storage.md).

## Client and API call map

| CoreWeave call | Runpod call |
| --- | --- |
| `http://NAME.ORG_ID-CLUSTER.coreweave.app/PATH` | `https://ENDPOINT_ID.api.runpod.ai/PATH` + `Authorization: Bearer RUNPOD_API_KEY` |
| `https://GATEWAY.ORG_ID.gw.cwinference.com/v1` (OpenAI client `base_url`) | `https://ENDPOINT_ID.api.runpod.ai/v1`, or `https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1` (vLLM worker) |
| `https://api.inference.wandb.ai/v1` | `https://api.runpod.ai/v2/MODEL_SLUG/openai/v1` (Public Endpoint) |
| `http://NAME.NAMESPACE.svc.cluster.local:PORT` | Endpoint URL, or `http://POD_ID.runpod.internal:PORT` (global networking) |
| `BatchV1Api().create_namespaced_job(...)` | `POST https://api.runpod.ai/v2/ENDPOINT_ID/run` with `{"input": {...}}` |
| `read_namespaced_job_status` | `GET https://api.runpod.ai/v2/ENDPOINT_ID/status/JOB_ID` |
| `kubectl logs` | `GET /v2/pods/POD_ID/logs`, `GET /v2/serverless/ENDPOINT_ID/workers/WORKER_ID/logs` |
| `kubectl scale deploy` / HPA patch | `PATCH /v2/serverless/ENDPOINT_ID` (`workers`) |
| `kubectl apply -f pvc.yaml` | `POST /v2/network-volumes` |
| `kubectl create secret` | `POST /v2/account/secrets` |
| `POST /v1alpha1/inference/deployments` | `POST /v2/serverless` |
| `cwic auth login`, `COREWEAVE_API_TOKEN` | `RUNPOD_API_KEY`, `rp login` |
| `kubectl get nodepool`, `cwic node get` | `runpodctl gpu list`, `GET /v2/catalog/gpus` |
| S3 client at `cwobject.com` | Mounted path, or S3 client at `https://s3api-DATACENTER.runpod.io/` |

Job states: `IN_QUEUE`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`.
`/run` results are kept 30 minutes; use a `webhook` or write outputs to a volume. Clients of
scale-to-zero endpoints need retries for cold starts. See
[endpoint-workflows](../../runpod-usage/reference/endpoint-workflows.md).

## Gaps: stop and ask the user

| Found | Why it needs a decision | Options |
| --- | --- | --- |
| DaemonSet, operator, CRD, admission webhook, Helm chart with cluster-scoped objects | Depends on the Kubernetes API | Rebuild against the Runpod API; drop it; keep that part on Kubernetes |
| Multi-container Pod, sidecar, init container | One container per Pod or worker | Merge into one image with a supervisor; separate Pod on global networking; one-time copy for init downloads |
| Deployment with more than one replica and no HTTP or queue interface | Pods do not autoscale | Add a handler or HTTP server and use Serverless; run N Pods |
| VPC CIDRs, NetworkPolicy, Direct Connect, private-only Services, `loadBalancerSourceRanges` | Runpod has global networking between Pods, with generated public URLs | App-level auth; global networking for Pod-to-Pod; keep a gateway in front |
| UDP ports | Pods expose HTTP and TCP | Change protocol; keep that service elsewhere |
| Custom hostname and TLS (cert-manager, Ingress hosts) | Runpod serves generated hostnames | Put the user's DNS proxy or API gateway in front |
| Bucket policies, versioning, lifecycle rules, workload identity federation | Network volumes are file systems | Keep an external object store; accept plain files |
| Data needed in several data centers | A network volume is in one data center | One volume per data center with a copy each; global volume |
| CronJob | Schedule lives outside Runpod | CI schedule, Airflow, cron calling `/run` |
| Request longer than 5.5 min or payload above 30 MB on HTTP inference | Load-balancing limits | Queue endpoint; Pod with a TCP port |
| GB200, GB300, GH200 instance types, or images built for a non-x86 architecture | Images are `linux/amd64`; map GPUs by VRAM | Rebuild the image; pick a GPU by VRAM; Runpod sales |
| SUNK with custom `NodeSet` images, SCIM users, accounting, more than 8 nodes | Managed Slurm uses Runpod PyTorch images | Managed Slurm + install at job start; unmanaged Slurm on a custom image; Runpod sales |
| Reserved Instances or a committed contract on CoreWeave | Billed for the term regardless of usage | User confirms contract end date before cutover; Runpod sales for committed capacity |
| Spot Node Pools | REST v2 and `runpodctl` create on-demand Pods | On-demand; Serverless for bursty work |

## Verify

1. Endpoint: `GET https://api.runpod.ai/v2/ENDPOINT_ID/health` shows a ready worker, then
   send one production-shaped request from outside Runpod and compare the response with the
   CoreWeave response for the same input.
2. Pod: `runpodctl pod get POD_ID --output json` shows `runtimeStatus: running`, then
   `curl https://POD_ID-PORT.proxy.runpod.net/PATH`.
3. Data: compare file counts and total size between the bucket or PVC and the volume
   (`aws s3 ls ... --recursive --summarize` on both sides, or `du -sh` on the mount).
4. Measure one cold start and several warm requests; report both.
5. Slurm: `sinfo` lists every node; run a one-node and an all-node `srun nvidia-smi`.
6. Confirm cost guards: `workers.min` is `0` unless the user asked for warm workers, idle
   test Pods are deleted, `runpodctl pod list --all` and `runpodctl serverless list` match
   the plan.

## Shut down CoreWeave

Run only after explicit user approval, and after the user confirms the data copy and any
reserved-capacity contract terms. Show the commands first.

```bash
kubectl delete -f MANIFESTS_DIR/                  # workloads, Services, HPAs
kubectl delete pvc PVC_NAME -n NAMESPACE          # after the copy is verified
kubectl delete nodepool NODE_POOL_NAME            # nodes are removed without waiting for workloads
cwic inference deployment delete DEPLOYMENT_ID    # deployments before gateways
cwic inference gateway delete GATEWAY_ID
aws s3 rm s3://BUCKET_NAME --recursive --profile cw
aws s3api delete-bucket --bucket BUCKET_NAME --profile cw   # only empty buckets delete
terraform destroy                                 # in the CoreWeave configuration, if used
```

- Delete each CKS cluster in the Cloud Console (Clusters page; state must be Running, Failed
  or Preempted).
- Versioned buckets need object versions and delete markers removed first.
- Deleted Distributed File Storage volumes keep data for about 24 hours by default.
- Delete unused API access tokens and Object Storage access keys in the Cloud Console.
- Deleting resources does not end a Reserved Instance term.
