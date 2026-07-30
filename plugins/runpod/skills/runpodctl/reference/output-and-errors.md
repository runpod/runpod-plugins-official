# runpodctl — output format, error codes, env vars

Everything an agent needs to parse runpodctl's output and decide what to do with a
failure. The 80% rule is in [SKILL.md](../SKILL.md#output--errors); this file is the
full surface.

**Version floor: runpodctl ≥ v2.8.0.** The coded error shape, the serverless `urls` object
and GPU pricing/per-DC availability all arrived in v2.8.0.

Older binaries (≤ v2.7.3) did **not** print plaintext — they printed
`{"error":"<message>"}` on stderr with no `code` and no `status`, and the message was
interpolated unescaped, so a message containing a quote produced malformed JSON. They also
dumped usage text after runtime errors. So the pre-v2.8.0 failure mode is *valid-looking
JSON with the field you're branching on missing* — **gate on `code` being present**, not on
whether stderr parses as JSON. `runpodctl version` is a weak gate: it prints plaintext, and
a binary built from source reports a placeholder version regardless of the code it contains.

## Output format

JSON is the **default** — the CLI is built for agent consumption, and data goes to
**stdout**.

```bash
runpodctl pod list                    # json (default)
runpodctl pod list --output=yaml      # yaml — the only alternative
```

**There is no table format** — `json` and `yaml` are the only values, matched
**case-sensitively**. An unrecognized value is not an error; it silently falls back to
JSON, so `--output=table` *and* `--output=YAML` both return JSON. Pass lowercase `yaml` or
don't pass the flag.

(The legacy `get pod` / `get cloud` commands print a human table on stdout and ignore
`--output` entirely — see [plaintext gaps](#plaintext-gaps).) Some commands print a human table on stdout regardless — the legacy
`get pod`/`get cloud` paths do — so a table on stdout is a signal you're on a legacy
command, not a format you asked for.

## Error format

Errors go to **stderr** as a single flat JSON object, and the exit code is
**non-zero**, so stdout parses as data.

```jsonc
{"error":"failed to get endpoint: endpoint not found","code":"not_found","status":404}
```

| field | notes |
| --- | --- |
| `error` | human-readable message, unwrapped on the REST path. A GraphQL HTTP failure whose body has no extractable message falls back to the **raw body**, which can itself be JSON — so never parse this field, either way |
| `code` | stable, lowercase, present on every JSON error (see [plaintext gaps](#plaintext-gaps)) |
| `status` | HTTP status — only when the failure arrived on a **non-2xx** response (REST *or* GraphQL) |

**Branch on `code`, never on `status` or the message text.** `status` is absent whenever
the API answered HTTP 200 with empty data, which is how GraphQL reports a missing
resource — so `if (status === 404)` misses every GraphQL not-found:

```jsonc
// serverless get <missing> — REST, so a status is available
{"error":"failed to get endpoint: endpoint not found","code":"not_found","status":404}
// template get <missing> — GraphQL answered 200/null, so there is no wire status
{"error":"failed to get template: template not found: bogus-template-id","code":"not_found"}
```

`code` is both: a typed code (from the API or from the error itself) wins, and the
output sink fills in a fallback when there isn't one — so local validation and transport
failures carry a code too, not just API responses.

### Codes

| code | meaning |
| --- | --- |
| `usage_error` | unknown command, unknown flag, bad/wrong-count args, or a **cobra-required** flag left out. Usage text prints after the JSON |
| `not_found` | the **API** does not have the resource |
| `bad_request` (400) `unauthorized` (401) `forbidden` (403) `conflict` (409) `rate_limited` (429) `server_error` (5xx) `api_error` | derived from the REST status |
| `graphql_error` | a GraphQL call failed: an `errors` array in a 200 body, **or** a non-2xx response from the GraphQL endpoint (that form also carries `status`) |
| `no_credentials` | no API key configured at all — set `RUNPOD_API_KEY` or run `runpodctl doctor` |
| `network_error` | the API could not be reached at all — DNS, connection refused, TLS, timeout |
| `cli_error` | anything else local: config, environment, and validation the command does itself |

Treat this as **the set the CLI generates, not an exhaustive list** — an explicit code
from the API is passed through lowercased, so a code outside the table can arrive from
the server. **Give your handler a default branch that treats an unknown code as fatal**
and surfaces `error` verbatim; never fall through to a retry.

### What to retry

**runpodctl has no internal retry** — it never backs off for you, so whatever your
wrapper does is all that happens.

- **Retry with backoff:** `network_error`, `rate_limited`, `server_error` (and `api_error`
  when `status` is 5xx). A transient `graphql_error` is possible too but indistinguishable
  from a permanent one, so cap those attempts tightly.
- **Never retry:** `usage_error`, `cli_error`, `bad_request`, `not_found`, `conflict`,
  `no_credentials`, `unauthorized`, `forbidden`.

Two invariants make that safe to encode:

- **`not_found` always means server-side.** A bad *local* path (say a mistyped
  `--model-path`) is `cli_error`, so `not_found` never means "you typed a path wrong".
- **`network_error` is the only code the CLI assigns to mean "couldn't reach the API"**,
  detected structurally. Deliberately *not* `network_error`: a malformed `RUNPOD_API_URL`
  and a local wait loop timing out (e.g. `--wait-for-hash`) are both `cli_error`, so a
  retry loop never fires for something a retry cannot fix.

### Auth failures are two different codes

`no_credentials` means **no key is configured**. A key that is present but wrong, expired
or revoked is `unauthorized` (401), and one lacking access to the resource is `forbidden`
(403):

```jsonc
// RUNPOD_API_KEY=rpa_bogus… pod list
{"error":"api request failed with status 401","code":"unauthorized","status":401}
```

Don't collapse these — re-prompting for a "missing" key when the real problem is a
revoked one sends an agent in a circle.

### Invocation mistakes split across two codes

`usage_error` covers what cobra validates: unknown command/flag, wrong arg count, and
missing `MarkFlagRequired` flags. Validation a command performs itself lands in
`cli_error`, even though it's just as much an invocation mistake:

```jsonc
// ssh remove-key with neither --name nor --fingerprint
{"error":"either --fingerprint or --name must be provided","code":"cli_error"}
```

So `cli_error` is a mixed bucket — "your invocation was wrong" *and* "your local
environment is wrong". Read `error` to tell them apart; don't retry either.

### Missing API key

The JSON-covered commands all report `no_credentials` — `pod` (`list`/`get`/`create`),
`template create`/`update`, every `ssh` subcommand, `model *`:

```jsonc
{"error":"api key not found. get your key at https://www.runpod.io/console/user/settings then: export RUNPOD_API_KEY=your-key OR run: runpodctl doctor","code":"no_credentials"}
```

```jsonc
{"error":"unknown flag: --nope","code":"usage_error"}
```

Usage text follows the JSON on stderr — and, unlike older builds, a *runtime* error no
longer dumps usage text after it.

### Exit codes, and what else is on stderr

Every failure on the JSON path exits non-zero (`model` and `update` used to print an error
and exit **0**; they don't anymore). The exceptions are in
[plaintext gaps](#plaintext-gaps) below.

**Non-empty stderr is not a failure signal.** Deprecation notices (`warning: 'runpodctl
get pod' is deprecated…`), `pod create` advisories (`note: …`) and config-migration lines
all go to stderr on successful runs. Gate on the exit code first, then parse stderr.

### Plaintext gaps

The JSON error shape covers `pod`, `serverless`, `template`, `volume`, `registry`,
`gpu`, `datacenter`, `billing`, `user`, `model`, `ssh`, `send`, `receive`, `hub` and
`update` — including every GraphQL call site (a GraphQL failure is `graphql_error`, or
`not_found` for the nil-data lookups). These surfaces still print plaintext and carry
no `code`:

| surface | shape |
| --- | --- |
| legacy `get`/`create`/`remove`/`start`/`stop pod`, `create`/`remove pods`, `get cloud` | `Error: <msg>` on stderr, exit 1 — including the missing-key case, which carries the same message as `no_credentials` but no JSON and no `code`. Success prints a human **table** on stdout, not JSON |
| `exec` (hidden, deprecated) | progress on **stdout**, error plaintext on stderr, **exit 0**; polls up to **5 minutes** for the pod's SSH info before giving up |
| `project` (hidden) | prints errors to **stdout** and exits **0** |

### Parsing `ssh info`

`ssh info` has three shapes, and only one of them is an error:

| situation | output |
| --- | --- |
| connectable | `{"id","name","ssh_command","ip","port","ssh_key":{…}}` on stdout, exit 0 — note **snake_case**, unlike the camelCase everywhere else in the CLI. A `"setup":"runpodctl doctor"` key appears when the local key needs fixing |
| pod exists, not connectable | `{"error":"pod not ready","id":…,"name":…,"status":…}` on **stdout**, exit **0**, no `code`. Here `status` is the pod's desired status, *not* an HTTP status |
| no such pod | `{"error":"pod 'x' not found","code":"not_found"}` on stderr, exit 1 |

So: check the exit code, then check for an `error` key even on stdout.

"Not ready" fires whenever the pod has no **public port 22**, which is not the same thing
as "still booting". A pod whose image never starts an sshd reports
`{"error":"pod not ready","status":"RUNNING"}` indefinitely — verified by creating a
`ubuntu:22.04` CPU pod and polling for ~70 s at `status: RUNNING` throughout. So **bound
any SSH readiness loop** and don't treat `RUNNING` as "SSH is coming"; if it never arrives,
the image is the problem, not the wait.

So a parser should tolerate a non-JSON line on stderr from those, and must not rely on
the exit code for `exec` or `project`. Prefer the non-legacy equivalents: `pod
get`/`pod create`/`pod delete`, and `ssh info <pod-id>` + your own `ssh` invocation
instead of `exec`.

## Environment variables

| variable | default | what it sets |
| --- | --- | --- |
| `RUNPOD_API_KEY` | — | API key. Also settable via `runpodctl doctor` or `~/.runpod/config.toml` (`apikey`) |
| `RUNPOD_API_URL` | `https://rest.runpod.io/v1` | REST control plane (config key `restApiUrl`) |
| `RUNPOD_GRAPHQL_URL` | `https://api.runpod.io/graphql` | GraphQL control plane (config key `apiUrl`) |
| `RUNPOD_INVOKE_URL` | `https://api.runpod.ai/v2` | base for the invoke URLs reported by `serverless create`/`get`/`list`/`update` (config key `invokeUrl`) |

**Invoke is a separate service from the control plane.** Pointing `RUNPOD_API_URL` or
`RUNPOD_GRAPHQL_URL` at a non-prod host does *not* move the invoke URLs — override
`RUNPOD_INVOKE_URL` explicitly when you need that, or the emitted URLs target prod.

## Serverless invoke URLs

`serverless create`/`get`/`list`/`update` return a `urls` object, computed from the
endpoint ID, so a freshly created endpoint is callable without a second lookup:

```jsonc
"urls": {
  "run":     "https://api.runpod.ai/v2/<endpoint-id>/run",
  "runsync": "https://api.runpod.ai/v2/<endpoint-id>/runsync",
  "health":  "https://api.runpod.ai/v2/<endpoint-id>/health"
}
```

`status` isn't in the object; it's `<run url minus /run>/status/<job-id>`.

## GPU pricing and per-data-center availability

`gpu list` reports on-demand price per hour per cloud type plus a per-DC stock
breakdown:

```jsonc
{
  "gpuId": "NVIDIA A100 80GB PCIe",
  "displayName": "A100 PCIe",
  "memoryInGb": 80,
  "secureCloud": true,          "securePricePerHr": 1.39,
  "communityCloud": true,       "communityPricePerHr": 1.19,
  "stockStatus": "Low",         "available": true,
  "dataCenterAvailability": [
    {"dataCenterId": "CA-MTL-3", "stockStatus": "Low"},
    {"dataCenterId": "EU-RO-1",  "stockStatus": "none"}
  ]
}
```

- A price is **explicitly `null`** when that cloud type doesn't offer the GPU, which is
  distinguishable from a real `0`. Read `securePricePerHr`/`communityPricePerHr` rather
  than guessing that a lower tier is cheaper.
- Top-level `stockStatus` is the **best status across data centers** — use
  `dataCenterAvailability[]` as ground truth for *where* a create will actually
  schedule, especially when co-locating with a network volume.
- An unrecognized non-empty status now ranks above absent/`none` instead of tying with it,
  so **`available` no longer reports `false`** for a GPU whose only status is a value the
  CLI doesn't know. It still ranks *below* `Low`, so a known level still wins the top-level
  `stockStatus` — that tradeoff is deliberate, and it's why `dataCenterAvailability[]` is
  the field to read. Casing and surrounding whitespace are normalized now, so they are no
  longer a source of unknown values.
- Two sentinels for one concept: the per-DC breakdown spells an unreported status
  `"none"`, while the top-level field **omits the key** for the same condition. Handle
  both.
- **Stock values are capitalized levels but the sentinel is lowercase** — `"High"`,
  `"Medium"`, `"Low"`, `"none"` in practice. `"unavailable"`, `"out of stock"` and
  `"no stock"` also count as no-stock, and comparison is case-insensitive internally, so
  lowercase before testing and don't write `if s != "none"`.
- **`gpu list` hides no-stock GPUs by default.** Pass `--include-unavailable` when
  targeting one data center, or you may never see a GPU that has stock only there.

Two scoping limits the fields don't express:

- **The prices are pod on-demand rates** (`gpuTypes { securePrice communityPrice }`). They
  are not serverless rates — serverless bills per request-second — so don't present them
  as the cost of an endpoint.
- **`dataCenterAvailability[]` has no cloud-type attribution**, while pricing is split
  secure vs community. "Cheapest option that schedules in DC X" therefore isn't answerable
  from `gpu list` alone; treat it as two separate reads.

And when you act on the choice: pin placement with `--data-center-ids`, or the analysis
doesn't constrain anything. For serverless, `--gpu-id` takes a GPU *type* id and is
translated server-side to a GPU **pool**, so the endpoint may run on more than the one
card you priced (pool vs type ids: [`runpod-usage` gpu-selection](../../runpod-usage/reference/gpu-selection.md)).
