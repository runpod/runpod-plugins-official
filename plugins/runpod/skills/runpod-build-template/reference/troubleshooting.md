---
concepts: [container-image, endpoint-build, model-store, network-volume, worker, exposed-port, registry-credential]
---

# Diagnose the stage before retrying

Keep the failing command/request, redacted error, source/image/build/resource identity,
confirmed cause versus hypothesis, and next expected signal. A retry needs a reason:
transient transport may justify one retry with backoff; deterministic limits require a
changed cause or route. After two targeted repairs for the same cause, reassess rather
than repeating unchanged work. These defaults do not limit unrelated useful progress.

| Symptom | Inspect and recover |
| --- | --- |
| Source absent/private/wrong revision | Verify URL/ref/access; finish independent work and give the exact access handoff. |
| Missing files in build | Check context, `.dockerignore`, submodules, LFS pointers and generated assets. |
| Docker command fails | Distinguish missing CLI, stopped daemon, context/socket access, architecture and disk; choose an eligible hosted route if appropriate. |
| Dependency/import/native-extension failure | Check interpreter/ABI, framework/CUDA constraints, CPU fallback and shadowing; avoid blind upgrades/redundant torch. |
| Build needs GPU/privilege/system service | Verify the actual requirement against builder capability; use compatible artifacts or another verified builder. |
| Private base/package/model or failed pull | Identify source/build-secret/registry-push/target-pull/runtime boundary; never expose credentials. |
| Build times out or is too large | Measure the failing phase, context/layers/downloads and current builder limits. If weights dominate, assess [model delivery](model-delivery.md) before another builder or model change; retain the chosen model and explicit baked-image test requirements. |
| Disk full | Identify container, volume, builder or host filesystem; remove only task-owned disposable data. |
| Container exits or service inaccessible | Inspect entrypoint/workdir, CRLF/shebang, permissions, process lifetime, interface and ports; run clean startup. |
| Baked files disappear | Inspect real mount points; keep immutable runtime/source outside data mounts. |
| Existing volume fails after image update | Detect runtime/app compatibility and incomplete initialization; stage safe repair and preserve originals. Never delete the workspace to fix it. |
| Shared download/environment corruption | Check identity/version, filesystem locking and partial files; atomic completion and separate incompatible versions. |
| OOM or slow CPU fallback | Run representative GPU input/batch/context; bound concurrency and check actual device use without silently changing quality. |
| Repeated jobs leak memory/files | Inspect retained tensors, globals, web process count and per-request temp cleanup, including error paths. |
| Retry/cancellation duplicates or truncates writes | Use workload-appropriate idempotency and durable output state; clean only owned temporary data. |
| Ready/200 but workload fails | Exercise useful output and gate readiness on required initialization. |
| GitHub build complete but old code serves | Inspect release/update trigger and deployed identity; do not rebuild unchanged source blindly. |
| No worker capacity/funds/quota/region match | Separate scheduling/account blockers from image correctness; propose compatible authorized alternatives. |
| Interrupted/unknown build or deploy result | Inspect existing identifiers before retrying; avoid duplicate resources and keep resume information. |

When blocked, deliver completed files/checks, the failing stage, evidence, smallest
human action, exact resume instruction and remaining temporary resource IDs. Continue
independent authoring. Do not answer only “install Docker and try again.”
