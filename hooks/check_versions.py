#!/usr/bin/env python3
"""Version consistency guard. Run from repo root.

Every version-bearing file must declare the SAME version — the plugin is versioned as
a whole, and each skill's `metadata.version` mirrors that single plugin version in
lockstep (see CONTRIBUTING.md → Cutting a release). Releases are automated by
release-please; this guard just fails CI if anything ever drifts out of sync.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
seen = {}

# JSON manifests: read the top-level "version" key.
for f in [
    "plugins/runpod/.claude-plugin/plugin.json",
    "plugins/runpod/.codex-plugin/plugin.json",
    "plugins/runpod/gemini-extension.json",
    ".claude-plugin/marketplace.json",
]:
    seen[f] = json.loads((ROOT / f).read_text()).get("version")

# release-please sources of truth.
seen["version.txt"] = (ROOT / "version.txt").read_text().strip() or None
seen[".release-please-manifest.json"] = json.loads(
    (ROOT / ".release-please-manifest.json").read_text()
).get(".")

# Skill frontmatter: read `version:` from each SKILL.md (tolerates a trailing
# `# x-release-please-version` annotation comment).
_VER_RE = re.compile(r'^\s*version:\s*"?([0-9][^"\s]*)"?', re.MULTILINE)
for skill in sorted(ROOT.glob("plugins/runpod/skills/*/SKILL.md")):
    m = _VER_RE.search(skill.read_text())
    seen[str(skill.relative_to(ROOT))] = m.group(1) if m else None

# A skill release-please does not know about never gets bumped, so the next
# release PR fails this check instead of the PR that added the skill. Catch it
# where it is cheap to fix.
config = json.loads((ROOT / "release-please-config.json").read_text())
registered = {
    entry if isinstance(entry, str) else entry["path"]
    for entry in config["packages"]["."]["extra-files"]
}
unregistered = sorted(
    str(skill.relative_to(ROOT))
    for skill in ROOT.glob("plugins/runpod/skills/*/SKILL.md")
    if str(skill.relative_to(ROOT)) not in registered
)
if unregistered:
    print("version check FAILED — skills missing from release-please-config.json:")
    for f in unregistered:
        print(f"  {f}")
    print("Add each to packages['.'].extra-files, or release-please will not bump it.")
    sys.exit(1)

vals = set(seen.values())
if None in vals or len(vals) != 1:
    print("version check FAILED — versions disagree:")
    for f, v in seen.items():
        print(f"  {str(v):10} {f}")
    sys.exit(1)
print(f"version check OK — all manifests + skills at {vals.pop()}")
