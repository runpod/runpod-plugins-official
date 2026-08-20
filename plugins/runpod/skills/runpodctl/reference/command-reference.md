# runpodctl — behavior reference

**This file does not list flags.** `runpodctl <resource> <action> --help` does, it is always
current, and it ships with the binary in front of you:

```bash
runpodctl --help                          # resources
runpodctl <resource> --help               # actions + aliases
runpodctl <resource> <action> --help      # exact flags, defaults, examples
runpodctl help <resource> <action>        # same, and traverses aliases (`pod remove`) that --help does not
runpodctl version                         # which surface you actually have
```

What lives here instead is the part `--help` never tells you: **what a flag means when it
succeeds, what "ready" is defined as, which field to trust, and what a failure looks like.**
Output shapes, error codes and env vars are in
[output-and-errors.md](output-and-errors.md).

> Two `--help` gotchas: cobra does **not** traverse aliases for `--help`, so `pod remove --help`
> answers `unknown command` even though `pod remove <id>` works — use `runpodctl help pod remove`.
> And the deprecated `get pod` / `get cloud` paths are hidden from `--help` but still live.

## Pods

### Waiting for readiness (`--wait`, v2.9.0+)

| | detail |
| --- | --- |
| ready means | the pod's **public port 22** accepts a tcp connection *and* answers with an ssh protocol banner. No key, no handshake — it proves sshd is up, not that your key is installed. Port 22 merely appearing in `runtime.ports` is not enough: prod allocates that port even for images that run no sshd |
| timeout | `--wait-timeout` accepts `90s`, `10m`, `1h`, `2d`; default `10m` |
| output | progress on **stderr** every ~15s; stdout stays exactly one json object, in the `pod get` shape (so it includes the live `ssh` block, unlike a plain create) |
| on failure | the pod is **not** deleted — exit is non-zero, code `wait_timeout` (or `wait_interrupted` on ctrl-c), and the error object carries the pod id in `id` plus the delete command. A second ctrl-c always exits |
| refuses | `--ssh=false` (there would be nothing to wait for) |
| warns, still waits | `--compute-type CPU` (cpu pods are created over rest, which cannot request Runpod-managed ssh, so only an image that starts its own sshd becomes reachable) and `--cloud-type COMMUNITY` without `--public-ip` (community cloud only maps a public ssh port on a machine that has a public ip) |

### Pod status fields

`pod get` and `pod list` report both (v2.9.0+):

| field | meaning |
| --- | --- |
| `desiredStatus` | what the platform intends: `RUNNING`, `EXITED`. Says `RUNNING` while the image is still pulling |
| `runtimeStatus` | what is actually happening: `running`, `initializing` (no container reported yet — pull/create/boot), `stopped`, `terminated`, `unknown` (the runtime lookup failed or was not made — **not** "the pod is down") |
| `runtimeStatusReason` | stable token when there is more to say, e.g. `awaiting_container`, `stopped_by_user`, `stopped_by_runpod`, `terminated_outbid`, `runtime_unavailable` |
| `uptimeSeconds` | present only while the container is up; omitted otherwise (it used to be a constant `0`) |
| `lastStatusChange` | the backend's raw free-text note, carried so a phrasing the cli does not tokenise still reaches you |
| `networkVolumeId` / `networkVolume` | **v2.10.0+:** `pod get --include-network-volume` fills both — the id and the full volume object. On **v2.9.0 and earlier both were dropped on deserialization** and read back `null` even with the flag, so a pre-v2.10.0 binary cannot tell you whether a pod has a volume. Upstream reports the `networkVolumeId` also comes back *without* the flag now (it is free alongside the pod), but only the flagged path is covered by a test — pass `--include-network-volume` rather than relying on that |

`--status` filters **`desiredStatus` only** — `--status initializing` silently matches nothing.

### Reading pod logs (`pod logs`, v2.10.0+)

| | detail |
| --- | --- |
| output | **json lines**, one `{source,line,ts}` object per line — pipe straight to `jq`, no SSE frame parsing |
| `--source` | `container` (your workload's stdout/stderr), `system` (the platform narrating image pull, container create, start), or `both` (default) |
| termination | without `--follow` it replays history and **exits on its own** once lines stop arriving (`--max-wait`, default `5s`, bounds the wait). With `--follow` it streams until interrupted and reconnects itself if the connection drops |
| history | `--tail 0-5000` (default 100; `0` = live only), or `--since 30m|2h|7d|<rfc3339>`, which overrides `--tail` |
| what to read it for | a stalled deploy is a `system` story — repeated pull progress, or a `create container` that never reaches `start` |

## Serverless (alias: sls)

### Invoking an endpoint (`serverless run`, v2.9.0+)

| | detail |
| --- | --- |
| payload | the **handler** payload, sent as `{"input": <your json>}`. Must be a json object; parsed and size-checked locally (the api's `/run` body limit is 10 MiB), so quoting mistakes and oversized bodies fail as `usage_error` before the upload |
| `--input` vs `--input-file` | mutually exclusive; one is required. `-` reads stdin either way. A payload with its own top-level `input` key gets a warning — that is usually a whole curl envelope pasted in, which arrives double-wrapped |
| stdout | always the job payload, including a `FAILED` job's `error`, and the last payload seen when the wait ran out. Printed byte-faithfully (handler keys are not renamed or re-typed) |
| stderr | progress notes and the error object — never job data |
| exit codes | `0` when `COMPLETED`, and when `--no-wait`/`--wait 0` submitted successfully. `1` on request failure, on wait-budget exhaustion (`timeout`), or on `FAILED`/`CANCELLED`/`TIMED_OUT` (`job_failed`) |
| two budgets | `--wait` bounds the whole job; the shared `timeout` config key (30s) bounds one api call. A call inside a wait is clamped to what is left, never below 1s |
| `/run`, never `/runsync` | `/runsync` is not synchronous: the connection is released after ~90s with the job still running, no job id exists until it answers (so a slow response strands a billed, unpollable job), and a `sync-` job's result expires after 1 minute vs 30 for `/run` |

`serverless status <endpoint-id> <job-id>` polls a job submitted earlier; `serverless health
<endpoint-id>` returns worker + job counts.

### Reading worker logs (`serverless logs`, v2.10.0+)

Same flags and semantics as `pod logs` above, plus:

| | detail |
| --- | --- |
| output | `{source,line,ts,workerId}` — the extra `workerId` is what makes the no-`--worker` form usable |
| `--worker` | optional. **Omit it and the command resolves the endpoint's workers itself** and reads all of them at once, tagging each line. With `--follow` it also picks up workers that appear mid-run, so an endpoint scaling up does not need the command re-run |
| what to read it for | the crash loop: repeated `system` `start container` lines with **no** `container` output means the container exits before the handler runs, which leaves jobs sitting in the queue with nothing wrong with capacity |

### Endpoint update and zero values

`serverless update` sends **zero values** as of **v2.10.0** (`--workers-min 0`,
`--idle-timeout 0`, `--workers-max 0`, `--scaler-value 0`). On **v2.9.0 and earlier those were
silently dropped** from the request, so resetting a dev endpoint back to scale-to-zero looked
like it applied and the endpoint kept billing. On an older binary verify with `serverless get
<id>`, or `PATCH https://rest.runpod.io/v1/endpoints/<id>` with an explicit `{"workersMin":0}`.

`serverless update` has **no `--gpu-id` flag** — change an existing endpoint's GPU pool with
that same `PATCH` and `{"gpuTypeIds":[...]}`.

**Multi-DC** (`--network-volume-ids <v1>,<v2> --data-center-ids <dc1>,<dc2>`) needs
**runpodctl ≥ v2.4.0**; data does not sync between volumes automatically — golden path
[10](../../runpod/golden-paths/10-multi-region-ha-serverless.md).

⚠️ `serverless get --include-workers` returns raw v1 worker records **including
`RUNPOD_AI_API_KEY`/`RUNPOD_ENDPOINT_SECRET` in `env`** — don't paste its output into a ticket.

### Error codes worth branching on

`timeout`, `job_failed`, `wait_timeout` and `wait_interrupted` are the codes these commands
add, and `not_found` gains a nuance during a wait. They live with every other code in
[output-and-errors.md](output-and-errors.md#codes) — including which are safe to retry, which
mean work outlived the cli, and the `id` field that names a resource a failed wait left
behind.

## Models

`model add` supports upload sessions, versioning, metadata, and private-source credentials.
Concepts: [model-caching.md](model-caching.md); flags: `runpodctl model add --help`.

## Registry credentials

Prefer `registry create --password-stdin` (needs **v2.11.0+**) for scripts so the credential does not enter the
process table or shell history. A secret already held in an environment variable can be piped
without expanding its value into the runpodctl argument list:

```bash
printenv REGISTRY_TOKEN | runpodctl registry create --name "x" --username "u" --password-stdin
```

Redirecting a credential file to `--password-stdin` also works, including multi-line
credentials such as a GCR service-account JSON key. The command strips one trailing line
ending but preserves leading, inner, and other trailing whitespace.

`--password` remains supported for compatibility, but places the credential in `argv`.
When neither password flag is present and stdin is a terminal, runpodctl prompts without
echo. With non-terminal stdin and no password source it returns `usage_error` instead of
blocking; `--password` and `--password-stdin` are mutually exclusive.

## SSH

`ssh info <pod-id>` returns **connection details, not an interactive session** — and it has
three output shapes, only one of which is an error. That table is in
[output-and-errors.md](output-and-errors.md#parsing-ssh-info); read it before writing a
readiness loop. If interactive SSH isn't available, execute remotely via
`ssh user@host "command"`.

`ssh remove-key` takes `--name` **or** `--fingerprint`; use the fingerprint to disambiguate
keys that share a name.

## File Transfer

`send`/`receive` do encrypted, incremental, compressed transfer — don't pre-tar or
pre-compress the source. **Agent flow (one side sends, the other receives):**

1. Run `send <path>` **without** a code. The **first line of stdout is the one-time code**;
   `send` then blocks until the receiver connects — so capture that first line as it streams
   (background the process, tee to a log) rather than waiting for exit.
2. On the other machine (use `runpodctl ssh` into the pod/host if needed) run `receive <code>`
   with that exact code — positional, there is no `--code` flag. Each `send` mints a **fresh**
   code — never reuse or invent one.
3. Both processes must exit `0`. On failure, re-run `send` and use its **new** first-line code.

To push local files to a pod: get `ssh info <pod-id>`, start `send` locally (capture the
code), then `ssh` to the pod and run `receive <code>` there. For large/library-style data, a
network volume or the S3 API is often simpler than `send`/`receive`.

## Hub, templates, volumes, registry, info, utilities

Plain CRUD plus filters — `--help` is complete and this file would only go stale restating it:

```bash
runpodctl hub --help              # list/search/get; --type, --category, --owner, --order-by
runpodctl template --help         # list/search/get/create/update/delete; --type official|community|user
runpodctl network-volume --help   # list/get/create/update/delete
runpodctl registry --help         # list/get/create/delete
runpodctl gpu list --help         # + $/hr per cloud and dataCenterAvailability[]
runpodctl datacenter list --help  # alias: dc
runpodctl billing --help          # pods / serverless / network-volume
runpodctl user --help             # account + balance (alias: me)
runpodctl doctor                  # interactive: diagnose and fix cli issues
runpodctl completion              # auto-detect shell and install completion
```

Which of these to reach for, and the traps that are not flags (Hub worker selection, CPU
endpoints, template-vs-image, cost guards) are in the [SKILL.md](../SKILL.md) decision rules.
