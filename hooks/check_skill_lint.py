#!/usr/bin/env python3
"""Lint skill frontmatter and the Runpod MCP tool names the docs cite.

Checks over plugins/:

1. Every backticked MCP-tool-shaped name (`list-pods`, `create-registry`, ...) in a
   Markdown file is a tool the Runpod MCP server serves, per the vendored snapshot in
   testdata/runpod-mcp/tools.json. A name it does not serve is reported; the server's
   own tool list (`tools/list`) is where to find the current name.
2. Each SKILL.md `name` follows the Agent Skills spec (1-64 chars, lowercase letters,
   digits and single hyphens) and matches its directory; `description` is non-empty
   and at most 1024 characters (https://agentskills.io/specification).
3. `allowed-tools`, when present, is a space-separated string, as the spec requires;
   a comma between entries is reported.
4. Frontmatter uses only the spec's top-level keys, so the skills upload anywhere that
   validates against it (claude.ai rejects unknown keys such as `user-invocable`).
5. One home per fact: no Markdown file under plugins/runpod/skills copies a run of
   `min_words` consecutive words from a canonical block listed in
   hooks/canonical_facts.json (evals/, tests/ and fixtures are exempt). A copy is how a
   fact drifts: one place gets fixed and the other keeps the stale text.

Refresh the snapshot from a runpod-mcp checkout (no network, no credentials):
    python3 hooks/check_skill_lint.py --refresh ../runpod-mcp

Needs PyYAML (CI installs a pinned copy): pip install pyyaml
Run from the repo root: python3 hooks/check_skill_lint.py [--self-test]
"""

from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    yaml = importlib.import_module("yaml")
except ModuleNotFoundError:
    print("check_skill_lint needs PyYAML: pip install pyyaml")
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "testdata/runpod-mcp/tools.json"
CANONICAL = ROOT / "hooks/canonical_facts.json"
SKILLS = ROOT / "plugins/runpod/skills"

# A backticked token is checked as a tool name when it starts with one of the MCP
# server's verbs; other hyphenated words (flags, most concept ids) never match. Verb-shaped
# concept ids and skill names are exempted through NOT_TOOLS below.
VERBS = [
    *("cancel", "create", "delete", "deploy", "describe", "endpoint", "get", "list"),
    *("lookup", "pod", "purge", "read", "restart", "retry", "revoke", "run", "runsync"),
    *("search", "set", "start", "stop", "stream", "update"),
]
TOOL_SHAPE = re.compile(r"`((?:" + "|".join(VERBS) + r")-[a-z0-9]+(?:-[a-z0-9]+)*)(?=[` ])")
SPEC_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Concept ids (runpod-usage/concepts/*.yaml) and skill names are never tools, nor is
# `pod-xyz`, the example pod id in runpodctl/evals/pod-ssh-connect.eval.md.
NOT_TOOLS = (
    {"pod-xyz"}
    | {p.stem for p in (SKILLS / "runpod-usage/concepts").glob("*.yaml")}
    | {p.name for p in SKILLS.iterdir() if p.is_dir()}
)


def load_snapshot() -> set[str]:
    return set(json.loads(SNAPSHOT.read_text())["tools"])


def tool_refs(text: str, not_tools: set[str] = NOT_TOOLS) -> list[tuple[int, str]]:
    """Return (line number, name) for every backticked tool-shaped name."""
    return [
        (number, match.group(1))
        for number, line in enumerate(text.splitlines(), start=1)
        for match in TOOL_SHAPE.finditer(line)
        if match.group(1) not in not_tools
    ]


def stale(name: str, tools: set[str]) -> str | None:
    """Why a cited name is not a current tool, or None when it is one."""
    if name in tools:
        return None
    return f"`{name}` is not a Runpod MCP tool; check the server's tool list for the current name"


def frontmatter(text: str) -> dict[str, object] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            data = yaml.safe_load("\n".join(lines[1:i]))
            return data if isinstance(data, dict) else None
    return None


def skill_problems(directory: str, meta: Mapping[str, object]) -> list[str]:
    problems = []
    name = meta.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name) or len(name) > 64:
        problems.append(f"name {name!r} is not 1-64 lowercase letters, digits and hyphens")
    elif name != directory:
        problems.append(f"name {name!r} does not match its directory {directory!r}")
    description = meta.get("description")
    if not isinstance(description, str) or not description.strip():
        problems.append("description is missing or empty")
    elif len(description) > 1024:
        problems.append(f"description is {len(description)} characters (max 1024)")
    extra = sorted(set(meta) - SPEC_KEYS)
    if extra:
        problems.append(f"non-spec frontmatter key(s) {extra}; move them under metadata")
    tools = meta.get("allowed-tools")
    if tools is not None and (not isinstance(tools, str) or "," in re.sub(r"\([^)]*\)", "", tools)):
        problems.append("allowed-tools must be a space-separated string, not comma-separated")
    return problems


def words(text: str) -> list[str]:
    """Lower-cased words with Markdown emphasis, links and code fences stripped."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"\]\([^)]*\)", "] ", text)
    return re.findall(r"[a-z0-9](?:[a-z0-9_.'/+-]*[a-z0-9])?", text.lower())


def section(text: str, heading: str) -> str | None:
    """The body under `heading`, up to the next heading of the same or a higher level."""
    lines = text.splitlines()
    level = len(heading) - len(heading.lstrip("#"))
    for i, line in enumerate(lines):
        if line.strip() == heading:
            body = []
            in_fence = False
            for nxt in lines[i + 1 :]:
                if nxt.lstrip().startswith("```"):
                    in_fence = not in_fence
                m = re.match(r"^(#+) ", nxt)
                if m and not in_fence and len(m.group(1)) <= level:
                    break
                body.append(nxt)
            return "\n".join(body)
    return None


def shingles(seq: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(seq[i : i + n]) for i in range(len(seq) - n + 1)}


def duplicate_problems(files: Mapping[str, str], config: Mapping[str, object]) -> list[str]:
    """Report files that copy a run of min_words words from a canonical block."""
    n, blocks = config["min_words"], config["blocks"]
    if not isinstance(n, int) or not isinstance(blocks, list):
        raise TypeError("canonical facts: min_words must be an int and blocks a list")
    problems = []
    tokens = {path: words(text) for path, text in files.items()}
    for block in blocks:
        home, heading = block["home"], block["heading"]
        body = section(files.get(home, ""), heading)
        if body is None:
            problems.append(
                f"canonical block {block['id']}: heading {heading!r} not found in {home}"
            )
            continue
        canon = shingles(words(body), n)
        allowed = {a["path"] for a in block.get("allow", [])}
        for path, seq in tokens.items():
            if path == home or path in allowed or re.search(r"(^|/)(evals|tests|fixtures)/", path):
                continue
            for i in range(len(seq) - n + 1):
                if tuple(seq[i : i + n]) in canon:
                    problems.append(
                        f"{path}: copies canonical block {block['id']!r} ({home} {heading!r}): "
                        f'"{" ".join(seq[i : i + n])}"; link to it or summarize in your own words'
                    )
                    break
    return problems


def refresh(checkout: Path) -> None:
    """Rewrite the snapshot from a runpod-mcp checkout's tool sources."""
    names: set[str] = set()
    sources = [checkout / "src/specgen/generated/tools.gen.ts"]
    sources += sorted((checkout / "src/specgen/tools").glob("*.ts"))
    for source in sources:
        names.update(re.findall(r"^\s{2,4}name: '([a-z][a-z0-9_-]*)',$", source.read_text(), re.M))
    on_demand = (checkout / "src/specgen/on-demand.ts").read_text()
    names.update(re.findall(r"DESCRIBE_TOOL_NAME = '([a-z-]+)'", on_demand))
    if not names:
        sys.exit(f"refresh: no tool names found under {checkout}")
    commit = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    snapshot = {
        "source": f"runpod/runpod-mcp@{commit}",
        "tools": sorted(names),
    }
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(f"wrote {SNAPSHOT.relative_to(ROOT)}: {len(names)} tools from {snapshot['source']}")


def self_test() -> None:
    assert tool_refs("use `list-pods` then `stop-pod`; see `pod-doctor`", {"pod-doctor"}) == [
        (1, "list-pods"),
        (1, "stop-pod"),
    ]
    assert tool_refs("`get-job-status wait:300000`") == [(1, "get-job-status")]
    tools = load_snapshot()
    derived = {n.split("-")[0] for n in tools if "-" in n}
    assert derived <= set(VERBS), f"VERBS is missing {sorted(derived - set(VERBS))}"
    not_tools = {"pod-volume-disk"}
    assert (
        tool_refs("`network-volume`, `pod-volume-disk` and `runpodctl pod list`", not_tools) == []
    )
    assert "tool list" in (stale("stop-pod", {"pod-action"}) or "")
    assert stale("pod-action", {"pod-action"}) is None
    good = {
        "name": "demo",
        "description": "Does a thing. Use when asked.",
        "allowed-tools": "Bash(rg:*) Bash(python3 x.py:*)",
    }
    assert skill_problems("demo", good) == []
    assert skill_problems("other", good)
    assert skill_problems("demo", {**good, "description": "x" * 1025})
    assert skill_problems("demo", {**good, "allowed-tools": "Bash(rg:*), Bash(ls:*)"})
    assert skill_problems("demo", {**good, "allowed-tools": "Read, Grep"})
    assert skill_problems("demo", {**good, "name": "Demo--x"})
    assert skill_problems("demo", {**good, "user-invocable": True})
    canon = (
        "# T\n\n## Rule\n\nPin the floor on every create or a modern image lands on an old host."
        "\n\n```bash\n# a shell comment, not a heading\n```\n\nStill the rule."
        "\n\n## Next\n\nother"
    )
    config: dict[str, Any] = {
        "min_words": 6,
        "blocks": [{"id": "r", "home": "a.md", "heading": "## Rule"}],
    }
    copy = {
        "a.md": canon,
        "b.md": "As noted: pin the floor on every create or a modern image lands.",
    }
    assert len(duplicate_problems(copy, config)) == 1
    assert (
        duplicate_problems({"a.md": canon, "b.md": "Set a floor ([why](a.md#rule))."}, config) == []
    )
    assert duplicate_problems({"a.md": canon, "x/evals/e.md": copy["b.md"]}, config) == []
    assert duplicate_problems({"a.md": "# T"}, config)
    allow = {
        **config,
        "blocks": [{**config["blocks"][0], "allow": [{"path": "b.md", "reason": "r"}]}],
    }
    assert duplicate_problems(copy, allow) == []
    rule = section(canon, "## Rule")
    assert rule is not None and "other" not in rule and "Still the rule." in rule
    assert words("Pin it explicitly. Then 12.8.") == ["pin", "it", "explicitly", "then", "12.8"]
    print("skill lint self-test OK")


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        return
    if "--refresh" in sys.argv:
        if sys.argv.index("--refresh") + 1 >= len(sys.argv):
            sys.exit("usage: check_skill_lint.py --refresh <runpod-mcp checkout>")
        refresh(Path(sys.argv[sys.argv.index("--refresh") + 1]).resolve())
        return
    tools = load_snapshot()
    errors: list[str] = []
    for md in sorted(p for p in (ROOT / "plugins").rglob("*.md") if p.name != "CHANGELOG.md"):
        rel = md.relative_to(ROOT)
        for number, name in tool_refs(md.read_text(errors="replace")):
            problem = stale(name, tools)
            if problem:
                errors.append(f"{rel}:{number}: {problem}")
    texts = {
        str(p.relative_to(SKILLS)): p.read_text(errors="replace")
        for p in sorted(SKILLS.rglob("*.md"))
    }
    errors += duplicate_problems(texts, json.loads(CANONICAL.read_text()))
    for skill in sorted(SKILLS.glob("*/SKILL.md")):
        meta = frontmatter(skill.read_text(errors="replace"))
        if meta is None:
            errors.append(f"{skill.relative_to(ROOT)}: no parseable frontmatter")
            continue
        rel = skill.relative_to(ROOT)
        errors += [f"{rel}: {problem}" for problem in skill_problems(skill.parent.name, meta)]
    if errors:
        print(f"skill lint FAILED: {len(errors)} problem(s)")
        for error in errors:
            print(f"  {error}")
        snapshot = SNAPSHOT.relative_to(ROOT)
        print(f"Tool names are checked against {snapshot}; refresh it with --refresh.")
        sys.exit(1)
    print(f"skill lint OK ({len(tools)} MCP tools in snapshot)")


if __name__ == "__main__":
    main()
