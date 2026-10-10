---
concepts: [container-image, endpoint-build, pod, serverless-endpoint, worker, job]
---

# Evidence and optimization

Use the real entrypoint and representative workload. Record meaningful checks as
**passed / failed / unverified / not applicable**, including command/request, source
revision, image identity, environment, observed result and relevant redacted logs.

| Stage | What it establishes |
| --- | --- |
| Authored | Required files and exact deployment handoff exist. |
| Static-checked | Config/syntax/paths/secret handling checked; no runtime claim. |
| Image-built | The selected builder produced the intended architecture/artifact. |
| Workload-tested | Real entrypoint and useful output checked locally or remotely. |
| Target GPU-tested | Representative operation used the intended GPU/framework. |
| Runpod end-to-end tested | Real external workflow/job/route succeeded on the selected target. |

Report stages independently. No Docker or cloud access is an honest boundary, not a
reason to abandon file authoring. Do not call a generated project validated merely
because its files parse. Managed GitHub images may require target-side validation
because that built artifact cannot be exported for local testing.

## Comparable improvements

Preserve the baseline source/image and define the optimization objective and correctness
tolerances first. Hold representative input, model revision, precision, hardware class,
storage and stated cache conditions comparable. Report changed tradeoffs; do not silently
reduce output quality, disable features or alter data to improve a benchmark.

Measure relevant phases separately where observable: allocation/queue, pull/unpack,
workspace setup/copy, model loading, first successful task, warm requests, and peak
CPU/RAM/VRAM. Record compressed transfer and unpacked disk separately. Some phases
overlap or are hidden: mark that instead of deriving false precision. A first request
does not establish a cold host cache. Cache reuse is conditional on actual layer residency.

Choose a practical repeat count before the test within its budget. Retain raw observations
and report medians/ranges; tiny samples do not establish tail percentiles. A code-only
change should preserve heavy dependency layer identities; compare the produced images,
not just Dockerfile order. If no runnable baseline exists, report candidate results and
the limitation without improvement percentages.

Run the selected target's restart/state/repeated-request checks. Include likely failure
and subsequent recovery, not only a happy path. Validate output content against known
expected results or tolerances, rather than accepting any HTTP 200 or completed job.

## Handoff and cleanup

Summarize files changed, why, verification actually performed, outstanding blockers,
the exact continuation and remaining resource identities. Mark requirements provisional
until measured. Keep detailed evidence in this handoff or maintainer records; the
user-facing README/release needs only limitations that affect deployment or use.
Retain logs/results before cleanup, remove only task-owned disposable
resources, and confirm their final state. If cleanup fails, report remaining resources
and cost exposure without claiming completion of cleanup.
