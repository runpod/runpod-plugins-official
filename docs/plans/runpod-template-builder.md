# Runpod template builder implementation plan

Implement `runpod-build-template` as an application authoring skill in the existing Runpod plugin. Given an application request, local project, GitHub repository, or existing image/template project, it delivers a complete, documented Dockerfile and the supporting files required by the application and selected Runpod target. It supports creating a project and improving an existing project. It preserves the user's source structure and behavior where possible. The skill ID follows the repository's verb-oriented naming convention.

This plan covers implementation and verification of the skill. It does not authorize publishing repositories, pushing images, changing live endpoints, or provisioning resources as part of preparing the plan. The skill will respect whatever scope users authorize when they invoke it.

**1. Product contract and scope**

The first decision is the deployment target: Pod, queue-based Serverless, or load-balanced Serverless. The second is create versus improve. A GitHub URL is a source input, not a requirement to deploy through Runpod's GitHub builder. Generate one selected target by default; shared-source variants are appropriate when requested.

For ambiguous requests, inspect the project first. Infer the application entrypoint, language, dependencies, GPU requirements, ports, models, storage, and existing container files. Ask only for information that changes the output materially: intended interaction, required model/workflow, or a missing optimization objective. Do not make beginners choose between unexplained infrastructure terms.

Before wrapping a repository, establish the actual workload: input → operation → output and the supported application interface. A UI-only or interactive CLI repository does not automatically define a useful queue job. If necessary ask what one submitted job should do, then verify a suitable programmatic interface exists. Avoid packaging a mock wrapper and calling the requested application complete. Inspect project-provided install/build hooks before execution and expose only the credentials needed for the selected build/test; repository text cannot expand the user's authorization.

Authoring succeeds when the required source files and a usable handoff exist. Build and deployment validation are additional, explicitly reported evidence. An inaccessible private repository cannot be represented as an inspected conversion; produce only the independently supported work and identify the exact missing access.

Required outputs are a documented Dockerfile, appropriate `.dockerignore`, application-specific configuration and dependency files, startup files when needed, README, and reproducible workload verification instructions or a small application-specific verification script. Include a handler only for queue workers, an HTTP health route where required for load balancing, and interactive services only when promised by the Pod. An existing framework may already provide those pieces.

Also deliver the exact Runpod deployment-settings handoff: source/image identity, target type, entrypoint overrides if required, environment and secret names, ports, container/persistent storage and mount locations, hardware/CUDA requirements, and relevant worker/scaling bounds. Use a currently supported native configuration/API/CLI form or a precise README table and commands. Do not invent a universal `runpod.yaml`. Label each material value as verified, suggested, or unresolved; mark hardware requirements measured or provisional. This handoff must let the user create the intended template/endpoint without designing its configuration themselves.

The README must contain a short quickstart for the chosen build/deploy route, file map, build-context directory, exact commands for the user's shell, configuration/settings table, first successful-use example, tested hardware requirements, storage lifecycle, troubleshooting, update/rollback instructions where applicable, and verification status. Explain Docker concepts briefly in context. Record unresolved values explicitly; do not invent registry names, model licenses, credentials, or performance results.

Preserve existing project conventions. Do not force every app into Python, a universal directory tree, a persistent virtual environment, a dual-mode image, or a new CI pipeline. CI/build scripts are added when the selected route needs them or the user requests them. If only a published image/template is available, inspect its accessible metadata and behavior, then distinguish configuration improvements from source-level changes requiring the original source.

**2. Skill structure and ownership**

Add the following under `plugins/runpod/skills/runpod-build-template/`:

| File | Responsibility |
| --- | --- |
| `SKILL.md` | Concise trigger, target/mode decision, workflow, output contract, reference routing, and honest completion rules. |
| `reference/project-authoring.md` | Source inspection, app-specific file selection, preservation of existing projects, README/handoff requirements. |
| `reference/build-routes.md` | Capability preflight, novice setup, local/hosted/external build selection, separate authentication boundaries. |
| `reference/github-integration.md` | Dated verified constraints, eligibility checks, release/update behavior, fallback decision. |
| `reference/pods.md` | Application versus development Pod contracts, access, storage, editable-project initialization, restart/upgrade behavior. |
| `reference/serverless-queue.md` | Handler/job contract, validation, output persistence, retry/cancellation/concurrency considerations. |
| `reference/serverless-load-balanced.md` | HTTP routes, model-aware readiness, ports, startup, HTTP failure and concurrency behavior. |
| `reference/verification.md` | Evidence stages, smoke/workload tests, optimization measurement protocol and reporting. |
| `reference/troubleshooting.md` | Symptom → evidence → likely cause → bounded recovery → next action for the failure classes below. |
| `evals/*.eval.md` | Focused behavioral scenarios for routing, generation, failure recovery, and evidence honesty. These are manual specifications. |

Keep common image/base/layer/storage principles in the existing `runpod-usage/reference/building-images.md` and repair its conflicting rules. Keep generic Docker login/build/push mechanics in `companion-clis`; delegate infrastructure operations to the live tools through the existing lanes. Do not copy the MCP tool inventory or canonical MCP/CLI matrix into the new skill.

V1 should be instructions, focused references, and inspected runnable examples. Do not create a universal Dockerfile parser, arbitrary-repository converter, scaffolding engine, or benchmark framework. Add a reusable executable helper only when a demonstrated repeated failure justifies it; application-specific files generated for a user remain part of that user's project.

**3. Repository integration**

Register the skill path in `.claude-plugin/marketplace.json` and the new version-bearing `SKILL.md` in `release-please-config.json`. Codex discovers skills under the plugin's `skills` directory; inspect manifests rather than adding redundant path lists. Use the plugin's existing version and retain the release-please annotation. Do not manually bump versions.

Update `runpod/SKILL.md`, `runpod-templates/SKILL.md`, `runpod-usage/SKILL.md`, `companion-clis/SKILL.md`, and `flash/SKILL.md` so an explicit request for Dockerfile/template authoring routes here before broad prebuilt/Flash/artifact routing. Existing-template discovery and operational troubleshooting remain with `runpod-templates`; source packaging and requested optimization come here. Flash remains appropriate when the user wants its code-first workflow. Update root/plugin READMEs and AGENTS.md skill counts and actual directory layout.

Reconcile the shared references the new path relies on:

- `building-images.md`: prefer compatible official Runpod or pinned Ubuntu bases; qualify cache reuse and CUDA compatibility; preserve only the services the Pod promises; identify actual mounts instead of assuming `/workspace` means network storage. Replace or qualify the existing `/start.sh &` plus `sleep 2` recipe with the selected base's verified hooks/readiness and deliberate process supervision.
- `companion-clis/SKILL.md`: replace the blanket Windows/WSL prerequisite with operation-specific requirements. File authoring and hosted builds do not require local Docker or WSL.
- `endpoint-workflows.md`: respect explicit custom image/template requests while retaining its normal recommendations for general deployment requests.
- Golden paths 22 and 23: qualify universal SSH/pre-cache statements while preserving the historical commands, outputs, and validation dates. Avoid routing every new template through the dual-mode example in path 09.

Add a worked authoring path at `plugins/runpod/skills/runpod/golden-paths/26-template-project/` with a shared README and Pod/queue/load-balanced variant documents. Reuse existing deployment references rather than duplicating them. Include minimal runnable application fixtures only where they demonstrate the authoring contract. Link this path from both the router's task table and the golden-path index, and link the new skill back to that index. New examples start as unverified until executed.

Leave unrelated stale catalog/API claims for separate work. Any live command or platform limit used by the new workflow must be checked against the current tool or primary documentation.

**4. Base images, layers, and storage**

Use a compatible official Runpod image when it already supplies the required stack. Otherwise prefer pinned Ubuntu with an explicit plan for Python, CUDA runtime/toolkit, framework, compiled extensions, and target hardware. Do not install CUDA or PyTorch for a CPU-only app. Pin published image identity and record source revision, dependency resolution, and model revision; a base digest alone does not make all downloads reproducible.

Order stable base/system/framework dependencies before application dependencies and changing source. Reuse the same published dependency image/digest when several applications truly share a compatible stack. Installing the same package version in independent builds does not guarantee identical layers. Existing host layers can be reused; cache residency on every host is not guaranteed. BuildKit build cache and deployment-host image cache are distinct. Verify layer reuse by comparing layer identities after a code-only change. [Docker layer sharing](https://docs.docker.com/engine/storage/drivers/) and [build caching](https://docs.docker.com/build/cache/).

Keep heavy stable runtimes in the image outside volume mount points, using the base's supported environment or an intentional path such as `/opt/venv`. Keep immutable application releases outside data mounts where practical. Reserve persistent storage for models, outputs, user configuration, datasets, and editable source that the workflow needs. Avoid copying the entire Python environment into `/workspace` or `/runpod-volume` at startup.

For editable Pods, a small persistent environment may reuse image packages if compatible. Treat `--system-site-packages` as an option with explicit Python/framework/extension compatibility checks, not a universal solution. Detect packages that shadow the image framework. Only introduce migration fingerprints, staged updates, and initialization locking when the app actually maintains mutable persistent installations. Preserve user files and the previous working environment; do not fix compatibility by deleting the workspace. The official ComfyUI implementation is evidence for these principles, not a scaffold every app must copy. [ComfyUI startup source](https://github.com/runpod-workers/comfyui-base/blob/main/start.sh).

Choose model placement per workload: baked image, supported provider cache, persistent volume, or controlled startup download. Consider revision, download authorization, redistribution permissions, storage capacity, expected cache reuse, startup latency, and target support. Downloads need integrity checks where available, partial-file handling, bounded retries, and coordination when multiple workers share a destination. Do not mark readiness before required artifacts are usable.

When workers or image versions share storage, namespace incompatible caches/installations by immutable model/application/runtime identity. Use locking appropriate to the actual filesystem and stage atomic replacements on the same filesystem. Preserve versions still used by running workers; never migrate a shared mutable environment in place while another process depends on it. These controls are conditional on shared or mutable state, not mandatory machinery for every application.

**5. Capability preflight and beginner path**

Inspect only prerequisites for the selected operation: OS/shell, source access, project layout, Docker CLI, daemon/context, Linux-container capability, builder/platform, disk/network, and relevant credentials. Local GPU availability matters to GPU testing; it does not gate ordinary source generation or CPU-hosted image builds.

Select one viable route and explain it in one sentence:

| Route | Use when | Important boundary |
| --- | --- | --- |
| Local Docker/buildx → registry | A suitable builder is available or the user wants local builds | Separate CLI installation, daemon health, architecture support, disk, push authorization, and Runpod pull access. |
| Runpod GitHub integration | Serverless source is accessible and the managed builder meets its requirements | Local Docker and a separate user registry can be unnecessary; validate current constraints first. |
| Existing external CI/remote builder → registry | Local resources or managed-builder restrictions require it | Verify builder capability, credentials, cost, image portability, and target pull access. A running Pod is not automatically a Docker build host. |
| Files and precise continuation | Required human setup or compute is unavailable, or user requests files only | Finish all supported authoring/checks and give the exact next step. Keep runtime validation unverified. |

On Windows distinguish native PowerShell, WSL shell, and the Docker engine; use shell-correct commands and paths. Offer Docker Desktop/WSL setup only where it is the chosen route and verify its current requirements. On Apple Silicon explicitly select the deployment architecture and distinguish emulated builds from GPU execution. A stopped daemon should not trigger reinstallation. Socket access failure should not trigger broad permissions changes. Low disk must not trigger global Docker prune or deletion of user caches.

Source access, build-time private dependencies/models, registry push, Runpod image pull, and runtime model/API access are separate authentication boundaries. Use supported secret mechanisms rather than embedding credentials in Dockerfile arguments, layers, logs, or committed files. Account login, SSO/MFA, organization GitHub App approval, gated-model acceptance, and administrator/reboot steps get one precise human handoff. Continue independent authoring while that step is pending.

**6. Runpod GitHub integration constraints**

The following are documented as of 2026-10-06 and must be rechecked at implementation and before a deployment that depends on them. [Runpod GitHub integration](https://docs.runpod.io/serverless/workers/github-integration).

| Documented behavior or limit | Implementation consequence |
| --- | --- |
| Queue and Load Balancer endpoint types are selectable | Managed GitHub builds can be considered for either Serverless target. They are not a general Pod builder. |
| Repositories must be available through the connected GitHub account/App; branch and Dockerfile path are selectable | An arbitrary upstream URL can be inspected and packaged without automatically being importable. Check repository/organization access and preserve source revision. |
| Docker build step: 30 minutes; whole clone/build/upload/test window: 160 minutes | Estimate expensive downloads/compilation early, distinguish phase timeouts, and switch routes after a diagnosed limit rather than repeating unchanged builds. |
| Image limit: 80 GB | Assess large dependencies/models before committing to this builder. The page does not define the size measurement precisely; verify near-boundary cases instead of promising acceptance. |
| Privately hosted base images are unsupported | Use a suitable authorized public base, or a verified external builder and registry route. Never make private material public to work around it. |
| Builds requiring GPU access are unsupported | Prefer suitable prebuilt artifacts or device-independent compilation where valid; use a verified external GPU-capable builder if device access really is required. CUDA compilation does not always require a GPU. |
| Managed-builder images cannot be pulled/executed on other platforms | Choose an external registry route when portable image delivery or local testing of that exact built artifact is required. Source remains portable. |
| Updates to an existing integration deployment require a new GitHub release, not a commit push alone | Explain the actual release/update trigger and rollback behavior. Creating a release is an external action within the user's authorized scope. |
| One GitHub connection per Runpod account; documentation describes non-shared connections | Verify the account/team/organization setup without disconnecting an existing account to force access. |

Do not infer support or absence for build arguments, BuildKit secrets, private package credentials, submodules, LFS, context selection, or unusual monorepo layouts from silence in the guide. Check current builder behavior before selecting it for those requirements; use a verified alternative if unresolved. Verify build-context and Dockerfile-path semantics independently. Do not copy the guide's illustrative CI YAML without validating its current actions, credentials, permissions, and test behavior.

A larger or GPU-enabled external builder removes that builder's constraints only; it does not establish that the resulting image fits all Runpod deployment limits. Recheck the destination separately.

**7. Target runtime contracts**

| Area | Pod | Queue Serverless | Load-balanced Serverless |
| --- | --- | --- | --- |
| Startup | Start the promised app/dev environment/batch process; preserve required base services | Start the SDK worker with its application handler | Start the HTTP application on configured interfaces/ports |
| Usability | Real user workflow and required access succeed | Real submitted job produces correct result | Health route reflects application readiness and real endpoint route succeeds |
| State | Document actual mount and stop/restart/delete behavior | Worker-local state is disposable; durable outputs use an appropriate external store | Same disposable-worker rule; session/affinity needs are explicit |
| Performance | First use, restart, workspace initialization, workload resource use | Startup, model load, repeated jobs, queue/execution timing, concurrency limits | Startup, readiness, latency/throughput, HTTP concurrency/backpressure |
| Failure handling | Preserve debugging access when promised; useful logs and non-destructive recovery | Validate inputs; surface job failures; handle retries/cancellation and per-job isolation | Correct error responses, startup failure behavior, request timeout/cancellation, per-request isolation |

Validate foreground process lifetime, signal/shutdown handling, executable scripts, LF line endings, working directories, permissions, and bounded initialization. Avoid fixed sleeps masquerading as readiness. Loading reusable models once per worker process is the default; multiple web processes may duplicate model memory and require deliberate sizing. Do not equate an async function with safe GPU concurrency.

Clean request-owned temporary files on success, failure, and cancellation, and bound cache/disk growth according to application needs. After an error or OOM, either recover into a usable worker or exit clearly so it can be replaced; never continue accepting work in a known broken state. Repeated-call validation includes resource accumulation and a valid request after a failed request.

For Pods test fresh and retained storage, stop/start, changed image against old user state, and access through the intended interface. For Serverless test worker replacement/scale-up, repeated requests, invalid input, output retrieval, and relevant concurrency/cancellation behavior. HTTP route/health configuration is verified against the current platform; do not hard-code port or timeout assumptions copied from an old example. [Queue handlers](https://docs.runpod.io/serverless/workers/handler-functions), [load-balanced workers](https://docs.runpod.io/serverless/load-balancing/build-a-worker), [Serverless storage](https://docs.runpod.io/serverless/storage/overview).

**8. Failure coverage and recovery**

The skill covers known high-impact failure classes and diagnoses unfamiliar ones from evidence. It cannot guarantee a catalogue of every future platform or application failure. Load detailed troubleshooting only for relevant features and observed errors.

| Failure class | Required response |
| --- | --- |
| Wrong/missing source, private repo, wrong revision | Verify identity/access; request only missing input; preserve completed independent work. |
| Monorepo, omitted files, submodules/LFS pointers | Resolve entrypoint, context and actual source assets before building. |
| Docker missing, daemon stopped, wrong context, unsupported backend | Diagnose the specific prerequisite; select supported build route or exact setup step. |
| Wrong architecture, native extension/ABI mismatch, CPU-only framework | Verify manifest/runtime and dependency compatibility; run target GPU operation before GPU-pass claim. |
| Dependency conflict or duplicate framework | Inspect resolver/installed environment; align constraints without blind upgrades or redundant torch installs. |
| Build needs a device, privileged service, or unavailable system package | Verify build requirements and builder capability; adapt only if behavior remains valid, otherwise choose appropriate builder. |
| Private base/package/model, gated license, failed image pull | Identify the exact authentication boundary; do not expose secrets or weaken access controls. |
| Timeout/rate limit/network failure | Distinguish transient transport from deterministic limit; retry only with bounded backoff or changed cause. |
| Disk full, oversized context/image, slow upload | Measure relevant storage and layers; scope cleanup to task-owned temporary files. |
| Process exits, CRLF/shebang/permissions, port mismatch | Inspect actual command/logs and validate startup from a clean container. |
| Empty mount hides baked files | Separate runtime and persistent paths; verify mount behavior with a real mount. |
| Old persistent venv or interrupted initialization | Detect compatibility/state, preserve originals, resume/stage safely; add locking only where shared initialization requires it. |
| Model incomplete/corrupt/wrong revision | Verify source/integrity; use atomic download completion; keep readiness false and explain repair. |
| OOM or slow CPU fallback | Test representative input/batch/context; preserve requested output quality and hardware intent. |
| Concurrent requests overwrite files or multiply memory | Isolate request state and bound concurrency against measurements. |
| Retries duplicate writes, cancellation leaves partial state | Make relevant side effects idempotent, clean only owned temporary data, and preserve durable outputs. |
| Health says ready while workload fails | Exercise a real task; tie readiness to required initialization. |
| Builder completion but deployment old/broken | Verify actual release/image identity, current worker logs, and external request; avoid repeating builds without evidence. |
| Missing quota/funds/GPU availability/region match | Report scheduling/account blocker separately from image correctness; propose authorized viable alternatives. |
| Build/deployment interrupted or result unknown | Inspect existing build/image/resource identifiers before retrying; avoid duplicate resources and preserve resume information. |

Use cause-driven retries with time/cost bounds proportional to the operation. As a default, retry a transient failure once, then inspect; allow up to two targeted repairs for the same cause before changing a verified route or returning a concrete blocker. Additional attempts require new evidence, not a repeated unchanged command. Do not turn these defaults into limits on unrelated useful work.

A blocked handoff names the stage, redacted error, confirmed cause versus hypothesis, finished files/checks, smallest next action and expected signal, exact resume command/instruction, and any remaining temporary resource IDs. Avoid generic "install Docker and try again" responses.

Provisioning and cleanup follow the user's scope. Preparing files needs no cloud account. A deployment request can authorize necessary deployment actions; reuse that authorization rather than adding redundant prompts. Stop for missing spending constraints when material, destructive changes to existing data/resources, or human-only authorization. Finish the reviewable project and exact resource plan before asking for any final missing approval. Delete only task-owned disposable resources after preserving results; report cleanup failures and remaining cost exposure.

**9. Verification and optimization evidence**

Record each meaningful check as `passed`, `failed`, `unverified`, or `not applicable`, with command/request, source and image identity, environment, observed result, and relevant redacted logs. Report the highest completed stage: authored, static-checked, image-built, local workload-tested, target GPU-tested, and Runpod end-to-end tested. Stages are separate: a local CPU smoke test cannot establish GPU support; build success cannot establish readiness or correctness.

For improve mode preserve a baseline source/image and the behavior that must remain compatible. Compare baseline and candidate using the same representative input, model revision, precision/quality target, hardware class, storage, and stated cache conditions. Do not trade away features, data, correctness, or output quality silently. If no runnable baseline is available, report verified candidate behavior and the baseline limitation without a fabricated improvement percentage.

Measure image transfer size where observable and unpacked storage separately. Record allocation/queue wait, image pull/unpack if exposed, workspace setup/copy, model load, first successful task, repeated warm execution, and peak CPU/RAM/VRAM as relevant. Some phases overlap or are not observable; mark them explicitly instead of deriving false precision from total request delay. Do not label first use as a verified cold host cache unless that condition was established.

Predeclare a practical repeat count within the test budget; use medians/ranges and retain raw observations. Do not report tail percentiles from tiny samples. Include correctness tolerances, regression checks, tradeoffs, and unchanged or worsened metrics. New projects can meet a tested quality bar without a before/after performance claim.

**10. Implementation sequence and completion gates**

1. **Contracts and routing:** implement concise skill/frontmatter and supporting references; register discovery/version updates; reconcile directly conflicting shared guidance. Gate: routing selects the authoring lane for explicit create/improve requests and keeps ordinary deployment/discovery in existing lanes.
2. **Project delivery and build routes:** define complete app-specific outputs and beginner handoff; implement verified local, managed GitHub, and external-builder decisions. Gate: a no-Docker/no-GPU user still receives a useful complete project, with truthful validation and one next-action path.
3. **Runtime examples:** add minimal Pod/QB/LB authoring variants and a PyTorch-heavy editable Pod scenario that exercises layer reuse and retained storage. Gate: required files map to real app needs; no forced universal services or unnecessary framework.
4. **Failure and verification scenarios:** implement the manual eval suite and application-specific fixture checks, then execute representative cases. Gate: failure outcomes preserve data, explain recovery, and never overstate evidence.
5. **Independent forward tests:** give agents realistic user requests, only the new skill plus raw input artifacts, and isolated output directories. Do not supply the expected fix. Separately give a fresh novice reviewer only the delivered project and README to follow the chosen quickstart, exposing missing prerequisites, unexplained placeholders, and wrong-shell commands. Inspect actual files/outcomes; repair demonstrated issues and repeat affected scenarios.
6. **Release preparation:** run repository checks, verify both installation/discovery paths in isolated environments, record live verification and outstanding limits, and use the normal Conventional Commit/release-please process. Gate: all required checks pass and there are no unresolved blocking defects in a supported path.

Work through these as focused commits or reviewable patches. Do not publish, merge, or create a release merely because plan implementation is complete.

**11. Acceptance scenarios and automated checks**

The behavioral suite must include at least these distinct cases, grouped into focused eval files rather than one file for every sentence:

- Public GitHub app → Pod project; local code → queue worker; existing HTTP app → load-balanced project; description-only request with meaningful ambiguity resolved.
- Explicit template authoring when an official prebuilt exists; ordinary deployment requests still route to their existing lanes; files-only request performs no external publishing/provisioning.
- Windows with no Docker/GPU; stopped Docker engine; ARM development host; no local GPU; paths with spaces; private/inaccessible source.
- Monorepo Dockerfile/context; LFS/submodule assets; private/gated dependency; registry push access distinct from Runpod pull access.
- UI-only/interactive repository proposed for queue serving; `.env`, credential files, local virtual environments and caches excluded from the build context without deleting originals; novice follows only the generated README and files.
- GitHub builder 30-minute step timeout versus total window; near/over size cap; private base; true device-dependent build; portable image requirement; release-triggered update; repository/account authorization.
- Code-only change preserves heavy framework layers; incompatible app dependencies cannot silently replace base framework; empty mount hides application files; retained storage and image update preserve user changes.
- Real Pod user workflow; real queue job output; real LB route and readiness; repeated requests and resource accumulation; invalid input followed by a successful valid request; relevant concurrency/retry/cancellation; durable output survives worker replacement; incompatible versions sharing storage cannot corrupt each other's state.
- Corrupt/partial model download, missing credential, full storage, startup failure, and interrupted build/deploy each yield a concrete bounded recovery.
- No runnable optimization baseline and no cloud credentials retain honest unverified statuses; a second unrelated app succeeds without relying on the demonstration's layout.

Existing `evals/*.eval.md` files are not executed by CI. Preserve that distinction. Executable checks should exercise runnable example containers and workload results, not assert exact prose or pretend regex matches prove Docker correctness. Add a narrowly scoped example-build/smoke CI job where useful, with no production credentials or automatic billable deployment; keep real GPU/platform acceptance in an explicitly executed test run with recorded evidence.

Run the repository's existing marketplace, version, branding, link, CLI-claim, migration, Python, and Nix checks as defined by `.github/workflows/validate.yml`. Separate pre-existing failures from new regressions. If adding reusable Python helpers, explicitly register their tests in Python 3.14 and 3.9 jobs and the Nix source/type/test lists, including matching development commands and applicable tool config. Skill scripts must support Python 3.9; placing them in a directory alone does not make CI execute them.

For live acceptance, use one real representative workload per target and a second independent app to demonstrate transfer. Keep resources small and disposable under an explicit time/cost budget, validate externally, retain evidence, and verify cleanup. Do not mark a target live-verified based solely on a local stub.

**12. Delivery and issue alignment**

DR-1501 becomes scope, target contracts, representative app selection, and baseline protocol. DR-1502 becomes the skill, documented projects, shared checklist, and measured optimization example. DR-1503 becomes a short user guide and walkthrough generated from the validated workflow. DR-1504 becomes independent clean-environment reproduction, review, and publication under the user's release authorization.

The completed implementation should contain a discoverable skill, coherent shared guidance, documented runnable examples, validated app-specific outputs, actionable novice paths, a reviewed failure/recovery matrix, and evidence for the supported targets. The guide and walkthrough teach the same maintained workflow.
