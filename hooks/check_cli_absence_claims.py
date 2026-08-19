#!/usr/bin/env python3
"""Check the skills' "runpodctl cannot do X" claims against the real CLI surface.

Every claim that a runpodctl command does NOT exist is an assertion of ABSENCE, and
absence is the one kind of claim that rots silently: `--help` deference does not
protect it (there is no flag to look up), a reader has no reason to probe, and the
claim reads as authoritative right up until the release that adds the command.

This has now happened twice in the same skill. v2.9.0 added `serverless health`,
falsifying "diagnosis relies on /health worker counts"; v2.10.0 added `pod logs` and
`serverless logs`, falsifying eleven assertions that worker logs were MCP-only —
including an eval that graded an agent CORRECT for saying so. An eval that asserts a
false negative is worse than a stale flag list: it trains the behavior in.

So: find the absence claims, extract the command each one names, and fail if that
command exists in the vendored surface snapshot.

    python3 hooks/check_cli_absence_claims.py         # vendored snapshot (CI gate)
    python3 hooks/check_cli_absence_claims.py --live  # latest release (drift job)

Exit 1 if any absence claim names a command that exists.
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/runpod/skills"
SNAPSHOT = ROOT / "testdata/runpodctl/command-surface.json"

# Sentences that assert a runpodctl command is missing. Deliberately narrow: it must
# name runpodctl (or "the CLI"/"the CLI lane") AND use absence wording. Broad matching
# here produces noise that gets the whole check disabled.
ABSENCE = re.compile(
    r"(?:runpodctl|the CLI(?: lane)?|CLI lane)[^.\n]{0,120}?"
    r"\b(?:has no|have no|has never had|lacks|cannot|can't|is unable to|no first-class|"
    r"there is no|there's no|no (?:such )?(?:\w+[- ])?command)\b"
    r"[^.\n]{0,160}"
    r"|\b(?:has no|there is no|there's no|no first-class)\b[^.\n]{0,80}?"
    r"\bcommand\b[^.\n]{0,60}?\bin (?:runpodctl|the CLI)\b",
    re.IGNORECASE,
)

# "only MCP can X" is the same claim from the other side.
MCP_ONLY = re.compile(
    r"\b(?:only|sole)\b[^.\n]{0,60}\bMCP\b[^.\n]{0,120}"
    r"|\bMCP[- ]only\b[^.\n]{0,120}"
    r"|\bthe (?:only|one) (?:lane|tool lane|route)\b[^.\n]{0,120}",
    re.IGNORECASE,
)

# "you must use MCP for X" / "X requires the MCP server" is an absence claim with no
# absence wording in it — the form that slipped past the first two patterns.
MUST_USE_MCP = re.compile(
    r"\b(?:must use|have to use|need(?:s)? (?:to use )?|requires?"
    r"|only\b[^.\n]{0,24}?\b(?:via|through|with|from|in))\b"
    r"[^.\n]{0,60}\b(?:MCP|Console)\b[^.\n]{0,80}"
    r"|\b(?:MCP|Console)\b[^.\n]{0,40}\bis (?:the )?(?:only|required)\b[^.\n]{0,80}",
    re.IGNORECASE,
)

# A claim only falsifies if it names a real command path. `<verb> <noun>` pairs like
# "worker-log command" are not command paths; these are.
RESOURCES = r"pod|serverless|sls|template|tpl|hub|model|network-volume|nv|registry|reg|user|gpu|datacenter|dc|billing|doctor|ssh|send|receive|update|version"
# Case-insensitive: a claim that opens a sentence capitalizes the resource
# ("Serverless logs are only available through MCP"), and a case-sensitive match
# let exactly that phrasing through.
CMD_IN_TEXT = re.compile(rf"\b({RESOURCES})\s+([a-z][a-z-]+)\b", re.IGNORECASE)

# Absence claims that are true and must stay allowed. Each needs a reason: this list is
# how a legitimate "MCP has no tool for this" survives the check, not an escape hatch for
# a claim nobody rechecked.
ALLOW = {
    # (substring that must appear in the matched text, why it is allowed)
    "MCP has no tool for these": "about MCP's surface, not runpodctl's",
    "MCP rejects that combination": "about MCP's surface, not runpodctl's",
    "no worker-log path on REST v1": "about REST v1, not runpodctl",
    "v1 has no worker-log path at all": "about REST v1, not runpodctl",
    "MCP narrows to one GPU type": "about MCP's surface",
    "no CPU concept": "about MCP's surface",
    "cannot change it": "about the API, not a missing command",
    "cannot express a SKU": "about MCP's surface",
    "can't change the tier": "about the API",
    "no type field": "about REST v1 / the API shape",
    "OAuth": "MCP-only auth mode, genuinely MCP-only",
    "CLIs stay unauthed": "MCP-only auth mode",
    "stream-job": "incremental job output is genuinely MCP-only",
    "no `--gpu-id` flag": "a missing flag, which --help does cover",
    "no table format": "a missing flag value, covered by output-and-errors.md",
}


def load_surface(live: bool) -> tuple[str, set[str]]:
    if not live:
        snap = json.loads(SNAPSHOT.read_text())
        return snap["version"], set(snap["commands"]) | set(snap.get("hidden_commands", []))
    tag = json.load(urllib.request.urlopen(
        "https://api.github.com/repos/runpod/runpodctl/releases/latest"))["tag_name"]
    import platform
    arch = "arm64" if platform.machine() in ("arm64", "aarch64") else "amd64"
    osname = "darwin" if sys.platform == "darwin" else "linux"
    url = f"https://github.com/runpod/runpodctl/releases/download/{tag}/runpodctl-{osname}-{arch}"
    with tempfile.NamedTemporaryFile(delete=False, suffix="-runpodctl") as fh:
        fh.write(urllib.request.urlopen(url).read())
        binp = fh.name
    Path(binp).chmod(0o755)
    cmds: set[str] = set()

    def walk(path: str) -> None:
        out = subprocess.run([binp] + path.split() + ["--help"],
                             capture_output=True, text=True).stdout
        seen = False
        for ln in out.splitlines():
            if ln.startswith("Available Commands:"):
                seen = True
                continue
            if seen and ln.startswith(("Flags:", "Global Flags:")):
                break
            if seen:
                m = re.match(r"\s+(\S+)\s", ln)
                if m and m.group(1) not in ("help", "completion"):
                    child = f"{path} {m.group(1)}".strip()
                    cmds.add(child)
                    walk(child)

    walk("")
    return tag, cmds


# A claim that a command lacks a FLAG or a field is not an absence-of-command claim.
# `--help` covers those, which is the whole reason this check only guards commands.
FLAG_CLAIM = re.compile(
    r"--[a-z][a-z0-9-]*"                      # a literal flag
    r"|\b(?:flag|field|param(?:eter)?|option|key|support)s?\b"
    r"|`[a-z]+[A-Z]\w*`",                     # a backticked camelCase api field, e.g. `templateId`
    re.IGNORECASE)
# "no longer MCP-only", "is not the only lane" — the claim is being retired, not made.
NEGATED = re.compile(r"\b(?:no longer|not (?:an? )?(?:the )?only|used to be|"
                     r"is no longer|stopped being|until v?\d|before v?\d|as of v?\d)\b",
                     re.IGNORECASE)


def allowed(text: str, line: str = "") -> str | None:
    # negation often sits just outside the matched span ("no longer an MCP-only capability"),
    # so judge it on the whole line.
    if NEGATED.search(line or text):
        return "negated / historical — the claim is being retired, not asserted"
    if FLAG_CLAIM.search(text):
        return "about a missing flag or field, which --help covers"
    for needle, why in ALLOW.items():
        if needle.lower() in text.lower():
            return why
    return None


# Phrasings that MUST fail, and legitimate ones that MUST NOT. A pattern tweak that
# quietly stops catching a form is the failure mode this check cannot afford, and every
# MUST_CATCH line below is a phrasing that actually evaded an earlier version of these
# regexes. Run with --self-test (CI does).
MUST_CATCH = [
    "runpodctl has no serverless logs command.",
    "There is no pod logs command in runpodctl.",
    "The CLI lane cannot read serverless logs.",
    "Only MCP can do serverless logs.",
    "Worker logs are MCP-only; runpodctl serverless logs does not exist.",
    "runpodctl is unable to do serverless logs.",
    "runpodctl lacks a serverless logs subcommand.",
    "For pod logs you must use the MCP server.",
    "Reading serverless logs requires the MCP server.",
    "Serverless logs are only available through MCP.",
    "Pod logs require the Console.",
]
MUST_ALLOW = [
    "serverless update has no --gpu-id flag.",
    "MCP create-endpoint lacks templateId support for pod create.",
    "serverless logs needs runpodctl >= v2.10.0.",
    "Logs are no longer MCP-only: runpodctl serverless logs exists.",
    "MCP has no tool for send or receive.",
]


def self_test(commands: set[str]) -> int:
    bad = []
    for claim in MUST_CATCH:
        if not scan_line(claim, commands):
            bad.append(("should have been caught", claim))
    for claim in MUST_ALLOW:
        if scan_line(claim, commands):
            bad.append(("should have been exempt", claim))
    for why, claim in bad:
        print(f"  self-test: {why}: {claim}")
    if bad:
        print(f"self-test FAILED ({len(bad)} of "
              f"{len(MUST_CATCH) + len(MUST_ALLOW)} cases)")
        return 1
    print(f"self-test OK ({len(MUST_CATCH)} caught, {len(MUST_ALLOW)} exempt)")
    return 0


def scan_line(line: str, commands: set[str]) -> list[str]:
    """Return the existing commands a line's absence claims name, or []."""
    hits: set[str] = set()
    for rx in (ABSENCE, MCP_ONLY, MUST_USE_MCP):
        for m in rx.finditer(line):
            if allowed(m.group(0), line):
                continue
            named = {f"{r.lower()} {a.lower()}" for r, a in CMD_IN_TEXT.findall(line)}
            hits |= named & commands
    return sorted(hits)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="check against the latest runpodctl release instead of the snapshot")
    ap.add_argument("--self-test", action="store_true",
                    help="verify the patterns still catch known-bad phrasings")
    args = ap.parse_args()

    version, commands = load_surface(args.live)
    # index by "<resource> <action>" and by alias-expanded form
    exists = set(commands)

    if args.self_test:
        return self_test(exists)

    failures, notes = [], []
    for path in sorted(SKILLS.rglob("*.md")):
        rel = path.relative_to(ROOT)
        for n, line in enumerate(path.read_text().splitlines(), 1):
            hits = scan_line(line, exists)
            if hits:
                failures.append((rel, n, line.strip(), hits))
            elif any(rx.search(line) for rx in (ABSENCE, MCP_ONLY, MUST_USE_MCP)):
                notes.append((rel, n, line.strip()))

    if failures:
        print(f"CLI absence-claim check FAILED against runpodctl {version}:\n")
        for rel, n, text, hits in failures:
            print(f"  {rel}:{n}")
            print(f"    claims absence: {text[:150]}")
            print(f"    but these exist: {', '.join('runpodctl ' + h for h in hits)}\n")
        print("Fix the claim. If it is genuinely still true, add it to ALLOW with a reason.")
        return 1

    print(f"CLI absence-claim check OK against runpodctl {version} "
          f"({len(notes)} absence claim(s) reviewed, none name an existing command)")
    if args.live:
        for rel, n, text in notes:
            print(f"  note {rel}:{n}  {text[:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
