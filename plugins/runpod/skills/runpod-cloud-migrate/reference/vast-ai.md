---
concepts: [pod, serverless-endpoint, serverless-handler, network-volume, global-volume, exposed-port, spot-pod, file-transfer]
---
# Migrate from Vast.ai to Runpod

Scope: Vast.ai instances (on-demand, interruptible, reserved), templates, local volumes, Cloud Sync, Serverless (endpoint, workergroup, PyWorker), Deployments (beta), and automation written against the `vastai` CLI, the `vastai` Python package and the Vast REST API. Targets: Runpod Pods, Serverless queue and load-balancing endpoints, Runpod SDK apps, network volumes, global volumes, `runpodctl` and REST v2 (`https://api.runpod.io/v2`).

Sources: Vast.ai docs, checked 2026-11-14:
[runpod-to-vast](https://docs.vast.ai/examples/migrations/runpod-to-vast),
[docker-environment](https://docs.vast.ai/guides/instances/docker-environment),
[networking](https://docs.vast.ai/guides/instances/connect/networking),
[launch modes](https://docs.vast.ai/guides/instances/connect/overview),
[instance types](https://docs.vast.ai/guides/instances/choosing/instance-types),
[volumes](https://docs.vast.ai/guides/instances/storage/volumes),
[data movement](https://docs.vast.ai/guides/instances/storage/data-movement),
[cloud sync](https://docs.vast.ai/guides/instances/storage/cloud-sync),
[create instance](https://docs.vast.ai/cli/reference/create-instance),
[search offers](https://docs.vast.ai/cli/reference/search-offers),
[show instances](https://docs.vast.ai/cli/reference/show-instances),
[serverless architecture](https://docs.vast.ai/guides/serverless/architecture),
[PyWorkers](https://docs.vast.ai/guides/serverless/creating-new-pyworkers),
[endpoint parameters](https://docs.vast.ai/guides/serverless/serverless-parameters),
[OpenAI proxy](https://docs.vast.ai/guides/serverless/openai-compatible-api),
[deployments](https://docs.vast.ai/guides/serverless/deployments/index).

Customer-facing version of this file: `https://docs.runpod.io/migrate/vast-ai`.

## Detect

| Signal | What it means | Lands on |
| --- | --- | --- |
| `from vastai import VastAI` / `VastAI(` | Control-plane code on the Vast Python SDK | REST v2 `/v2/pods`, or `@app.task` |
| `from vastai import Serverless` / `client.get_endpoint(name=` | Client of a Vast Serverless endpoint | `runpod.Endpoint`, or `https://api.runpod.ai/v2/ENDPOINT_ID/runsync` |
| `from vastai import Worker, WorkerConfig` / `HandlerConfig(` / `BenchmarkConfig(` | PyWorker `worker.py` | Queue handler, or load-balancing server |
| `from vastai import Deployment` / `@app.remote(` / `@app.context(` | Vast Deployment (beta) | `runpod.App` with `@app.queue` or `@app.api` |
| `vastai search offers` / `search_offers(` | Offer search before create | `GET /v2/catalog/gpus`, `runpodctl gpu list` |
| `vastai create instance` / `create_instance(` / `vastai launch instance` | Instance create | `runpodctl pod create`, `POST /v2/pods` |
| `--bid_price` / `bid_price=` / `--type bid` / `vastai change bid` | Interruptible instance | Gap: see Gaps |
| `vastai prepay instance` | Reserved instance | Gap: see Gaps |
| `--onstart-cmd` / `--onstart ` / `onstart_cmd=` | On-start script (SSH or Jupyter launch mode) | Pod start command (`cmd`, `--docker-args`) or the image |
| `-p [0-9]+:[0-9]+/udp` / `VAST_UDP_PORT_` | UDP port mapping | Gap: see Gaps |
| `-p [0-9]+:[0-9]+` inside `--env` | TCP port mapping | `ports` as `PORT/http` or `PORT/tcp` |
| `VAST_TCP_PORT_` / `PUBLIC_IPADDR` | Container builds its own public address | `RUNPOD_TCP_PORT_`, `RUNPOD_PUBLIC_IP`, or the proxy URL |
| `CONTAINER_ID` / `CONTAINER_API_KEY` / `VAST_CONTAINERLABEL` | Container reads Vast identity | `RUNPOD_POD_ID`, `RUNPOD_API_KEY`, `RUNPOD_POD_HOSTNAME` |
| `env >> /etc/environment` / `env \| grep _ >> /etc/environment` | Vast SSH-mode env workaround | Delete the line |
| `VAST_API_KEY` / `vast_api_key` / `vastai set api-key` | Vast credential | `RUNPOD_API_KEY` |
| `console.vast.ai/api/v0` / `/bundles/` / `/asks/` | Raw Vast REST calls | REST v2 |
| `openai.vast.ai/` | OpenAI-compatible proxy client | `https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1` |
| `vastai create endpoint` / `vastai create workergroup` / `PYWORKER_REPO` | Vast Serverless deploy | `runpodctl serverless create`, `POST /v2/serverless` |
| `vastai copy` / `vastai cloud copy` / `V\.[0-9]+:` | Data movement, volume copy | `runpodctl send`/`receive`, `network-volume upload`/`download` (runpodctl v3.1.0+), or `aws s3` against the S3-compatible API |
| `vastai create volume` / `--create-volume` / `--link-volume` / `-v V\.` | Machine-local volume | Network volume |
| `vastai/base-image` / `vastai/pytorch` / `@vastai-automatic-tag` | Vast-specific image or tag | Upstream or `runpod/` image, pinned tag, CUDA floor |
| `vms_enabled=true` / `docker.io/vastai/kvm` | VM instance | Gap: see Gaps |
| `cpu_arch=arm64` | ARM host | Gap: Runpod images are `linux/amd64` |

Inventory commands (read-only): `vastai show instances --raw`, `vastai show volumes --raw`, `vastai show endpoints --raw`, `vastai show workergroups --raw`, `vastai show deployments --raw`, `vastai show env-vars --raw`, `vastai show connections --raw`, `vastai show scheduled-jobs --raw`. Instance fields worth reading: `id`, `label`, `actual_status`, `gpu_name`, `num_gpus`, `image_uuid`, `image_runtype`, `onstart`, `extra_env`, `disk_space`, `geolocation`, `is_bid`, `dph_total`, `ports`.

## Product map

| Vast.ai | Runpod | Note |
| --- | --- | --- |
| Instance | Pod | Create takes a GPU type ID, not an offer ID. No host choice. |
| Offer search | `runpodctl gpu list`, `runpodctl datacenter list`, `GET /v2/catalog/gpus?include=AVAILABILITY&product=POD` | Stock is per GPU type and data center. Read, then create, then fall back on `400`. |
| On-demand instance | On-demand Pod | |
| Interruptible instance | On-demand Pod, Serverless queue endpoint, or `@app.task` | REST v2 and `runpodctl` create on-demand Pods. |
| Reserved instance | On-demand Pod | Committed capacity goes through Runpod sales. |
| `datacenter=true` / verified hosts | `cloud: SECURE` (default) / `COMMUNITY` | |
| Launch modes (entrypoint, SSH, Jupyter) | One Pod type with `startSsh`, `startJupyter` | The image entrypoint keeps running. |
| Template | Template | Pod and Serverless templates are separate (`--serverless`). |
| Instance disk | Container disk (ephemeral) + volume disk at `/workspace` | A stop clears the container disk. |
| Local volume | Network volume (one data center) or global volume (any data center) | |
| Cloud Sync | Cloud Sync (console), `aws s3`/`rclone` in the Pod, S3-compatible API on network volumes | |
| Serverless endpoint + workergroup | Serverless endpoint | One resource. |
| PyWorker | Handler (`QUEUE`) or your HTTP server with `/ping` (`LOAD_BALANCER`) | No benchmark, no workload calculator. |
| Deployment (`@app.remote`) | `runpod.App` + `@app.queue` | |
| OpenAI proxy | vLLM worker `/openai/v1` route | `model` must be the deployed model name. |
| Account env vars | Secrets, `{{ RUNPOD_SECRET_name }}` | Referenced explicitly per Pod or template. |
| `--login` | Registry credential, `--registry-auth-id` / `registry` | |
| Teams | Organizations | |

## Field map

Instance create (`vastai create instance OFFER_ID ...`):

| Vast field | `runpodctl pod create` | REST `POST /v2/pods` |
| --- | --- | --- |
| offer `id` (from search) | `--gpu-id`, `--gpu-count` | `gpu.id`, `gpu.count` |
| `--image` | `--image` | `image` |
| `--label` | `--name` | `name` (required) |
| `--disk` | `--container-disk-in-gb`, `--volume-in-gb` | `disk`, `mounts.persistent.{size,path}` |
| `--env '-e K=V'` | `--env '{"K":"V"}'` | `env` (object) |
| `--env '-p 8000:8000'` | `--ports "8000/http"` or `"8000/tcp"` | `ports: ["8000/http"]` |
| `--env '-p 8082:8082/udp'` | none | none |
| `--env '-h NAME'` | none | none |
| `--args A B` | `--docker-args "A B"` | `cmd: ["A","B"]` |
| `--entrypoint X` | template `--docker-entrypoint` | `entrypoint: ["X"]` |
| `--onstart-cmd 'CMDS'` | `--docker-args` | `cmd: ["bash","-c","CMDS"]` |
| `--ssh` | `--ssh` (default true) | `startSsh: true` |
| `--direct` | `22/tcp` in `--ports` | `22/tcp` in `ports` |
| `--jupyter` | template with JupyterLab | `startJupyter: true` + `8888/http` |
| `--login '-u U -p T REG'` | `--registry-auth-id` | `registry` |
| `--template_hash` | `--template-id` | `templateId` |
| `--link-volume`, `--mount-path` | `--network-volume-id` | `mounts.network[].{volumeId,path}` |
| `--bid_price` | none | none |
| `--cancel-unavail` | not needed | not needed (optional `queue` waits for capacity) |
| search `cuda_vers>=X` | `--min-cuda-version X` | `gpu.minCudaVersion` |
| search `geolocation in [..]` | `--country-code`, `--data-center-ids` | `dataCenterIds` |
| search `cpu_cores_effective>=`, `cpu_ram>=` | check `--help` | `gpu.minVcpuCountPerGpu`, `gpu.minRamPerGpu` (per GPU) |
| search `reliability`, `inet_down`, `dlperf`, `static_ip`, `machine_id`, `dph_total<=` | none | none (read `price` from the catalog to cap cost) |

Serverless (`vastai create endpoint` + `vastai create workergroup`):

| Vast field | `runpodctl serverless create` | REST `POST /v2/serverless` |
| --- | --- | --- |
| `--endpoint_name` | `--name` | `name` |
| `--max_workers` | `--workers-max` | `workers.max` |
| `--min_load` > 0 | `--workers-min` | `workers.min` |
| `--inactivity_timeout` | `--idle-timeout` | `workers.idleTimeout` |
| `--target_util` | `--scale-by`, `--scale-threshold` | `scaling: {type: QUEUE_DELAY, queueDelay}` or `{type: REQUEST_COUNT, requestCount}` |
| `--cold_workers`, `--cold_mult`, `--min_cold_load` | none | none |
| `--template_hash` | `--template-id` or `--hub-id` | `templateId` |
| `--launch_args "--image I --disk D --env ..."` | template `--image`, `--container-disk-in-gb`, `--env` | `image`, `disk`, `env` |
| `--search_params "gpu_ram>=24 ..."`, `--gpu_ram` | `--gpu-id POOL` | `gpu.pools`, `gpu.excludedTypes`, `gpu.count` |
| (routing model) | queue by default | `type: QUEUE` or `LOAD_BALANCER` (required) |

GPU names: Vast `gpu_name=RTX_4090` becomes `NVIDIA GeForce RTX 4090`; `A100_PCIE` becomes `NVIDIA A100 80GB PCIe`; `H100_SXM` becomes `NVIDIA H100 80GB HBM3`; `L40S` becomes `NVIDIA L40S`. Resolve every other name from `runpodctl gpu list --include-unavailable` (`gpuId`) and the catalog's `pool` field. Do not guess IDs.

Runtime environment variables:

| Vast | Runpod Pod |
| --- | --- |
| `CONTAINER_ID` | `RUNPOD_POD_ID` |
| `VAST_CONTAINERLABEL` | `RUNPOD_POD_HOSTNAME` |
| `CONTAINER_API_KEY` | `RUNPOD_API_KEY` (Pod-scoped) |
| `PUBLIC_IPADDR` | `RUNPOD_PUBLIC_IP` (when the Pod has one) |
| `VAST_TCP_PORT_22` | `RUNPOD_TCP_PORT_22` |
| `VAST_TCP_PORT_X` | `RUNPOD_TCP_PORT_X` (TCP ports requested above 70000); HTTP ports use `https://$RUNPOD_POD_ID-PORT.proxy.runpod.net` |
| `VAST_UDP_PORT_X` | none |
| `GPU_COUNT` | `RUNPOD_GPU_COUNT` |
| `SSH_PUBLIC_KEY` | `PUBLIC_KEY` |
| `DATA_DIRECTORY` | none (use `/workspace`) |
| none | `RUNPOD_DC_ID`, `RUNPOD_CPU_COUNT`, `RUNPOD_VOLUME_ID` |

Status:

| Vast `actual_status` | REST `status` | `runpodctl` `runtimeStatus` |
| --- | --- | --- |
| `null`, `created`, `loading`, `rebooting` | `PROVISIONING`, `STARTING` | `initializing` |
| `running` | `RUNNING` | `running` |
| `stopped` | `EXITED` | `stopped` |
| `exited` (crashed) | `ERROR` | `error` |
| `unknown`, `offline` | no direct value | `unknown` means the lookup failed: keep polling |
| destroyed | `TERMINATED`, then `404` | `terminated`, then not found |

Vast `exited` means failure. Runpod `EXITED` means stopped. Rewrite every status comparison, do not rename strings.

## Code translation

Create, wait, fetch, delete (Vast SDK to REST v2):

```python
# before
from vastai import VastAI
v = VastAI(api_key=os.environ["VAST_API_KEY"])
offer = v.search_offers(query="gpu_name=RTX_4090 num_gpus=1", order="dph_total", limit=1, storage=30)[0]
iid = v.create_instance(id=offer["id"], image=IMAGE, disk=30, label="job",
                        env="-e MODE=fast -p 8000:8000", args=["bash", "-c", START],
                        cancel_unavail=True)["new_contract"]
inst = v.show_instance(id=iid)          # poll until inst["actual_status"] == "running"
url = f"http://{inst['public_ipaddr']}:{inst['ports']['8000/tcp'][0]['HostPort']}"
v.destroy_instance(id=iid)
```

```python
# after
import os, requests
API = "https://api.runpod.io/v2"
H = {"Authorization": f"Bearer {os.environ['RUNPOD_API_KEY']}"}
r = requests.post(f"{API}/pods", headers=H, timeout=60, json={
    "name": "job", "image": IMAGE,
    "gpu": {"id": "NVIDIA GeForce RTX 4090", "count": 1, "minCudaVersion": "12.4"},
    "disk": 30, "env": {"MODE": "fast"}, "ports": ["8000/http"],
    "cmd": ["bash", "-c", START]})
# 201 = created; 400 or 403 = could not be placed or no access, try the next GPU type; 422 = fix the body
pod_id = r.json()["id"]
status = requests.get(f"{API}/pods/{pod_id}", headers=H).json()["status"]   # poll until RUNNING
url = f"https://{pod_id}-8000.proxy.runpod.net"
requests.delete(f"{API}/pods/{pod_id}", headers=H)   # 204; GET then returns 404
```

Same job as a function (one Pod per call, terminated on return):

```python
import runpod
app = runpod.App("job")

@app.task(gpu="4090", env={"MODE": "fast"}, container_disk_gb=30)
def job():
    import torch
    return {"gpu": torch.cuda.get_device_name(0)}

@runpod.local_entrypoint
def main():
    print(job.remote())
# rp flash dev main.py
```

PyWorker to queue handler. Delete `worker.py` (`WorkerConfig`, `HandlerConfig`, `BenchmarkConfig`, `LogActionConfig`). Load the model at import, handle one job per call:

```python
import runpod
model = load_model()            # replaces LogActionConfig.on_load

def handler(job):
    return model.generate(**job["input"])   # replaces HandlerConfig(route="/generate")

runpod.serverless.start({"handler": handler})
```

PyWorker to load-balancing server. Keep the model server, bind to `PORT`, add `GET /ping` returning `200` when ready, set `PORT_HEALTH` equal to `PORT`. Clients call `https://ENDPOINT_ID.api.runpod.ai/PATH`.

Deployment to SDK app:

```text
# before                                    # after
from vastai import Deployment               import runpod
app = Deployment(name="square")             app = runpod.App("square")
@app.remote(benchmark_dataset=[{"x": 2}])   @app.queue(gpu="4090", workers=(0, 3))
async def square(x): return x * x           def square(x: int): return x * x
```

SDK details: [runpod-flash/SKILL.md](../../runpod-flash/SKILL.md). Handler patterns: [endpoint-workflows.md](../../runpod-usage/reference/endpoint-workflows.md).

## Data

| Vast source | Route to Runpod |
| --- | --- |
| Object storage (S3, R2, GCS) pulled at boot | Keep as is, or pull once inside a Pod onto a network volume: `aws s3 sync`, `rclone copy`, `hf download` |
| Running instance disk | On the instance: `runpodctl send PATH`; on the Pod: `runpodctl receive CODE`. Or `rsync -avzP -e "ssh -p PORT" SRC root@POD_IP:/workspace/` (Pod needs `22/tcp`) |
| Stopped instance disk | `vastai copy C.ID:/path local:./path` or `vastai cloud copy` to a bucket first |
| Local volume | `vastai copy V.ID:/data/ C.ID:/workspace/data/` first (volume to local path is unsupported on Vast) |
| Local machine | `runpodctl network-volume upload VOLUME_ID LOCAL [REMOTE]` (runpodctl v3.1.0+; check `runpodctl network-volume --help`; S3 API keys in `RUNPOD_S3_ACCESS_KEY` / `RUNPOD_S3_SECRET_KEY`, data center with the S3 API) |
| Hugging Face weights on Serverless | Cached models: `runpodctl serverless create ... --model-reference URL` |

Rules: create the network volume in a data center that has stock of the target GPU (`runpodctl datacenter list`). Network volumes mount at `/workspace` on Pods and `/runpod-volume` on Serverless. A Vast volume mounted at `/data` or `/mnt` needs a path change or an explicit mount path. A global volume has no S3 API: load it from a Pod. Vast bills bandwidth per GB at the host's rate, so tell the user before pushing large data out of an instance. Details: [storage.md](../../runpod-usage/reference/storage.md). Exact flags: `runpodctl network-volume upload --help`.

## Client and API call map

| Vast | Runpod |
| --- | --- |
| `Serverless().get_endpoint(name=N)` then `endpoint.request("/route", payload, cost=C)` | `POST https://api.runpod.ai/v2/ENDPOINT_ID/runsync` with `{"input": payload}`, or `runpod.Endpoint("ENDPOINT_ID").run_sync(payload)` |
| `result["response"]` | job object: `id`, `status`, `output` |
| long request held open against a worker | `/run` then `/status/JOB_ID`, `/stream/JOB_ID`, or `webhook` in the body |
| worker sessions | worker affinity on load-balancing endpoints (`X-Runpod-Worker-Id`) |
| `OpenAI(base_url="https://openai.vast.ai/NAME", api_key=VAST_KEY)`, `model=""` | `OpenAI(base_url="https://api.runpod.ai/v2/ENDPOINT_ID/openai/v1", api_key=RUNPOD_KEY)`, real `model` |
| `vastai show instances --raw` | `runpodctl pod list --all`, `GET /v2/pods` |
| `vastai show instance ID --raw` | `runpodctl pod get POD_ID`, `GET /v2/pods/POD_ID` |
| `vastai stop\|start\|reboot instance ID` | `runpodctl pod stop\|start\|restart POD_ID`, `POST /v2/pods/POD_ID/action` |
| `vastai destroy instance ID -y` | `runpodctl pod delete POD_ID`, `DELETE /v2/pods/POD_ID` |
| `vastai label instance ID NAME` | `runpodctl pod update POD_ID --name NAME`, `PATCH /v2/pods/POD_ID` |
| `vastai logs ID` | `runpodctl pod logs POD_ID`, `GET /v2/pods/POD_ID/logs` |
| `vastai ssh-url ID` | `runpodctl ssh info POD_ID`, Pod `ssh.direct` / `ssh.proxy` |
| `vastai execute ID 'ls'` | SSH, or `POST /v2/pods/POD_ID/exec` (argv array, 1 to 25 s) |
| `vastai create ssh-key` | `runpodctl ssh add-key --key-file PATH` (before creating Pods) |
| `vastai create template` | `runpodctl template create` (`--serverless` for endpoints) |
| `vastai create volume` | `runpodctl network-volume create --name N --size GB --data-center-id DC` |
| `vastai show endpoints` / `delete endpoint` | `runpodctl serverless list` / `delete` |
| `vastai show invoices-v1` | `runpodctl billing pods`, `GET /v2/billing/pods` |
| `vastai set api-key` / `VAST_API_KEY` | `RUNPOD_API_KEY` / `rp login` |

Command details: [runpodctl/SKILL.md](../../runpodctl/SKILL.md). Ports and proxy behavior: [networking.md](../../runpod-usage/reference/networking.md).

## Gaps: stop and ask the user

| Vast feature in use | Why it needs a decision | Options |
| --- | --- | --- |
| UDP ports (`/udp`, `VAST_UDP_PORT_X`) | Pods do not route UDP | (a) move the protocol to TCP, (b) keep the UDP-facing component off Runpod and connect over TCP, (c) leave this workload on Vast |
| Interruptible bids (`--bid_price`) | REST v2, `runpodctl` and the MCP server create on-demand Pods | (a) on-demand Pod with checkpoints to `/workspace`, (b) Serverless queue endpoint that scales to zero, (c) `@app.task`. Costs differ: show the catalog price and get approval |
| Reserved instances (`prepay`) | No self-serve prepay; savings plans are closed to new purchases | (a) on-demand, (b) user contacts Runpod sales. Check Vast refund terms before destroying a reserved instance |
| Host filters (`reliability`, `inet_down`, `static_ip`, `machine_id`, price cap in the query) | Runpod places by GPU type, cloud tier and data center | Map to Secure Cloud, `dataCenterIds`, `minCudaVersion`; cap cost from the catalog `price` |
| VM instances, Docker Compose, systemd | Pods are single containers | (a) one Pod per service with global networking, (b) one image running several processes |
| ARM (`cpu_arch=arm64`) | Images must be `linux/amd64` | Rebuild for amd64 |
| Data kept on the instance disk outside `/workspace` | A Pod stop clears the container disk | Move paths under `/workspace` or a network volume |
| Machine-local volume shared by co-located instances | Network volume is per data center | (a) network volume + pin the data center, (b) global volume for read-heavy data |
| Scheduled Cloud Sync (`--schedule`) | No scheduler on Runpod Cloud Sync | cron in the Pod, or an external scheduler against the S3 API |
| `cold_workers`, `cold_mult`, load-based scaling | Runpod scales on queue delay or request count | (a) `workers.min` = 0 with FlashBoot and cached models, (b) `workers.min` > 0, which bills continuously |
| Custom hostname (`-h`) | No hostname field on Pod create | Use `RUNPOD_POD_HOSTNAME` / `RUNPOD_POD_ID` |
| Services exposed on `-p` with no auth | The proxy URL is public and has a 100 s limit | Add auth in the app; use `PORT/tcp` for long connections |

## Verify

1. Pod: poll `GET /v2/pods/POD_ID` until `status` is `RUNNING` (or `runpodctl pod get POD_ID` until `runtimeStatus` is `running`), with a time limit. Treat `ERROR` as terminal. Then probe the service port, since a running container does not mean a listening service.
2. Send a real request from outside Runpod: `curl https://POD_ID-PORT.proxy.runpod.net/...` or `POST https://api.runpod.ai/v2/ENDPOINT_ID/runsync` with `{"input": {...}}`. Compare the output with the Vast output for the same input.
3. Serverless: `GET https://api.runpod.ai/v2/ENDPOINT_ID/health`; confirm jobs leave `IN_QUEUE` and reach `COMPLETED`. Measure one cold start and one warm request.
4. Data: compare `du -sh` and file counts between the Vast source and `/workspace`.
5. Grep the repo and the image source again for the Detect signals. Zero matches outside docs, unless the user keeps a workload on Vast.
6. Stop and start one Pod and confirm the workload recovers from `/workspace` alone.
7. Report every Runpod resource created (ID, GPU, hourly `cost`) and what is still running.

## Shut down Vast.ai

Only after explicit user approval, and only for resources the user names or the migration replaced. Stopped instances and volumes keep billing for storage, so destroying is the only way to stop charges, and it deletes data.

```bash
vastai show endpoints --raw && vastai show workergroups --raw
vastai delete workergroup WORKERGROUP_ID     # does not destroy its worker instances
vastai delete endpoint ENDPOINT_ID
vastai show instances --raw                  # includes leftover workers and stopped instances
vastai destroy instance INSTANCE_ID -y
vastai show volumes --raw
vastai delete volume VOLUME_ID               # only after every instance using it is destroyed
vastai show instances --raw | jq 'length'    # confirm 0, or only what the user kept
vastai show user                             # remaining credit
```

Check JSON output, not exit codes: `vastai` exits 0 on failed requests. Tell the user to turn off autobilling, revoke the Vast API keys used by automation and remove `VAST_API_KEY` from CI secrets.
