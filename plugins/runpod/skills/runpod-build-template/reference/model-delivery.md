---
concepts: [model-store, container-image, network-volume, worker]
---

# Choose model delivery before building

For model workloads, inspect model configs, manifests and the real loader before
choosing where weights live. A collection may mix complete models and adapters with
separate bases, tokenizers or custom code. Record the required repositories, revisions,
access requirements and download sizes per supported selection; training ancestry
alone does not imply a separate base download. Storage bytes are not VRAM requirements.

Recommend a delivery plan with the reason, using the user's selected model and build
route. Do not wait for the user to name a Runpod feature. Preserve an explicit baked,
offline or preloaded-only requirement, including a requested builder stress test.

| Delivery | Authoring decision |
| --- | --- |
| Baked image | Useful for a fixed default or self-contained worker. Account for framework plus model layers, builder download time, image transfer and unpacking; do not bake an entire collection merely because it is offered. |
| Runpod Model Store / HF cache | Evaluate for HF-hosted Serverless weights before baking large downloads. Configure the endpoint's cached model and make the custom loader consume the matching local snapshot. |
| Persistent volume | Useful for reusable or user-selected weights. Specify the actual mount, capacity and how it becomes populated: preloaded files or a controlled first-start download. |
| Worker-local download | May fit small disposable data; account for repeat downloads on replacement. It is not persistent storage or a provider-managed pre-start download. |

For Serverless, consult [cached-model documentation](https://docs.runpod.io/serverless/endpoints/model-caching)
and the [official custom-worker example](https://github.com/runpod-workers/model-store-cache-example).
Checked **2026-10-10**: caching can be configured for Docker, GitHub and Hub deployments;
custom workers must integrate the cache into their loaders, and the documented limit
is one cached model per endpoint. Recheck current constraints before deployment.
An adapter plus separate base may need a hybrid plan, with a location for each component.
Do not substitute the adapter ID for the required base, or assume caching one includes both.
The endpoint Model field is distinct from the uploaded Model Repository feature; see
[model storage choices](../../runpodctl/reference/model-caching.md) when that distinction matters.
These reads do not require installing a CLI or obtaining cloud credentials.

## Connect configuration to the loader

Implement only the delivery modes the project needs. For a configurable template,
make the normal selection, such as `MODEL_ID`, drive the complete supported operation:
reuse matching baked/cache/volume files and fetch missing components to the chosen
writable storage when runtime downloads are allowed. Keep explicit path overrides for
users who need them; do not make manual preloading the default unless the requirements
or environment require it. Document any storage/token setup that cannot be automatic.

Choose and document lookup precedence. Match repository and revision, not the first
directory returned by a glob. Connect every required loader, including separate bases
and custom code, to matching artifacts through its supported cache-directory or
local-path interface; preserve the upstream loader's integrity checks.
Check the actual cache layout, including HF blob symlinks, against that loader API.
If it requires regular files, prefer a verified reusable materialization where
possible; account for duplicate disk and startup I/O when copies are necessary.
Finding a cache directory does not establish that weights load without copying.
Provider cache is a read source, not a download staging directory. Keep writes
in designated writable storage and coordinate shared downloads with integrity checks
and atomic completion. Enforce offline loading only after required downloads finish;
a global offline flag must not silently disable an intended fallback.

Changing an application environment variable does not update the endpoint Model field.
Explain when users must update that field as well, or when an allowed volume-download
fallback makes the application variable sufficient. Keep the Hub form, image default,
runtime behavior and README consistent when those surfaces are in scope.

## Verify the selected paths

Check the default and an alternate selection when supported; cache hit, missing or
wrong revision, read-only reuse, and interruption/restart where downloads are implemented.
Exercise the real loader and useful inference offline from the supplied artifacts where
possible. Small fixtures can check path selection and partial-download handling, but
cannot establish real model compatibility, GPU fit or Runpod-managed cache behavior.
Do not download every model or run GPU tests beyond the task's scope to check routing.
