---
name: runpod-mcp
description: >-
  Manage Runpod infrastructure through the connected Runpod MCP server's tool
  calls (pods, serverless endpoints and jobs, templates, network volumes,
  registry credentials, secrets, clusters, the GPU/CPU catalog, and billing),
  and connect the server when it is missing (hosted or local npx). Load it
  before the first Runpod MCP tool call of a request: it routes the task to the
  journey skill that carries the procedure, owns the answer contract and the
  rules on which resources you may change, and defers to runpodctl for the
  terminal, file transfer, and SSH setup; template project and Hub listing authoring
  routes to runpod-build-template.
allowed-tools: Bash(claude mcp:*)
compatibility: Linux, macOS, Windows
metadata:
  author: runpod
  version: "1.7.1" # x-release-please-version
  concepts: [runpod-platform, pod, serverless-endpoint, job, template, network-volume, registry-credential, gpu-type, log-stream, api-key, api-rate-limit]
license: Apache-2.0
---

# Runpod MCP

The Runpod MCP server exposes Runpod's control plane as structured tool calls, so an
MCP-capable agent can manage infrastructure without shelling out. It is the same Runpod
REST API that `runpodctl` uses. Pick MCP when its tools are connected (typed params,
structured errors, no shell quoting).

This skill does three things: it connects the server, routes each request to the
journey skill that carries its procedure ([Route by intent](#route-by-intent)), and owns
the **answer contract** below, which every reply follows.

**For a multi-step job, read the worked example before calling tools.** Tool calls are
easy to issue and easy to issue in the wrong order. The verified end-to-end sequences
live in [runpod/golden-paths/README.md](../runpod/golden-paths/README.md) (image →
template → endpoint, pod → volume → serverless, multi-region, autoscaling, monitoring).
The journey skills cover procedure within one journey; the paths cover what order to do
a whole job in.

## Connect

Connect the hosted server with **your API key as a Bearer header** if you also use runpodctl/flash. That one key auths the MCP *and* the CLIs (the 80% path):

```bash
claude mcp add --transport http runpod -s user https://mcp.getrunpod.io/ \
  --header "Authorization: Bearer $RUNPOD_API_KEY"
```

Plain **OAuth** ("Sign in with Runpod", via `npx @runpod/mcp-server@latest add`) is MCP-only: the CLIs stay unauthed, so use it only for MCP-only work. Local **stdio** runs the server as a subprocess with your key. Those variants + the key-vs-OAuth tradeoff: **[reference/connect.md](reference/connect.md)**. After connecting, reconnect the client (in Claude Code, `/mcp`) so the tools load.

**Verify it's live (do this before relying on MCP):** in Claude Code run `/mcp`.
`runpod` should show **Connected**, not *Needs authentication* (if it's the latter,
sign in there first; the bundled plugin server registers the URL but stays inert
until you authenticate). Confirm a real call works by asking for `list-endpoints`.
If the `runpod` tools aren't present at all, the server isn't connected: (re)run the
install above, or fall back to **runpodctl** for this task.

**Check the server version (which REST API it drives):** the MCP `initialize` handshake
returns it in `serverInfo.version`. `/mcp` in Claude Code shows it, or probe the hosted
server directly:

```bash
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
| curl -s -X POST https://mcp.getrunpod.io/ \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Authorization: Bearer $RUNPOD_API_KEY" -d @-
```

## The server is the source of truth

Once connected, read the server. Do not reason about its tools from memory.

1. **The tool list and every parameter** come from the client's own view of the
   connected server: `/mcp` in Claude Code, or `tools/list`. Each tool carries its
   own parameter descriptions, generated from Runpod's REST v2 contract. Check there
   before concluding a capability exists *or* doesn't. When a journey skill's tool
   binding disagrees with the live tool list, the live list wins.
2. **The server serves these same skills** from this plugin's release: `read-guide`
   (start with `read-guide runpod-mcp`) and the `runpod://guides/<id>` resources. With
   this plugin installed, the journey skills below are the procedure; the server's
   guides are the same text for an agent without the plugin.
3. **The wire contract** is the Runpod v2 OpenAPI document at
   `https://api.runpod.io/v2/openapi.json`, for fields beyond the tool surface.

One protocol quirk worth knowing, because it looks like a bug: delete tools can return
`isError: true` with "Unexpected end of JSON input" **even on success**, since the REST
API answers 204 No Content. Confirm with a follow-up `get-`/`list-` (a deleted resource
then 404s) rather than retrying the delete.

For concepts (pods vs serverless, GPU selection, storage), read `../runpod-usage/`.

## Use MCP vs runpodctl

- **Use runpod-mcp** when the tools are connected AND the task is infra CRUD,
  browsing/deploying an existing Hub listing, or a serverless job call the server
  exposes. Cap large job/log output to a file.
- **Use runpodctl instead** for: **`send`/`receive`** file transfer, **SSH** key
  management, **`doctor`** setup, **model cache**, or any shell-only agent, or
  when the user wants a reproducible command.
- **Pin the CUDA floor on every GPU create.** `create-pod` and `create-endpoint` take
  `gpu.minCudaVersion` (`"12.8"` by default, `"13.0"` only for a CUDA-13 image);
  `create-template` takes `allowedCudaVersions`. Without a floor the create accepts any
  host CUDA version, and a modern image can land on a host too old to run it. Why 12.8
  and when to use 13.0:
  [`runpod-usage` gpu-selection](../runpod-usage/reference/gpu-selection.md#step-3-pin-the-cuda-floor).
- **Hand pod creation to runpodctl** for a **multi-GPU priority list** (v2 `create-pod`
  takes one GPU type; check the live schema before assuming, and watch for a `_warning`
  on an otherwise-successful create), or for a **template + CPU** pod together, which
  v2 does not express. Each alone is fine in MCP: `templateId` (each field you pass
  replaces the template's whole value rather than merging) or `computeType: "CPU"`.
- **Not this lane:** authoring a template project or Hub listing files
  (→ [runpod-build-template](../runpod-build-template/SKILL.md)); writing/deploying
  your own Python with Flash (→ flash); downloading models or building/pushing
  images (→ companion-clis).

## Route by intent

| The user wants to… | Journey skill |
| --- | --- |
| Know what GPUs/workers/endpoints exist, what fits a model, what it costs | **discovery** |
| Create/inspect/update/delete pods, endpoints, templates, volumes, account secrets, SSH keys, clusters; inventory of the account | **lifecycle-crud** |
| Stand up a serverless endpoint for a model/workload and verify it with a real job | **serverless-deploy** |
| Host a ComfyUI workflow (workflow.json, custom Civitai models/LoRAs) as an endpoint | **serverless-deploy**, then its [ComfyUI reference](../serverless-deploy/reference/comfyui-serverless.md) |
| Rent/configure an interactive GPU pod; create a pod then pause/stop it for later | **pod-deploy** |
| Diagnose a broken/misbehaving pod (0 GPUs, CUDA, crashes, 502s) | **pod-doctor** |
| Operate an existing endpoint: jobs, scaling, workers, logs | **endpoint-ops** |
| Understand or reduce spend; billing breakdowns | **cost-audit** |
| Something the tools may not cover (file transfer, a command inside a Pod) | [Capability boundaries](#capability-boundaries--state-them-never-fake-them) below |

## Capability boundaries — state them, never fake them

This interface manages infra through the Runpod MCP tools. It does NOT do:
SSH sessions, file transfer to/from pods, local image builds, model downloads
to volumes, or interactive terminals. When a task needs one of those, say
that it is not available through these tools and name the lane that does it:
`runpodctl` for file transfer (`send`/`receive`), SSH setup and model
uploads; SSH or the console web terminal for commands inside a Pod; the Flash
SDK for code-first Serverless deploys; the console for Pod migration. Never
improvise a fake capability or silently drop that part of the task.

Check the served tool list before calling anything a gap: account secrets and
Instant Clusters were console-only once and are served tools now. The workaround
for each gap, and the discipline for answering one, are in
[reference/api-boundary.md](reference/api-boundary.md).

## Live reads before mutations

A template id, a GPU's stock or price, or a resource's state is confirmed with
a list- or get- tool before you act on it, even when a guide or an earlier
session named it.

## The answer contract

Every Runpod reply follows these rules. Journey skills add journey-specific
rules and report templates; they never weaken these.

**Facts come from tool reads, stated as facts.**
- Name the read behind each fact in the answer itself ("from the templates
  read", "from list-hub-repos", "from the pod's logs"): an image, a price or a
  stock figure stated without its read is not evidence, however correct.
- Quote real figures, names, and IDs from the reads you just made, not from
  memory and not rounded into vagueness. IDs verbatim.
- State current stock/status definitively ("RTX 4090 in EU-RO-1: available
  now"), never "should be", "probably", or "check later". The read you just
  did IS the check.
- Never contradict your own data: if your table says a card is available, the
  summary cannot call it out of stock.

**Commit; don't hedge, don't defer.**
- Diagnosis means ONE most-likely cause plus its concrete fix, chosen from the
  evidence, rather than a menu of possibilities or "run these commands and
  tell me".
- If the account state makes the question moot (nothing deployed, zero spend),
  say exactly that in one sentence and stop. An honest empty answer is
  complete.
- Never ask the user for information a tool could have given you. Push on
  with the tools you have; ask only when the user is the sole source: their
  credentials, their intent on a destructive step, a product choice.
- `create-cluster` always waits for an explicit go: never call it until the
  user has seen the shape (nodes, GPUs per node, data center) and the total
  hourly price from the catalog read and has said go in this conversation. A
  request to create a cluster asks for that plan and its price; the create
  waits for the go.
- When the request fixes a class but not the item ("a small model", "a 24 GB
  card", an image named without its settings), choose the documented default,
  state the choice in one line, and proceed. A setting the user did not
  mention is never a reason to stop; stop only when a wrong guess would spend
  heavily or destroy data.
- A request to deploy, set up or create something is the go for that create.
  Quote the hourly price from the catalog read in the same reply and make the
  call; never end the turn on "want me to go ahead?". Two things wait for an
  explicit go: a cluster (above), and a standing charge the user did not ask
  for by name, such as a warm worker. For those, create the part that bills
  nothing while idle, then quote the standing charge per hour and per month
  and offer it.

**Mutations bind to what this conversation created or the user named.**
- You may stop, update, or delete a resource created by your own tool calls
  in this conversation. You may also change the one resource the user named
  in the request by its id or an unambiguous name (a setting on one
  endpoint, one job on its queue), but only the change they asked
  for: a user-named resource is deleted only when the user asked for that
  delete. The user's instruction is the authority for that one resource, so
  do the change rather than handing them console steps. Otherwise, provenance
  comes from your create outputs, never from a name you found by listing. A
  disposable-looking name, an auto-generated slug, or a familiar prefix is not
  attribution.
- A cleanup or cost-cutting instruction does not extend that authority,
  however urgently it is phrased. For anything you cannot
  attribute to this conversation, the complete answer is the audit: what you
  checked, what qualifies, the ids, and the exact actions for the USER to
  take. That is a full answer, not a deferral. The commit-don't-hedge rule
  never licenses mutating a resource that isn't yours.
- When nothing this conversation created remains, say exactly that and touch
  nothing.
- Every write is checked by a fresh read. After a create or update, read the
  resource back and confirm the fields you set; after a delete, read again and
  confirm it is gone; after a job cancel or a queue purge, read the job or the
  queue again. For a settings change, also read the current values before the
  write, so the answer gives before and after, both from reads. The write
  call's own response is not that read, and the final message quotes what the
  read showed.
- A permission error on a resource you did not create is a correct answer,
  not an obstacle: report it as out of scope. Never retry it or advise
  re-running from a less-restricted session or key to get around it.

**The final message stands alone.**
- Close with a summary the user can act on without scrolling back: the ids,
  URLs, prices, and commands the task produced belong in it. No "the link
  above" and no pointer to an earlier turn.

**Carry the work as far as the tools allow.**
- Prefer a server-side wait (`wait` parameters) over handing the user a poll
  loop; check state between holds. When a wait outlasts what the tools can
  hold, report the evidenced state (what was created, what was submitted,
  what the worker states show) and the recommended next step. Offering to
  keep watching is fine; silently stopping mid-wait is not.

**Honest failure beats fabricated success.**
- Report failures with the observed evidence (the error body, the worker
  state, the log line). Never report a success without the artifact that
  proves it (the output the job returned).
- A missing credential or capability is reported as exactly that, with what
  you did to confirm it and what the user must supply.

**Use only the tools you were given.**
- If a tool is not available in this session, work with the ones that are;
  reads you already made can be analyzed directly. Never stall the task
  requesting new tool access.

**Report habits** (inventory, cost, deployment reports):
- Enumerations read best as tables carrying each resource's name and id.
- Every dollar figure comes from a billing/pricing read made this turn; give
  totals beside per-item figures, and show empty categories rather than
  silently dropping them.
- Lead the user to the number or verdict they asked for.

## Source & docs

- Server source: https://github.com/runpod/runpod-mcp
- Package (npm): https://www.npmjs.com/package/@runpod/mcp-server
- Hosted endpoint: https://mcp.getrunpod.io/
- Docs: https://docs.runpod.io
