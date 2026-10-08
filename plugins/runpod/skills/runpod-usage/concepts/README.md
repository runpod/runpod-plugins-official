# Concept file format

Each concept is one YAML file named `<id>.yaml`. To add one, follow the
`add-concept` skill in `.claude/skills/add-concept/SKILL.md` at the repo root. Every file is
public-facing: everything in it must be safe to show a customer and backed by a
public source.
The exact schema is `ontology/tools/src/schema.ts`. `pnpm validate` (run it in
`ontology/tools/`) checks every file against that schema, against the other files and against the
REST v2 spec.

```yaml
id: pod                         # kebab-case; matches the file name
name: Pod
kind: resource                  # see "Kinds"
summary: One or two customer-facing sentences.
product: pods                   # the console product it sits under, or null
is_a: null                      # kind-of parent (cpu-pod is_a pod)
part_of: null                   # the whole it belongs to (worker part_of serverless-endpoint)
aliases: [GPU pod, instance]

surfaces:                       # the same thing, named on every surface
  rest_v2:   { schema: Pod, paths: [/v2/pods, "/v2/pods/{id}"] }
  graphql:   { type: Pod, queries: [], mutations: [podFindAndDeployOnDemand] }
  mcp:       [create-pod, get-pod]
  runpodctl: [pod create, pod get]
  console:   Pods

fields:                         # REST v2 names are canonical
  - { name: "mounts.network[].volumeId", type: string, ref: network-volume, set: create }

states:                         # only for concepts with a lifecycle
  field: status
  values: { RUNNING: The container is running., EXITED: The pod is stopped. }
  transitions:
    - { action: stop, from: [RUNNING], to: EXITED }
  on_invalid_action: 409
  evidence: [...]

relations:
  - { type: located_in, target: data-center, cardinality: "1" }

steps:                          # only for kind: process, at least two, in order
  - id: stop
    title: Stopping releases the GPUs
    description: What happens in this step.
    concepts: [pod, machine]            # concepts the step involves
    rules: [pod.stopped-pod-keeps-host] # existing rules that govern it

rules:
  - id: pod.network-volume-same-dc      # <concept-id>.<slug>, unique across all files
    applies_to: ["field:mounts.network[].volumeId", field:dataCenterIds]  # omit for concept-wide rules
    statement: One to three sentences an agent can act on.
    on_violation: 400                   # optional: what the caller observes
    status: documented
    conflict: false
    see: [network-volume.placement-immutable]   # related rules on other concepts
    evidence:
      - { source: rest-v2-spec, ref: NetworkMount.volumeId, seen: 2026-09-28 }
      - { source: public-docs, url: "https://docs.runpod.io/storage/network-volumes", note: Why it matters. }
      - { source: skill, path: plugins/runpod/skills/runpod-usage/reference/storage.md }
```

Run `pnpm format` in `ontology/tools/` after editing. It rewrites every file in this style
(key order, folded text wrapped at 80 columns, one-line list entries, quoting where YAML needs
it) without changing the data, and CI runs `pnpm format:check`.

## Kinds

| Kind | Meaning | Examples |
|---|---|---|
| `platform` | The root | runpod-platform |
| `resource` | Has its own id and CRUD operations in the API | pod, serverless-endpoint, template, network-volume |
| `component` | Part of a resource, with no CRUD of its own | worker, job, container-disk, exposed-port |
| `catalog` | Read-only reference data | gpu-type, data-center, cloud-tier, public-endpoint |
| `capability` | Something you do with a resource | pod-ssh-access, log-stream, flashboot |
| `billing` | Charges and credit | billing-record, pod-billing, savings-plan |
| `limit` | A cap or quota | api-rate-limit |
| `tool` | A Runpod SDK or CLI the customer runs | flash |
| `external` | Referenced by Runpod but not owned by it | container-image |
| `infrastructure` | Runpod hardware a resource runs on, not managed directly | machine |
| `process` | How something works, as ordered steps across concepts | pod-deployment |

## Relations

The hierarchy lives in `is_a` and `part_of`. `relations` uses a closed set of types:

| Type | Meaning |
|---|---|
| `requires` | Cannot exist without the target |
| `uses` | Optionally references the target |
| `located_in` | Pinned to the target |
| `runs_on` | Executes on the target |
| `billed_by` | Its charges appear under the target |
| `constrained_by` | Capped by a limit or a catalog entry |

A field with `ref:` is an edge too, called `field_ref` in the SQLite `edges`
view. A process links to every concept its steps involve with an `involves`
edge.

## Processes

A `process` explains how something works over time, such as what happens when
a pod is deployed, stopped and restarted. Its `steps` are in order. Each step
names the concepts it involves and the existing rules that govern it, so the
facts stay on their concepts and the process ties them into a sequence. Put a
rule on the process itself only when it is about the flow as a whole.

## Status, evidence and conflicts

| status | Meaning |
|---|---|
| `documented` | Stated in the REST v2 spec, the public docs or a public skill |
| `verified` | Observed on a live account |

Each evidence entry has a `source` and the keys a reader needs to find it.
`note` adds context but never stands alone. `seen` is the date the source was
checked.

| source | What it is | Requires |
|---|---|---|
| `rest-v2-spec` | The REST v2 OpenAPI spec (`https://api.runpod.io/v2/openapi.json`, vendored at `testdata/runpod-migrate/v2-openapi.json`) | `ref` |
| `public-docs` | docs.runpod.io and the public GraphQL reference | `url` |
| `skill` | A skill file in this repo, cited by `path` from the repo root | `path` |
| `live-probe` | A request made against a live account | `ref`, `seen` |
| `other` | Anything else public, such as a CLI's `--help` output | `ref` or `url` |

A `url` must be https on a public source host: docs.runpod.io, api.runpod.io,
graphql-spec.runpod.io, runpod.io, huggingface.co, or a public `runpod`
repository on github.com. The list is `PUBLIC_HOSTS` in
`ontology/tools/src/validate.ts`; add a host there when citing a new public
source.

Set `conflict: true` only when two public sources disagree. The statement gives
both readings and tells the agent how to act, and the evidence cites both
sources. A live probe settles it.

## Writing style

- Write plain present tense in complete sentences. A statement is one to three sentences; a summary is one or two.
- Say what holds and, where it helps, what to do: "Set `dataCenterIds` to the volume's data center."
- Put code identifiers in backticks: fields, enum values, paths, environment variables, commands and headers.
- Write "Runpod". Capitalize "Pods" and "Serverless" only as product names. "Pod", "endpoint", "worker", "template" and "network volume" are lower-case generic terms.
- Keep statements durable. Avoid "currently", "today", "not yet" and similar words. When a fact may change, the evidence's `seen` date records when it was checked.
- Prefer positive claims. A claim that something does not exist needs the spec or docs as evidence, with a `seen` date.
- Avoid prices and other figures that change often, unless the spec or public docs state them as a limit.

## What the validator enforces

- Every file matches the schema, and its `id` matches its file name.
- Every `is_a`, `part_of`, relation target, field `ref`, `see:` and step reference resolves.
- Only a `process` has `steps`, and a process has at least two.
- Every `applies_to` names a field, state or action the concept declares.
- Every REST v2 schema, path and field root exists in the vendored spec.
- The `is_a` and `part_of` chains have no loops.
- No file names internal systems, internal source ids, private repositories or internal tools.
- Every evidence entry has the keys its source requires, and every `url` is on a public source host.
- No file uses time-bound wording.
- Every `skill` evidence `path`, on rules and on `states`, points at a file that exists in this repo.
