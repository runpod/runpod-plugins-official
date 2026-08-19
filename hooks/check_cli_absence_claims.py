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

# A claim only falsifies if it names a real command path. `<verb> <noun>` pairs like
# "worker-log command" are not command paths; these are.
RESOURCES = r"pod|serverless|sls|template|tpl|hub|model|network-volume|nv|registry|reg|user|gpu|datacenter|dc|billing|doctor|ssh|send|receive|update|version"
CMD_IN_TEXT = re.compile(rf"\b({RESOURCES})\s+([a-z][a-z-]+)\b")

# Absence claims that are true and must stay allowed. Each needs a reason: this list is
# how a legitimate "MCP has no tool for this" survives the check, not an escape hatch for
# a claim nobody rechecked.
ALLOW = {
    # (substring that must appear in the matched text, why it is allowed)
    "MCP has no tool for these": "about MCP's surface, not runpodctl's",
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
FLAG_CLAIM = re.compile(r"--[a-z][a-z0-9-]*|\b(?:flag|field|param(?:eter)?|option|key)s?\b",
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="check against the latest runpodctl release instead of the snapshot")
    args = ap.parse_args()

    version, commands = load_surface(args.live)
    # index by "<resource> <action>" and by alias-expanded form
    exists = set(commands)

    failures, notes = [], []
    for path in sorted(SKILLS.rglob("*.md")):
        rel = path.relative_to(ROOT)
        for n, line in enumerate(path.read_text().splitlines(), 1):
            for rx in (ABSENCE, MCP_ONLY):
                for m in rx.finditer(line):
                    text = m.group(0)
                    why = allowed(text, line)
                    if why:
                        continue
                    named = {f"{r} {a}" for r, a in CMD_IN_TEXT.findall(text)}
                    hits = sorted(named & exists)
                    if hits:
                        failures.append((rel, n, text.strip(), hits))
                    else:
                        notes.append((rel, n, text.strip()))

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
