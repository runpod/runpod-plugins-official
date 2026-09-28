#!/usr/bin/env python3
"""Validate the plugin marketplace manifests and their referenced paths.

Checks, statically (no network, no harness):
  - .claude-plugin/marketplace.json parses and has name + plugins.
  - Each plugin's source dir exists under metadata.pluginRoot (default ./plugins).
  - Each plugin has a .claude-plugin/plugin.json that parses.
  - Every skills[] path resolves to a dir containing a SKILL.md.
  - A plugin .mcp.json (if present) parses.
  - .agents/plugins/marketplace.json (Codex, if present) parses and its plugin
    source paths exist.

Exit non-zero on any failure. Run from the repo root: python3 hooks/validate_marketplace.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

type JSONValue = bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"] | None

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []


def load_json(path: Path) -> JSONValue:
    try:
        data: JSONValue = json.loads(path.read_text())
    except FileNotFoundError:
        errors.append(f"missing file: {path.relative_to(ROOT)}")
        return None
    except json.JSONDecodeError as e:
        errors.append(f"invalid JSON in {path.relative_to(ROOT)}: {e}")
        return None
    return data


def check_claude_marketplace() -> None:
    mp = load_json(ROOT / ".claude-plugin" / "marketplace.json")
    if mp is None:
        return
    if not isinstance(mp, dict):
        errors.append(".claude-plugin/marketplace.json: not a JSON object")
        return
    if not mp.get("name"):
        errors.append(".claude-plugin/marketplace.json: missing 'name'")
    plugins = mp.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        errors.append(".claude-plugin/marketplace.json: 'plugins' must be a non-empty list")
        return
    metadata = mp.get("metadata")
    plugin_root_val = (
        metadata.get("pluginRoot", "./plugins") if isinstance(metadata, dict) else None
    )
    plugin_root = ROOT / (plugin_root_val if isinstance(plugin_root_val, str) else "./plugins")
    for p in plugins:
        if not isinstance(p, dict):
            errors.append("plugin entry is not a JSON object")
            continue
        name = p.get("name", "<unnamed>")
        source = p.get("source")
        if not isinstance(source, str) or not source:
            errors.append(f"plugin '{name}': missing 'source'")
            continue
        # Claude Code requires a repo-root-relative path (must start with "." or "/");
        # a bare name is the pluginRoot-relative shorthand. Resolve accordingly.
        base = ROOT if source.startswith((".", "/")) else plugin_root
        pdir = (base / source).resolve()
        if not pdir.is_dir():
            errors.append(f"plugin '{name}': source dir not found: {pdir.relative_to(ROOT)}")
            continue
        # per-plugin manifests (Claude Code, and Codex/Gemini if present)
        load_json(pdir / ".claude-plugin" / "plugin.json")
        for extra in (pdir / ".codex-plugin" / "plugin.json", pdir / "gemini-extension.json"):
            if extra.exists():
                load_json(extra)
        # bundled MCP config, if any
        mcp = pdir / ".mcp.json"
        if mcp.exists():
            load_json(mcp)
        # declared skills
        skills = p.get("skills", [])
        if not isinstance(skills, list):
            continue
        for sk in skills:
            if not isinstance(sk, str):
                continue
            sdir = (pdir / sk).resolve()
            if not sdir.is_dir():
                errors.append(f"plugin '{name}': skill path not found: {sk}")
            elif not (sdir / "SKILL.md").is_file():
                errors.append(f"plugin '{name}': no SKILL.md in {sk}")


def check_codex_marketplace() -> None:
    path = ROOT / ".agents" / "plugins" / "marketplace.json"
    if not path.exists():
        return  # Codex support is optional
    mp = load_json(path)
    if mp is None:
        return
    if not isinstance(mp, dict):
        errors.append(".agents/plugins/marketplace.json: not a JSON object")
        return
    plugins = mp.get("plugins", [])
    if not isinstance(plugins, list):
        return
    for p in plugins:
        if not isinstance(p, dict):
            continue
        name = p.get("name")
        src = p.get("source")
        rel = src.get("path") if isinstance(src, dict) else None
        if not isinstance(rel, str) or not rel:
            errors.append(f"codex plugin '{name}': missing source.path")
            continue
        if not (ROOT / rel).is_dir():
            errors.append(f"codex plugin '{name}': path not found: {rel}")


def main() -> int:
    check_claude_marketplace()
    check_codex_marketplace()
    if errors:
        print("marketplace validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("marketplace validation OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
