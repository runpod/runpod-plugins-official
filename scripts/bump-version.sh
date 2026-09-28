#!/usr/bin/env bash
# LOCAL / EMERGENCY FALLBACK ONLY. Normal releases are automated by release-please
# (see CONTRIBUTING.md → Cutting a release): write Conventional Commits, merge the
# release PR it opens. Use this script only for a local test bump or if the Action
# is unavailable. It sets the version across every version-bearing file at once so
# nothing drifts (CI's check_versions.py enforces that they all agree).
# Usage: ./scripts/bump-version.sh 1.1.0
set -euo pipefail
NEW="${1:?usage: bump-version.sh <x.y.z>}"
cd "$(dirname "$0")/.."

# JSON manifests: replace the first "version": "..." string.
for f in \
  plugins/runpod/.claude-plugin/plugin.json \
  plugins/runpod/.codex-plugin/plugin.json \
  plugins/runpod/gemini-extension.json \
  .claude-plugin/marketplace.json \
  packages/knowledge/package.json; do
  python3 - "$f" "$NEW" <<'PY'
import re,sys
p,new=sys.argv[1],sys.argv[2]
s=open(p).read()
s2,n=re.subn(r'("version"\s*:\s*")[^"]+(")', lambda m: m.group(1)+new+m.group(2), s, count=1)
if n==0: sys.exit(f"no version field in {p}")
open(p,"w").write(s2); print(f"  {p} -> {new}")
PY
done

# release-please sources of truth.
printf '%s\n' "$NEW" >version.txt && echo "  version.txt -> $NEW"
python3 - .release-please-manifest.json "$NEW" <<'PY'
import json,sys
p,new=sys.argv[1],sys.argv[2]
d=json.load(open(p)); d["."]=new
open(p,"w").write(json.dumps(d,indent=2)+"\n"); print(f"  {p} -> {new}")
PY

# Skill frontmatter: bump each SKILL.md's `metadata.version` (YAML), preserving any
# trailing `# x-release-please-version` annotation comment.
for f in plugins/runpod/skills/*/SKILL.md; do
  python3 - "$f" "$NEW" <<'PY'
import re,sys
p,new=sys.argv[1],sys.argv[2]
s=open(p).read()
s2,n=re.subn(r'(?m)^(\s*version:\s*")[^"]+(".*)$', lambda m: m.group(1)+new+m.group(2), s, count=1)
if n==0: sys.exit(f"no version field in {p}")
open(p,"w").write(s2); print(f"  {p} -> {new}")
PY
done

# Prepend a CHANGELOG entry above the first "## " release heading (below the intro).
CL=plugins/runpod/CHANGELOG.md
DATE=$(date +%F)
python3 - "$CL" "$NEW" "$DATE" <<'PY'
import sys
p,new,date=sys.argv[1],sys.argv[2],sys.argv[3]
lines=open(p).read().splitlines(keepends=True)
at=next((i for i,l in enumerate(lines) if l.startswith('## ')), len(lines))
lines.insert(at, f"## {new} ({date})\n\n- _describe changes_\n\n")
open(p,"w").write("".join(lines))
PY
echo "Done. Edit $CL, then:  git commit -am \"chore(release): v$NEW\" && git tag v$NEW"
