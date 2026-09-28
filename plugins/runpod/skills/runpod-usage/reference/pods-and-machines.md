---
concepts: [machine, pod, pod-deployment, pod-migration, pod-volume-disk, network-volume, gpu-type]
---

# Pods and machines

A pod runs on one physical **machine** in a data center. Knowing that explains the most
confusing pod behavior: a stopped pod that cannot restart with a GPU even though the
data center shows plenty of stock.

## A pod is bound to its machine

- Runpod assigns the machine when the pod is **first deployed**. The pod stays on it while
  it runs, while it is stopped, and when it starts again.
- **Stopping releases the pod's GPUs** on that machine, and another customer can rent them
  while the pod is stopped.
- **Starting again only looks at that one machine.** Data-center availability describes free
  GPUs across all of its machines, so high stock for your GPU type does not mean your pod's
  machine has a free GPU.
- **Moving to another machine means a new pod** with a new pod id, either through migration
  (offered in the console when a stopped pod cannot get its GPU back) or a fresh deploy. The
  REST v2 pod actions are `start`, `stop`, `restart` and `terminate`; there is no migrate action.

## When a stopped pod will not start with a GPU

1. **Wait and retry** if the pod's machine may free up.
2. **Start it with zero GPUs** to reach the data on its volume disk, copy what you need off,
   then deploy a new pod.
3. **Deploy a new pod** anywhere in the data center. This is only painless when the data you
   need is on a **network volume**, which any pod in that data center can attach.

The habit that avoids the problem: keep data you need on a network volume, not only on the
pod's volume disk. See [`storage.md`](storage.md) for the storage layers.

## What else is per machine

| Property | Why it matters |
| --- | --- |
| **Volume disk** | Stored on the pod's machine. It survives a stop, is lost if the machine fails, and only that pod can use it. A network volume lives at the data-center level instead. |
| **CUDA version** | Set by the machine's driver, not the GPU type, so two machines with the same GPU can report different versions. A pod's `cudaVersion` shows what its machine reports. |
| **GPU count** | One pod runs on one machine, so the most GPUs a single pod can use is the GPU count of the largest machine of that type. `maxCount` on the GPU type reports it for each cloud. |

## Exact rules

The facts above come from the concept files, which cite their public sources:
[`machine`](../concepts/machine.yaml), [`pod-deployment`](../concepts/pod-deployment.yaml)
(deploy, stop, restart and recover as ordered steps), [`pod-migration`](../concepts/pod-migration.yaml)
and [`pod-volume-disk`](../concepts/pod-volume-disk.yaml). With the Runpod MCP server, read
them with `lookup-concept machine`.
