---
lanes: [runpod-mcp, rest, ssh, hf]
mcp: partial
concepts: [global-volume, network-volume, data-center, pod, cpu-pod, pod-volume-disk, container-disk, gpu-type, gpu-availability, pod-ssh-access, serverless-endpoint, endpoint-autoscaling, worker, credit-balance]
status: spec-checked
verified: "2026-11-13"
evals: [runpod/evals/global-volume-shared-files]
---

# Golden path 28 — share model files across data centers with a global volume

> **Status:** spec-checked 2026-11-13 — checked against the REST v2 spec (`/v2/global-volumes`, `Mounts.global`, `EndpointMountsInput`) and the public global volume docs; the name-only create, the CPU Pod mount and its default path, the `409` on a mounted delete and the `400` on a CPU endpoint come from the concept rules' live probes. Steps 3, 5 and 6 (the GPU fill Pod, the GPU endpoint and the request) are spec-only, with no live run. **Evals:** [global-volume-shared-files](../evals/global-volume-shared-files.eval.md). Status key: [golden-paths README](README.md#status-legend).

**Goal:** put model files on one global volume once, mount it on GPU compute in whatever data
center has stock, check that the compute reads the files, and clean up.

**Status:** DOCUMENTED — spec-checked 2026-11-13
**Lane(s):** runpod-mcp or REST v2 (volume, Pods, endpoint) · SSH + `hf` (writing the files)

## When to use this

A global volume has no data center, so mounting it does not narrow GPU choice the way a
network volume does. Use it for read-mostly files that compute in several data centers needs:
model weights, LoRA adapters, tokenizer and config files. It also covers the case where the
GPU you need has no stock in any data center where you hold a network volume.

Use something else when:

- **The workload writes a lot** (training, checkpoints) or several writers touch one file:
  a network volume, as in [07](07-network-volume-handoff.md).
- **The endpoint is CPU, or also needs network volumes:** an endpoint takes a global volume on
  GPU only, and carries network volumes or a global volume, not both. Per-data-center network
  volumes are paths [10](10-multi-region-ha-serverless.md) and
  [19](19-three-region-same-file.md).
- **The model is on Hugging Face and the target is GPU Serverless:** the host cache in
  [20](20-model-caching-endpoint.md) needs no volume at all.

Limits, mount paths and rates: [`runpod-usage` storage](../../runpod-usage/reference/storage.md#global-volume-any-data-center).

## Prerequisites

- The [shared prerequisites](README.md#before-you-run-any-path-shared-prerequisites),
  including an SSH key registered on the account before the fill Pod is created.
- For a Hugging Face model, the `hf` CLI on the Pod
  ([setup](../../runpod-companion-clis/reference/huggingface-setup.md)) and a token for a
  gated repo.
- For the endpoint, an image whose handler loads the model from a directory you pass in, for
  example through an env var.

## Walkthrough

1. **State the cost, then create the volume.** Tell the user it bills for stored data plus
   per-request fees, with writes, creates and lists priced above reads, and that it is deleted
   15 days after the account balance reaches $0. Then create it with a `name` and nothing
   else, through MCP `create-global-volume` or REST v2:

   ```bash
   curl -s -X POST https://api.runpod.io/v2/global-volumes \
     -H "Authorization: Bearer $RUNPOD_API_KEY" -H 'Content-Type: application/json' \
     -d '{"name":"shared-weights"}'
   ```

   The `201` response carries the `id`. There is no size or data center to choose: storage
   grows with the data. Names are not unique, so keep the id. An account holds a capped
   number of global volumes and a create past the cap is answered `400`, so read
   `list-global-volumes` first and reuse one that fits.

2. **Write the files from a short-lived Pod.** Any data center works. A CPU Pod created
   through the API is enough to download files (see the CPU note under Gotchas). Create it with
   MCP `create-pod` or `POST https://api.runpod.io/v2/pods`; if the create is refused, go to
   step 3:

   ```json
   {
     "name": "gv-fill",
     "image": "runpod/base:1.0.2-ubuntu2204",
     "cpu": { "id": "cpu3c", "vcpuCount": 2 },
     "disk": 20,
     "ports": ["22/tcp"],
     "startSsh": true,
     "mounts": { "global": [{ "volumeId": "<global-volume-id>", "path": "/workspace-global" }] }
   }
   ```

   Send no `persistent` mount: a pod volume disk beside a global volume is answered `400`.
   Read the Pod back with `get-pod` until it is `RUNNING` and `ssh.direct` is set, and check
   `mounts.global[0].path`. Then run the `ssh.direct.command` it returns (add
   `-o StrictHostKeyChecking=no`) and write the files:

   ```bash
   hf download <org>/<model> --local-dir /workspace-global/<model>
   ls -la /workspace-global/<model>
   ```

   Compare the file list and sizes with the source. The volume cannot set file permission
   bits, so a download from Hugging Face may print warnings about them.

   `hf download` normally locks each file and renames it into place, and the volume has no
   file locking or atomic rename. If the download fails on the volume, download to the
   container disk instead (set `disk` above the model's size), then copy and compare again.
   The `*` leaves out the `.cache` folder `hf` keeps in the download directory:

   ```bash
   hf download <org>/<model> --local-dir /root/<model>
   mkdir -p /workspace-global/<model>
   cp -r /root/<model>/* /workspace-global/<model>/
   ls -la /workspace-global/<model>
   ```

   If a command fails, delete the Pod before you report the failure: it bills while it runs,
   and the volume cannot be deleted while the Pod mounts it.

3. **If the CPU create is refused, fill from a GPU Pod.** Read GPU price and stock with MCP
   `list-gpu-types` (`include:["AVAILABILITY"]`, `product:["POD"]`) or
   `GET https://api.runpod.io/v2/catalog/gpus?include=AVAILABILITY&product=POD`, and pick the
   GPU type with stock and the lowest `price.secure`, the hourly list price for one GPU on
   Secure Cloud, where the create places the Pod by default. Tell the user the GPU type and
   that rate, say the Pod bills until step 4 deletes it, and create it only after they agree.
   The body is step 2's with `gpu` in place of `cpu`:

   ```json
   {
     "name": "gv-fill",
     "image": "runpod/base:1.0.2-ubuntu2204",
     "gpu": { "id": "<gpu-type-id>", "count": 1 },
     "disk": 20,
     "ports": ["22/tcp"],
     "startSsh": true,
     "mounts": { "global": [{ "volumeId": "<global-volume-id>", "path": "/workspace-global" }] }
   }
   ```

   Keep `path`: for a GPU Pod the spec names no default. Then read the Pod back, write the
   files and compare them as in step 2, with the same rule: if a command fails, delete the Pod
   before you report the failure.

4. **Delete the fill Pod** (`delete-pod`). The files stay on the volume. Delete it rather than
   stopping it: a stopped Pod still counts as mounting the volume.

5. **Attach the volume to the GPU compute, without pinning a data center.** All files must be
   in place before the workers start. For a queue endpoint, `create-endpoint` or
   `POST https://api.runpod.io/v2/serverless`:

   ```json
   {
     "name": "gv-serve",
     "type": "QUEUE",
     "image": "<your-image>",
     "env": { "MODEL_DIR": "/runpod-volume/<model>" },
     "gpu": { "pools": ["ADA_24", "AMPERE_24"], "count": 1, "minCudaVersion": "12.8" },
     "mounts": { "global": [{ "volumeId": "<global-volume-id>" }] },
     "workers": { "min": 0, "max": 1, "idleTimeout": 60 },
     "scaling": { "type": "QUEUE_DELAY", "queueDelay": 4 },
     "timeout": 600000
   }
   ```

   Workers see the volume at `/runpod-volume`, so the handler reads `/runpod-volume/<model>`.
   Leave `dataCenterIds` unset and list every pool the model fits. To move an existing
   endpoint off network volumes, send `"network": []`, the new `global` list and
   `"dataCenterIds": []` in one `update-endpoint`; the change applies to workers created
   afterwards. A GPU Pod takes the same `mounts.global` entry; set `path` there, since the
   spec names no default for a GPU Pod.

6. **Send one real request** and check that the worker loaded the model from
   `/runpod-volume/<model>` (`stream-worker-logs`), not from a fresh download.

## Verify

- `get-global-volume` returns the id and name.
- `get-endpoint` lists the volume under `mounts.global`, with `mounts.network` empty, and the
  request from step 6 returned real output.
- On a GPU Pod, `get-pod` shows the `mounts.global[0].path` you set, and `ls` on that path over
  SSH lists the files.

## Gotchas

- **CPU Pods: the sources differ.** The
  [global volume overview](https://docs.runpod.io/storage/globalvolume/overview) opens with
  storage "you can attach to GPU Pods and GPU Serverless endpoints", and
  [Global volumes for Pods](https://docs.runpod.io/storage/globalvolume/globalvolume-pods)
  covers GPU Pods only. The REST v2 reference
  ([create a Pod](https://docs.runpod.io/api-reference-v2/pods/create-a-pod), `Mounts.global`:
  "on GPU and CPU pods") and the overview's Limitations section ("CPU Pods through the API
  only") allow a CPU Pod created through the API, and a CPU Pod created through REST v2 has
  mounted one ([`global-volume.pod-mount`](../../runpod-usage/concepts/global-volume.yaml)). If
  a CPU create with `mounts.global` is refused, fill the volume from a GPU Pod as in step 3.
- **The default mount path depends on the route.** A CPU Pod created through REST v2 or MCP
  with no `path` and no network volume mounts it at `/workspace-global`; the console's deploy
  flow uses `/workspace` when no network volume is attached; for a GPU Pod, or one that also
  mounts a network volume, the spec names no default. Set `path` and read it back.
- **Late writes may not show up.** Changes made after a Pod or worker starts may not be visible
  inside it, and two writers to one file leave the last write. Fill first, then start the
  compute.
- **Not a POSIX file system.** It has no file locking, atomic rename, hard links or
  permission bits. A template that installs a Python environment into `/workspace`, such as
  the official ComfyUI template, cannot use it as its primary volume; mount it at a second
  path for model files. A tool that relies on locks or renames, such as `hf download`, can
  fail writing to it directly; step 2 downloads to the container disk and copies instead.
- **Delete is refused while mounted.** `delete-global-volume` answers `409` while any Pod,
  stopped Pods included, or endpoint still mounts it, and detaches or terminates nothing for
  you. A delete that succeeds removes the data for good.

## Cost & cleanup

- The volume bills for stored data plus requests until it is deleted; rates are in
  [`runpod-usage` storage](../../runpod-usage/reference/storage.md#global-volume-any-data-center).
  Turn on low-balance notifications: at a $0 balance it is flagged and deleted after 15 days.
- The fill Pod bills while it runs, per vCPU per hour for a CPU Pod and at the GPU rate from
  step 3 for a GPU Pod; delete it as soon as the copy checks out or fails. Endpoint workers
  bill while they run; `workers.min: 0` lets the endpoint scale to zero.
- Clean up in this order: `delete-pod` for every Pod that mounts the volume, `delete-endpoint`
  (or `update-endpoint` with `"global": []` to keep the endpoint; that applies to workers
  created afterwards, so wait until the running workers are gone), then
  `delete-global-volume`. Confirm with `list-global-volumes`.

## Skill gaps

- A live run should record the GPU endpoint and GPU Pod mounts, a worker reading the files at
  `/runpod-volume`, whether `hf download` writes straight onto the volume or needs the
  container-disk copy, and the cold-start time of a model loaded from it.
