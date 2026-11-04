---
concepts: [serverless-endpoint, flashboot, network-volume, volume-cache, worker]
---

# Serverless deploy — scenario rules

Rules the [serverless-deploy](../SKILL.md) playbook applies only in a particular
scenario. They moved here verbatim to keep the playbook short; the playbook names each
trigger and links here. Read the matching section before you act on that scenario.

## Load-balancer endpoint

For a load-balancer (custom-HTTP, direct-routing) endpoint rather than the queue, the cardinal rule is that the worker must serve HTTP on `PORT` (default 80) AND answer the health check at `HEALTH_CHECK_PATH` (default `/ping`) on `PORT_HEALTH` (default 80). Miss either and workers never pass health, so the endpoint looks stuck with zero ready workers; the endpoint read returns the exact health URL being polled. The endpoint type is also immutable after create, and a load-balancer endpoint has no queue: when every worker is busy, requests fail instead of waiting, so size `workers.max` for the peak.

## Cold-start levers on a new endpoint

When deploying a new endpoint, cold-start asks have four levers; for an endpoint that already exists, go to endpoint-ops and change nothing here. Name all four with their cost trade-offs: **FlashBoot** (faster worker start, no standing cost, best effort), **minimum/warm workers** (no cold start; bills that worker continuously, so quote $/hr × 730/mo from the price read), **idle timeout** (a longer window keeps a warm worker between bursts: fewer cold starts, more billed idle seconds), **model caching** (the model files on a network volume, in Runpod's model repository through `runpodctl model add`, or baked into the image; the load, not the boot, dominates big-model cold starts) (the endpoint's model reference is set in the console or with runpodctl; hand that step to the user). Then create the endpoint with the levers that add no standing charge (FlashBoot on, a longer idle timeout), read it back, and report the warm worker as the one lever left with its monthly price. Set a minimum worker only when the user asked for one or accepts that price. A question about which option to pick, with nothing created, does not answer a set-up request.

## Weights too large to bake into the image

When weights are too large to bake into the image, stage them on a network volume. Create the network volume in a data center that has the target GPU, attach it to the endpoint, point the worker's model path env at the volume mount, keep minimum workers 0, and confirm the wiring by reading the endpoint and volume back. When the user asked for the storage setup rather than a served model, those read-backs are the proof; a job on a large model costs money and download time, so it waits for their ask. The first worker's download seeds the cache. Do not create a staging pod the user did not ask for; offer it as the option if they want the cache warm before the first request. State two facts of the architecture you built, without hedging: the first worker downloads the weights to the volume once and every later cold start mounts the cache instead of re-downloading; and the volume must live in the same data center as the GPUs or it cannot mount. When the worker is the user's own handler code rather than a prebuilt image, keep its model cache on container disk and wrap the load in `VolumeCache` instead of pointing the model path at the mount (`runpodctl/reference/model-caching.md`). (The volume CRUD discipline is lifecycle-crud's; this is the serving-side wiring.)
