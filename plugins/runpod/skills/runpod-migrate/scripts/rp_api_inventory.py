#!/usr/bin/env python3
"""Inventory a codebase by Runpod API version.

Scans a directory tree and reports every place it talks to Runpod, tagged with
which API generation it uses: GraphQL, REST v1, REST v2, the serverless *job*
API (not part of this migration), or an SDK/CLI that wraps one of them.

Standard library only, no install step:

    python3 rp_api_inventory.py .                 # markdown report
    python3 rp_api_inventory.py . --json          # machine-readable
    python3 rp_api_inventory.py . --scope rest    # ignore GraphQL call sites
    python3 rp_api_inventory.py . --fail-on-legacy   # exit 1 if v1/GraphQL remain

Exit codes: 0 clean, 1 legacy usage found with --fail-on-legacy, 2 bad usage.

Two markers keep a hit out of the plan and out of --fail-on-legacy. They mean
opposite things and the report keeps them apart, so pick the accurate one:

    # rp-migrate: keep-v1    legacy left behind on purpose — a RUNPOD_API_V1
                             rollback path, or a GraphQL call with no v2 equivalent
    # rp-migrate: ignore     a false positive on code that is already correct

Each takes three scopes:

    # rp-migrate: <marker>              this line
    # rp-migrate: <marker> start / end  the region between them
    # rp-migrate: <marker> file         the whole file
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

# --------------------------------------------------------------------------
# Signal table
#
# Each signal is (generation, resource, regex, note) or
# (generation, resource, regex, note, unless_regex). `generation` drives the
# inventory buckets; `note` is what the report tells the migrating agent to do;
# `unless_regex` suppresses the hit when it also matches the line — needed
# because several names are legal in *both* versions (`/pods` is a v1 path and a
# v2 path; `idleTimeout` is top-level in v1 and nested under `workers` in v2).
# Ordering matters only for readability — every pattern is tested on every line.
# --------------------------------------------------------------------------

# A line that already carries a v2 marker is v2 code, whatever else it contains.
# Structural markers only — do NOT list guessed variable names here. Real code holds
# the base URL in a constant whose name we cannot predict; those are derived per file
# by BASE_ASSIGN below, which is honest where a hardcoded name list is wishful.
V2_CONTEXT = r"/v2/|api\.runpod\.io/v2"

# Resource names that are also ordinary code identifiers (`networkvolumes`,
# `containerregistryauth`) match inside package declarations, imports and module
# paths, which are not call sites. `github.com/acme/app/internal/networkvolumes`
# even carries the leading `/` that otherwise distinguishes a real path. Suppress
# the whole line in those positions rather than trying to spot the name itself:
# a language keyword at line start, or a VCS-style module path anywhere.
DECLARATION = (
    r"^\s*(package|import|from|use|require|mod|namespace|using)\b"
    r"|\b(github|gitlab|bitbucket|golang\.org|gopkg\.in)\.?[a-z]*/"
)

# `IDENT = "...api.runpod.io/v2..."` — captures whatever the file calls its base URL,
# so `f"{BASE}/pods"` eleven lines later is recognized as v2 rather than reported as a
# leftover v1 path. Without this, a correctly migrated file fails --fail-on-legacy.
BASE_ASSIGN_V2 = re.compile(r"""(\w+)\s*[:=]\s*[fr]?['"`][^'"`]*api\.runpod\.io/v2""")
BASE_ASSIGN_V1 = re.compile(r"""(\w+)\s*[:=]\s*[fr]?['"`][^'"`]*rest\.runpod\.io/v1""")

JOB_API = "job-api"  # api.runpod.ai/v2/<endpointId>/run — NOT the control plane

SIGNALS: list[tuple[str, str, str, str]] = [
    # ---- serverless job API: looks like "v2" but is a different API ---------
    (JOB_API, "job", r"api\.runpod\.ai/v2/", "Serverless job API — unaffected by the control-plane migration. Leave it alone."),
    (JOB_API, "job", r"\brunpod\.Endpoint\s*\(", "Python SDK job client (`runpod.Endpoint`) — job API, not the control plane. Leave it alone."),

    # ---- GraphQL -----------------------------------------------------------
    ("graphql", "endpoint", r"api\.runpod\.io/graphql", "GraphQL endpoint. → REST v2 https://api.runpod.io/v2"),
    ("graphql", "pod", r"\bpodFindAndDeployOnDemand\b", "→ POST /v2/pods"),
    ("graphql", "pod", r"\bpodRentInterruptable\b", "Spot/interruptible pods have no REST v2 equivalent. Keep on GraphQL or move to on-demand."),
    ("graphql", "pod", r"\bpodBidResume\b", "Spot/interruptible pods have no REST v2 equivalent. Keep on GraphQL or move to on-demand."),
    ("graphql", "pod", r"\bpodResume\b", "→ POST /v2/pods/{id}/action  {\"action\":\"start\"}"),
    ("graphql", "pod", r"\bpodStop\b", "→ POST /v2/pods/{id}/action  {\"action\":\"stop\"}"),
    ("graphql", "pod", r"\bpodTerminate\b", "→ DELETE /v2/pods/{id}"),
    ("graphql", "pod", r"\bpodEditJob\b", "→ PATCH /v2/pods/{id}"),
    ("graphql", "pod", r"\bpod\s*\(\s*input\s*:", "→ GET /v2/pods/{id}"),
    ("graphql", "serverless", r"\bsaveEndpoint\b", "→ POST /v2/serverless (create) or PATCH /v2/serverless/{id} (update)"),
    ("graphql", "serverless", r"\bdeleteEndpoint\b", "→ DELETE /v2/serverless/{id}"),
    ("graphql", "template", r"\bsaveTemplate\b", "→ POST /v2/templates or PATCH /v2/templates/{id}"),
    ("graphql", "template", r"\bdeleteTemplate\b", "→ DELETE /v2/templates/{id} — note v2 deletes by ID, GraphQL deleted by NAME."),
    ("graphql", "catalog", r"\bgpuTypes\b", "→ GET /v2/catalog/gpus?include=AVAILABILITY&product=POD (product is REQUIRED with include; 400 without it. Use product=SERVERLESS when picking a GPU for an endpoint.)"),
    ("graphql", "catalog", r"\bcpuTypes\b", "→ GET /v2/catalog/cpus?include=AVAILABILITY&product=POD (product is REQUIRED with include; 400 without it)"),
    ("graphql", "catalog", r"\blowestPrice\s*\(", "→ GET /v2/catalog/gpus?include=AVAILABILITY&product=POD (price + availability in one call; product is REQUIRED with include, 400 without it)"),
    ("graphql", "volume", r"\b(createNetworkVolume|updateNetworkVolume|deleteNetworkVolume)\b", "→ /v2/network-volumes"),
    ("graphql", "registry", r"\bsaveRegistryAuth\b", "→ POST /v2/registries"),
    ("graphql", "user", r"\bmyself\s*\{[^}]*\b(pods|endpoints)\b", "`myself { pods }` → GET /v2/pods; `myself { endpoints }` → GET /v2/serverless"),
    ("graphql", "user", r"\bmyself\b", "Account fields (email, clientBalance, currentSpendPerHr) have no REST v2 equivalent — keep this GraphQL call. If you only use `myself` to reach `pods`/`endpoints`, use GET /v2/pods and GET /v2/serverless instead."),
    ("graphql", "secret", r"\bsecret(Create|Delete)\b", "No REST v2 equivalent. Keep this GraphQL call."),
    ("graphql", "cluster", r"\b(createCluster|deleteCluster)\b", "No REST v2 write equivalent (v2 exposes cluster billing only). Keep this GraphQL call."),

    # ---- REST v1 -----------------------------------------------------------
    ("v1", "base", r"rest\.runpod\.io/v1", "REST v1 base URL. → https://api.runpod.io/v2"),
    # Require a real path separator: `["pods"]` is v2 envelope-unwrapping, the
    # opposite of a v1 call site.
    ("v1", "pod", r"/pods\b(?!/[a-z]*\{)", "v1 /pods → /v2/pods (response is now {\"pods\": [...]}, not a bare array)", V2_CONTEXT),
    ("v1", "serverless", r"/endpoints\b", "v1 /endpoints → /v2/serverless", V2_CONTEXT),
    # Both of these need a leading `/`, for the same reason `/pods` does. `networkvolumes`
    # and `containerregistryauth` are ordinary identifiers: Go packages, Python modules,
    # import paths, directory names. Matching the bare token flagged every one of them,
    # which made `--fail-on-legacy` fail on codebases that were already fully v2 — the one
    # thing that flag must never do. V2_CONTEXT then suppresses `/v2/...` lines, so the
    # correct hyphenated path and `/v2/billing/networkvolumes` do not report as v1.
    ("v1", "volume", r"/networkvolumes\b", "v1 /networkvolumes → /v2/network-volumes (hyphenated)", V2_CONTEXT + r"|network-volumes|" + DECLARATION),
    ("v1", "registry", r"/containerregistryauth\b", "v1 /containerregistryauth → /v2/registries", V2_CONTEXT + r"|" + DECLARATION),
    ("v1", "pod", r"/pods/[^'\"`\s]*/(start|stop|restart|reset)\b", "→ POST /v2/pods/{id}/action with {\"action\": \"start|stop|restart\"}. v1 `reset` has no direct v2 action.", V2_CONTEXT),
    ("v1", "any", r"/(pods|endpoints|templates|networkvolumes)/[^'\"`\s]*/update\b", "v1 POST .../update alias is gone. Use PATCH on the resource.", V2_CONTEXT),
    ("v1", "billing", r"/billing/(pods|endpoints|networkvolumes)\b", "→ /v2/billing/{pods,serverless,endpoints,network-volumes} — note v1 /billing/endpoints (serverless) is v2 /billing/serverless, and v2 /billing/network-volumes is hyphenated.", V2_CONTEXT),

    # ---- v1/GraphQL request-body field names ------------------------------
    ("v1-field", "pod", r"\bimageName\b", "→ `image`"),
    ("v1-field", "pod", r"\bcontainerDiskInGb\b", "→ `disk`"),
    ("v1-field", "pod", r"\bvolumeInGb\b", "→ `mounts.persistent.size`"),
    ("v1-field", "pod", r"\bvolumeMountPath\b", "→ `mounts.persistent.path` (or `mounts.network[0].path`)"),
    ("v1-field", "pod", r"\bnetworkVolumeId\b", "→ `mounts.network[0].volumeId` + an explicit `path` (v2 has no default mount path)"),
    ("v1-field", "pod", r"\bgpuTypeIds?\b", "→ `gpu.id` (pods, single type) or `gpu.pools` (serverless, pool IDs). v2 takes no fallback list — see breaking-changes.md."),
    ("v1-field", "pod", r"\bgpuCount\b", "→ `gpu.count`"),
    ("v1-field", "pod", r"\bcloudType\b", "→ `cloud`"),
    ("v1-field", "pod", r"\bcontainerRegistryAuthId\b", "→ `registry`"),
    ("v1-field", "pod", r"\bdocker(StartCmd|Args|Entrypoint)\b", "→ `args` (a single string). v2 has no separate entrypoint override."),
    ("v1-field", "pod", r"\bdesiredStatus\b", "→ `status` (enum gained PROVISIONING, STARTING, ERROR)"),
    ("v1-field", "pod", r"\bcostPerHr\b", "→ `cost`"),
    ("v1-field", "pod", r"\b(cpuFlavorIds|vcpuCount)\b", "→ `cpu.id` / `cpu.vcpuCount`"),
    ("v1-field", "pod", r"\b(gpuTypePriority|dataCenterPriority|cpuFlavorPriority)\b", "Removed in v2. Order/fallback is now client-side — see breaking-changes.md."),
    ("v1-field", "pod", r"\b(minRAMPerGPU|minVCPUPerGPU|minDownloadMbps|minUploadMbps|minDiskBandwidthMBps|supportPublicIp|volumeEncrypted|interruptible)\b", "Removed in v2 — no equivalent. Drop it or stay on v1/GraphQL for this call."),
    ("v1-field", "pod", r"\bcountryCodes\b", "No create-time equivalent, but there IS a migration: filter /v2/catalog/gpus?include=AVAILABILITY&product=POD&countryCodes=.. to get the matching data centers, then pass their IDs as dataCenterIds on create. dataCenterIds is enforced (verified 2026-08-18) despite the spec calling it `preferred`, so it is a sound basis for data residency. Over-narrow it and the create fails 400 `no instances available`, with no mention of data centers. Working code: breaking-changes.md -> Replacing countryCodes."),
    ("v1-field", "pod", r"\b(allowedCudaVersions|minCudaVersion)\b", "Moved, not removed → `gpu.allowedCudaVersions` / `gpu.minCudaVersion` on pod and endpoint create. Nested under `gpu` so they are unrepresentable on a CPU workload; left at the top level they 422. A non-empty allowedCudaVersions and minCudaVersion are mutually exclusive (400).", r"\bgpu\s*[.\[]|[\"']gpu[\"']\s*:"),
    ("v1-field", "serverless", r"\bworkers(Min|Max)\b", "→ `workers.min` / `workers.max`"),
    ("v1-field", "serverless", r"\bidleTimeout\b", "→ `workers.idleTimeout`", r"\bworkers\b"),
    ("v1-field", "serverless", r"\bscaler(Type|Value)\b", "→ `scaling.type` + `scaling.queueDelay` | `scaling.requestCount`"),
    ("v1-field", "serverless", r"\bexecutionTimeoutMs\b", "→ `timeout` (still milliseconds)"),
    ("v1-field", "serverless", r"\bflash[Bb]oot(Type)?\b", "→ `flashboot`, now the enum OFF | FLASHBOOT | PRIORITY_FLASHBOOT (was a boolean in v1)", r"[\"'](OFF|FLASHBOOT|PRIORITY_FLASHBOOT)[\"']"),
    ("v1-field", "serverless", r"\btemplateId\b", "Still accepted on v2 create and update, but resolved once at request time with no link retained — later template edits no longer reach the resource. If this code edits templates to roll out changes, that rollout silently stops working; inline the container fields instead. See breaking-changes.md Class 2."),
    ("v1-field", "serverless", r"\blocations\b", "GraphQL `locations` string → `dataCenterIds` array"),
    ("v1-field", "serverless", r"\bgpuIds\b", "GraphQL `gpuIds` → `gpu.pools` (array of pool IDs)"),
    ("v1-field", "template", r"\bis(Serverless|Public)\b", "→ `serverless` / `public`"),
    ("v1-field", "volume", r"\bdataCenterId\b", "On network volumes: → `dataCenter`. On pods it stays `dataCenterId`."),
    ("v1-field", "pod", r"\b(machineId|podHostId)\b", "Removed in v2. Host identity is no longer exposed; `dataCenterId` is the placement field that remains."),
    ("v1-field", "pod", r"\bmachine\s*[({]", "The v1/GraphQL `machine` object is gone in v2. Only `dataCenterId` survives."),
    ("v1-field", "pod", r"\buptimeInSeconds\b", "→ `runtime.uptime` (still seconds)"),
    ("v1-field", "pod", r"\bgpuUtilPercent\b", "→ `runtime.gpus[].util`"),
    ("v1-field", "pod", r"\bmemoryUtilPercent\b", "→ `runtime.gpus[].memoryUtil`"),
    ("v1-field", "pod", r"\b(cpuPercent|memoryPercent)\b", "→ `runtime.cpu.util` / `runtime.memory.util`"),
    ("v1-field", "pod", r"\b(publicIp|portMappings)\b", "→ `runtime.ports[]` (`{private, public, type, ip}`), populated only while RUNNING."),
    ("v1-field", "pod", r"\b(minVcpuCount|minMemoryInGb)\b", "Removed in v2 — no equivalent. GPU pods size RAM/vCPU from the GPU type."),
    ("v1-field", "pod", r"cloudType\s*:\s*ALL\b", "v2 `cloud` has no ALL. Pick SECURE or COMMUNITY, or try one then the other."),
    ("v1-field", "catalog", r"\bstockStatus\b", "→ `availability` (NONE | LOW | MEDIUM | HIGH), plus per-datacenter `dataCenters[].availability`."),
    ("v1-field", "catalog", r"\b(uninterruptablePrice|memoryInGb|displayName|secureCloud|communityCloud)\b", "Catalog field renames: → `price.secure` / `memory` / `name` / `secure` / `community`."),
    ("v1-field", "any", r"\benv\s*:\s*\[\s*\{", "GraphQL `env: [{key, value}]` → v2 `env` is a plain string map: `{\"KEY\": \"value\"}`."),

    # ---- already on v2 -----------------------------------------------------
    ("v2", "base", r"api\.runpod\.io/v2\b", "Already on REST v2."),
    ("v2", "volume", r"/v2/network-volumes\b", "Already on REST v2."),
    ("v2", "catalog", r"/v2/catalog/", "Already on REST v2."),
    ("v2", "pod", r"/v2/pods\b", "Already on REST v2."),
    ("v2", "serverless", r"/v2/serverless\b", "Already on REST v2."),

    # ---- wrappers ----------------------------------------------------------
    ("sdk", "python", r"^\s*import\s+runpod\b|^\s*from\s+runpod\b", "Python `runpod` SDK — wraps GraphQL/v1 internally. Check the SDK version before assuming a generation."),
    ("sdk", "python", r"\brunpod\.(create_pod|stop_pod|resume_pod|terminate_pod|get_pods|get_pod|get_gpus?|create_template|create_endpoint|update_endpoint_template)\b", "Python SDK control-plane call — wraps GraphQL. Replace with a v2 REST call to migrate."),
    ("sdk", "js", r"require\(['\"]runpod-sdk['\"]\)|from\s+['\"]runpod-sdk['\"]", "JS `runpod-sdk` — job API oriented; check what it is used for."),
    ("cli", "runpodctl", r"\brunpodctl\s+\w", "runpodctl already speaks the current API — nothing to migrate, but check pinned versions."),
    ("mcp", "mcp", r"@runpod/mcp-server|mcp\.getrunpod\.io", "Runpod MCP server — follows its own REST version (see serverInfo.version). Nothing to migrate."),

    # ---- indirect: resource names as bare strings --------------------------
    # A helper like `_url("pods", pod_id, "stop")` builds a v1 path with no literal
    # path anywhere. Advisory only — `resp.json()["pods"]` looks identical and is v2
    # envelope-unwrapping — so these are reported for review, never auto-planned.
    ("indirect", "any", r"[\"'](pods|endpoints|templates|networkvolumes|containerregistryauth)[\"']",
     "Resource name used as a bare string. If a helper joins it onto a base URL, it is a hidden call site — check how the path is built.", V2_CONTEXT),
]

COMPILED = [
    (s[0], s[1], re.compile(s[2]), s[3],
     re.compile(s[4]) if len(s) > 4 else None,
     len(s) > 4 and s[4] == V2_CONTEXT)   # does this signal defer to v2 context?
    for s in SIGNALS
]


def comment_index(line: str) -> int:
    """Index where a trailing comment starts, or -1. Quote-aware, so a `#` or `//`
    inside a string literal (a URL fragment, say) is not mistaken for a comment.

    Needed because the skill's own house style annotates migrations inline —
    `"image": image,  # was imageName` — and a whole-line-only comment test scores
    that as a live v1 field, which makes --fail-on-legacy fail on correct code."""
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c == "#":
            return i
        elif c == "/" and line[i + 1:i + 2] == "/" and line[i - 1:i] != ":":
            return i   # `//` comment, but never the `//` in `https://`
        elif c == "-" and line[i + 1:i + 2] == "-" and line[:i].strip() == "":
            return i
        i += 1
    return -1

# Lines that are prose about the API rather than calls to it — comments and docs.
# Still reported (commented-out v1 code is worth seeing) but kept out of the plan.
COMMENT_START = re.compile(r"^\s*(#|//|\*|--|<!--)")
TRIPLE_QUOTE = re.compile(r'"""' + "|'''")
PROSE_SUFFIXES = {".md", ".mdx", ".rst", ".txt", ".adoc"}

# Cheap whole-file gate so we only line-scan files that mention Runpod at all.
#
# DERIVED from SIGNALS on purpose — a hand-written gate drifts out of sync with the
# signal table and then silently skips whole files. The case that motivated this: a
# module that reads `p["costPerHr"]` off a wrapper's return value contains no Runpod
# URL, no operation name, and no import — nothing but a renamed response field. That
# is exactly the file a v2 migration breaks quietly, and a stale gate never opened it.
PREFILTER = re.compile("|".join(f"(?:{s[2]})" for s in SIGNALS))


def md_cell(s: str) -> str:
    """Escape a value for a GitHub-flavored markdown table cell."""
    return s.replace("|", "\\|").replace("\n", " ")


# Suppression markers. Both keep a hit out of the plan and out of --fail-on-legacy,
# but they say opposite things and the report must not conflate them:
#
#   keep-v1  legacy code left behind on purpose — a `RUNPOD_API_V1=1` rollback path,
#            or a GraphQL-only call (myself/secrets/spot) with no v2 equivalent.
#   ignore   not legacy at all — a false positive on code that is already correct.
#
# Reporting an `ignore` as `keep-v1` would claim the migration deliberately left v1
# behind when it left none, which is the exact lie the skill warns against.
#
# Each accepts three scopes:
#   rp-migrate: <marker> file           anywhere in a file  -> whole file
#   rp-migrate: <marker> start / end    bracket a region
#   rp-migrate: <marker>                the matching line
MARKERS = ("keep-v1", "ignore")
MARK_FILE = {m: re.compile(rf"rp-migrate:\s*{m}\s+file") for m in MARKERS}
MARK_START = {m: re.compile(rf"rp-migrate:\s*{m}\s+start") for m in MARKERS}
MARK_END = {m: re.compile(rf"rp-migrate:\s*{m}\s+end") for m in MARKERS}
MARK_LINE = {m: re.compile(rf"rp-migrate:\s*{m}\b(?!\s+(file|start|end))") for m in MARKERS}


def intentional_lines(text: str) -> tuple[str | None, dict[int, str]]:
    """
    Return (whole_file_marker, {line number: marker}).

    `keep-v1` wins over `ignore` when both cover the same line, because claiming
    legacy was kept on purpose is the safer error: it leaves the hit visible as
    legacy rather than dismissing it as a false positive.
    """
    for marker in MARKERS:
        if MARK_FILE[marker].search(text):
            return marker, {}

    marked: dict[int, str] = {}
    inside: set[str] = set()

    for lineno, line in enumerate(text.splitlines(), 1):
        for marker in MARKERS:
            if MARK_START[marker].search(line):
                inside.add(marker)

        for marker in MARKERS:
            if marker in inside or MARK_LINE[marker].search(line):
                # MARKERS is ordered keep-v1 first, so it wins a tie.
                marked.setdefault(lineno, marker)

        for marker in MARKERS:
            if MARK_END[marker].search(line):
                inside.discard(marker)

    return None, marked

# Directories whose contents are not the user's source. `.claude` matters more than it
# looks: agent worktrees under `.claude/worktrees/` are full copies of the repo, so
# scanning one repo with six worktrees reports every finding six or seven times. This
# skill ships as a Claude Code plugin, which makes its users exactly the people who have
# that directory. Measured on one real repo: 10,763 hits reported, 1,821 real.
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build",
    ".next", ".nuxt", "target", "vendor", ".terraform", ".mypy_cache", ".pytest_cache",
    ".tox", "site-packages", ".gradle", "coverage", ".idea", ".vscode",
    ".claude", ".worktrees", ".cache", ".ruff_cache", ".pnpm-store", "bower_components",
}
SKIP_SUFFIXES = {
    ".lock", ".min.js", ".map", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".pdf", ".zip", ".gz", ".tar", ".whl", ".so", ".dylib", ".bin", ".pt", ".pth",
    ".safetensors", ".onnx", ".parquet", ".pyc",
}
# Text formats worth scanning. Anything else is sniffed for NUL bytes instead.
MAX_BYTES = 2_000_000

LEGACY = {"graphql", "v1", "v1-field"}


def iter_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".git"))
        for fn in sorted(filenames):
            if any(fn.endswith(s) for s in SKIP_SUFFIXES):
                continue
            path = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(path) > MAX_BYTES:
                    continue
            except OSError:
                continue
            yield path


def scan_file(path: str, root: str):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return []
    if b"\0" in raw[:4096]:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return []
    if not PREFILTER.search(text):
        return []

    rel = os.path.relpath(path, root)
    whole_file_marker, marked = intentional_lines(text)
    ext = os.path.splitext(path)[1].lower()
    is_doc = ext in PROSE_SUFFIXES
    is_py = ext in {".py", ".pyi"}
    in_docstring = False

    # Whatever this file calls its v2 base URL counts as v2 context anywhere in it.
    # A name bound to a v1 base URL is deliberately NOT added — those lines are v1.
    v2_names = set(BASE_ASSIGN_V2.findall(text)) - set(BASE_ASSIGN_V1.findall(text))
    file_v2_ctx = (
        re.compile(r"\b(" + "|".join(re.escape(n) for n in sorted(v2_names)) + r")\b")
        if v2_names else None
    )
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if len(line) > 2000:
            line = line[:2000]
        docstring_line = in_docstring
        if is_py:
            quotes = len(TRIPLE_QUOTE.findall(line))
            if quotes:
                docstring_line = True          # the delimiter line itself is prose
                if quotes % 2:                 # odd count flips the state
                    in_docstring = not in_docstring
        cmt = comment_index(line)
        whole_line_comment = is_doc or docstring_line or bool(COMMENT_START.match(line))
        for gen, res, rx, note, unless, defers_to_v2 in COMPILED:
            m = rx.search(line)
            if not m:
                continue
            if unless and unless.search(line):
                continue
            if defers_to_v2 and file_v2_ctx and file_v2_ctx.search(line):
                continue   # e.g. f"{BASE}/pods" where BASE is this file's v2 base URL
            # A hit after a `#` / `//` is an annotation about the migration, not a
            # call site — report it, but keep it out of the plan.
            prose = whole_line_comment or (cmt != -1 and m.start() > cmt)
            hits.append({
                "prose": prose,
                "file": rel,
                "line": lineno,
                "generation": gen,
                "resource": res,
                "match": m.group(0)[:80],
                "note": note,
                "text": line.strip()[:200],
                # Which marker, not just whether one was present: the two mean
                # opposite things and the report keeps them apart.
                "marker": whole_file_marker or marked.get(lineno),
            })
    return hits


def dedupe(hits):
    """Collapse identical (file, line, generation) rows, keeping every note."""
    grouped = {}
    for h in hits:
        key = (h["file"], h["line"], h["generation"])
        if key in grouped:
            if h["note"] not in grouped[key]["notes"]:
                grouped[key]["notes"].append(h["note"])
            grouped[key]["matches"].append(h["match"])
        else:
            g = dict(h)
            g["notes"] = [h.pop("note")]
            g["matches"] = [h["match"]]
            g.pop("note", None)
            grouped[key] = g
    return sorted(grouped.values(), key=lambda h: (h["file"], h["line"]))


def render_markdown(hits, root, scope):
    by_gen = defaultdict(list)
    for h in hits:
        by_gen[h["generation"]].append(h)

    files_by_gen = {g: sorted({h["file"] for h in v}) for g, v in by_gen.items()}
    out = []
    out.append(f"# Runpod API inventory — `{root}`\n")

    order = ["graphql", "v1", "v1-field", "indirect", "v2", JOB_API, "sdk", "cli", "mcp"]
    label = {
        "graphql": "GraphQL (legacy)",
        "v1": "REST v1 (legacy)",
        "v1-field": "v1/GraphQL field names",
        "indirect": "Possible indirect call sites (review by hand)",
        "v2": "REST v2 (current)",
        JOB_API: "Serverless job API (out of scope)",
        "sdk": "SDK wrapper",
        "cli": "runpodctl",
        "mcp": "Runpod MCP",
    }

    out.append("| Generation | Call sites | Files |")
    out.append("| --- | --- | --- |")
    for gen in order:
        if gen in by_gen:
            out.append(f"| {label[gen]} | {len(by_gen[gen])} | {len(files_by_gen[gen])} |")
    if not hits:
        out.append("| _no Runpod API usage found_ | 0 | 0 |")
    out.append("")

    legacy_files = sorted({h["file"] for h in hits
                           if h["generation"] in LEGACY and not h["marker"] and not h["prose"]})
    kept = [h for h in hits if h["generation"] in LEGACY and h["marker"] == "keep-v1"]
    ignored = [h for h in hits if h["generation"] in LEGACY and h["marker"] == "ignore"]
    prose_hits = [h for h in hits if h["generation"] in LEGACY and h["prose"] and not h["marker"]]
    v2_files = sorted(files_by_gen.get("v2", []))
    mixed = sorted(set(legacy_files) & set(v2_files))

    out.append("## Verdict\n")
    if not legacy_files:
        out.append("- **Nothing to migrate.** No REST v1 or GraphQL control-plane calls found.")
    else:
        out.append(f"- **{len(legacy_files)} file(s) need migration.**")
    if prose_hits:
        out.append(
            f"- **{len(prose_hits)} legacy mention(s) are in comments or docs**, not live call "
            "sites. Reported below, excluded from the plan — but check for commented-out v1 code."
        )
    if kept:
        out.append(
            f"- **{len(kept)} legacy call site(s) are kept on purpose** "
            f"(`rp-migrate: keep-v1`) in {len({h['file'] for h in kept})} file(s) — "
            "rollback paths or GraphQL-only calls. Excluded from the plan and from `--fail-on-legacy`."
        )
    if ignored:
        out.append(
            f"- **{len(ignored)} hit(s) are marked false positives** "
            f"(`rp-migrate: ignore`) in {len({h['file'] for h in ignored})} file(s) — "
            "code that is already correct, not legacy being retained. Excluded from the plan "
            "and from `--fail-on-legacy`."
        )
    if v2_files:
        out.append(f"- **{len(v2_files)} file(s) are already on REST v2** — leave them alone.")
    if mixed:
        out.append(f"- **{len(mixed)} file(s) mix generations**: {', '.join(f'`{m}`' for m in mixed)}")
    if JOB_API in by_gen:
        out.append(
            f"- **{len(files_by_gen[JOB_API])} file(s) call the serverless *job* API** "
            "(`api.runpod.ai/v2/<endpointId>/run…`). That is a different API from the control "
            "plane and is **not** part of this migration — do not rewrite it."
        )
    if scope == "rest":
        out.append("- Scope is `rest`: GraphQL call sites are reported but excluded from the migration plan.")
    out.append("")

    for gen in order:
        rows = by_gen.get(gen)
        if not rows:
            continue
        out.append(f"## {label[gen]}\n")
        out.append("| Location | Match | Action |")
        out.append("| --- | --- | --- |")
        for h in rows:
            notes = md_cell("<br>".join(h["notes"]))
            if h["marker"] == "keep-v1":
                keep = " _(kept on purpose)_"
            elif h["marker"] == "ignore":
                keep = " _(false positive)_"
            else:
                keep = " _(comment/doc)_" if h["prose"] else ""
            out.append(f"| `{h['file']}:{h['line']}`{keep} | `{md_cell(h['matches'][0])}` | {notes} |")
        out.append("")

    if legacy_files:
        out.append("## Migration order\n")
        counts = Counter(h["file"] for h in hits
                         if h["generation"] in LEGACY and not h["marker"] and not h["prose"])
        out.append("Fewest call sites first — each file is one reviewable commit.\n")
        for f, n in sorted(counts.items(), key=lambda kv: (kv[1], kv[0])):
            out.append(f"1. `{f}` — {n} call site(s)")
        out.append("")

    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=".", help="directory (or file) to scan")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    ap.add_argument("--scope", choices=["all", "rest", "graphql"], default="all",
                    help="all (default) | rest: only migrate REST v1 | graphql: only migrate GraphQL")
    ap.add_argument("--fail-on-legacy", action="store_true", help="exit 1 when v1/GraphQL usage remains")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.path)
    if not os.path.exists(root):
        print(f"error: no such path: {args.path}", file=sys.stderr)
        return 2

    hits = []
    if os.path.isfile(root):
        base = os.path.dirname(root)
        hits = scan_file(root, base)
        root = base
    else:
        for path in iter_files(root):
            hits.extend(scan_file(path, root))

    hits = dedupe(hits)

    scoped = {"rest": {"v1", "v1-field"}, "graphql": {"graphql"}}.get(args.scope, LEGACY)
    in_plan = [h for h in hits if h["generation"] in scoped and not h["marker"] and not h["prose"]]

    if args.json:
        print(json.dumps({
            "root": root,
            "scope": args.scope,
            "counts": dict(Counter(h["generation"] for h in hits)),
            "files_needing_migration": sorted({h["file"] for h in in_plan}),
            "kept_on_purpose": sorted({h["file"] for h in hits
                                       if h["marker"] == "keep-v1" and h["generation"] in LEGACY}),
            "marked_false_positive": sorted({h["file"] for h in hits
                                             if h["marker"] == "ignore" and h["generation"] in LEGACY}),
            "prose_only": sorted({h["file"] for h in hits if h["prose"] and h["generation"] in LEGACY}),
            "already_v2": sorted({h["file"] for h in hits if h["generation"] == "v2"}),
            "job_api_leave_alone": sorted({h["file"] for h in hits if h["generation"] == JOB_API}),
            "hits": hits,
        }, indent=2))
    else:
        print(render_markdown(hits, root, args.scope))

    if args.fail_on_legacy and in_plan:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
