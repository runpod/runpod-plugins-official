#!/usr/bin/env bash
# MANUAL RELEASE (break-glass) — cut a tag + GitHub Release using YOUR credentials,
# not the release-please Action's GITHUB_TOKEN. Use this when the org hasn't enabled
# the release-please Action yet (so merging its PR can't tag), or the Action is down.
#
# It stays consistent with release-please: bump-version.sh also updates
# .release-please-manifest.json, so once the Action IS enabled it won't try to
# re-release a version you already cut here.
#
# Normal releases (once the org enables the Action): just merge the release PR — do
# NOT run this. See CONTRIBUTING.md → Cutting a release.
#
# Idempotent/resumable: every step checks state first, so a re-run after a partial
# failure (e.g. tag pushed but release failed) continues instead of erroring out.
#
# Usage (flags combine in any order):
#   ./scripts/release.sh X.Y.Z                 # bump + commit + push + tag + GitHub Release
#   ./scripts/release.sh X.Y.Z --publish-only  # tag current HEAD + Release only (bump already merged)
#   ./scripts/release.sh X.Y.Z --dry-run       # show what it would do, change nothing
#   ./scripts/release.sh X.Y.Z --yes           # skip the confirmation prompt (automation)
set -euo pipefail
cd "$(dirname "$0")/.."

# --- Parse args: first non-flag is the version; flags in any order ---
NEW=""
DRY=0
PUBLISH_ONLY=0
ASSUME_YES=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --publish-only) PUBLISH_ONLY=1 ;;
    --yes) ASSUME_YES=1 ;;
    -*)
      echo "error: unknown flag '$a'"
      exit 1
      ;;
    *)
      if [ -z "$NEW" ]; then
        NEW="$a"
      else
        echo "error: unexpected argument '$a'"
        exit 1
      fi
      ;;
  esac
done
[ -n "$NEW" ] || {
  echo "usage: release.sh <x.y.z> [--publish-only] [--dry-run] [--yes]"
  exit 1
}
[[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "error: version must be X.Y.Z, got '$NEW'"
  exit 1
}
TAG="v$NEW"
run() {
  echo "+ $*"
  [ "$DRY" = 1 ] || "$@"
}

# --- Guards (read-only) ---
command -v gh >/dev/null || {
  echo "error: gh CLI not found"
  exit 1
}
gh auth status >/dev/null 2>&1 || {
  echo "error: 'gh auth login' first (this releases as YOU)"
  exit 1
}

# HEAD vs origin/main — surfaced loudly (never silent), even under --yes.
git fetch -q origin main 2>/dev/null || true
if git rev-parse -q --verify origin/main >/dev/null 2>&1 &&
  [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "⚠ WARNING: HEAD ($(git rev-parse --short HEAD), $(git rev-parse --abbrev-ref HEAD)) is NOT origin/main ($(git rev-parse --short origin/main))."
  echo "  This tags/releases THIS commit, not main. Proceed only if that is intended."
fi

# --- Confirmation gate — precedes EVERY write below. --dry-run and --yes skip it. ---
confirm() {
  [ "$DRY" = 1 ] && return 0
  [ "$ASSUME_YES" = 1 ] && {
    echo "(--yes) proceeding without prompt."
    return 0
  }
  echo "About to release $TAG on origin ($(git remote get-url origin)) as $(gh api user -q .login 2>/dev/null || echo you):"
  echo "  mode=$([ "$PUBLISH_ONLY" = 1 ] && echo publish-only || echo full), target commit=$(git rev-parse --short HEAD)"
  read -r -p "Continue? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || {
    echo "aborted — nothing pushed"
    exit 1
  }
}
confirm

CUR="$(tr -d '[:space:]' <version.txt 2>/dev/null || echo '')"

# --- Bump (full mode; skipped if files are already at NEW, so a re-run resumes) ---
if [ "$PUBLISH_ONLY" = 0 ]; then
  if [ "$CUR" = "$NEW" ]; then
    echo "version files already at $NEW — skipping bump (resuming)."
  else
    [ "$DRY" = 1 ] || [ -z "$(git status --porcelain)" ] || {
      echo "error: working tree not clean — commit/stash first"
      exit 1
    }
    run ./scripts/bump-version.sh "$NEW"
    if [ "$DRY" = 0 ] && grep -q "_describe changes_" plugins/runpod/CHANGELOG.md 2>/dev/null; then
      echo "note: CHANGELOG has a '_describe changes_' placeholder — Ctrl-C, edit it, and re-run for a richer release body (re-run resumes safely)."
    fi
    run python3 hooks/check_versions.py
    run git commit -aqm "chore(release): $TAG"
  fi
  run git push origin HEAD # idempotent — no-op if already pushed
else
  run python3 hooks/check_versions.py
  [ "$DRY" = 1 ] || [ "$CUR" = "$NEW" ] || {
    echo "error: version.txt is '$CUR', not '$NEW' — did the bump merge to main?"
    exit 1
  }
fi

# --- Ensure the tag exists at the intended commit (idempotent + safety-checked) ---
TARGET="$(git rev-parse HEAD)"
ensure_tag() {
  if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    local at
    at="$(git rev-parse "refs/tags/$TAG^{commit}")"
    [ "$at" = "$TARGET" ] || {
      echo "error: local tag $TAG points at $at, not target $TARGET — delete it or check out the right commit"
      exit 1
    }
    echo "local tag $TAG already at target — ok"
  else
    git tag -a "$TAG" -m "$TAG"
  fi
  local remote_commit
  remote_commit="$(git ls-remote origin "refs/tags/$TAG^{}" 2>/dev/null | awk '{print $1}')"
  [ -n "$remote_commit" ] || remote_commit="$(git ls-remote origin "refs/tags/$TAG" 2>/dev/null | awk '{print $1}')"
  if [ -n "$remote_commit" ]; then
    [ "$remote_commit" = "$TARGET" ] || {
      echo "error: remote tag $TAG points at $remote_commit, not target $TARGET"
      exit 1
    }
    echo "remote tag $TAG already at target — ok"
  else
    git push origin "$TAG"
  fi
}
if [ "$DRY" = 1 ]; then echo "+ ensure tag $TAG at $(git rev-parse --short HEAD)"; else ensure_tag; fi

# --- Release notes: the CHANGELOG section for this version, else a stub ---
NOTES="Release $TAG"
if [ -f plugins/runpod/CHANGELOG.md ]; then
  extracted="$(awk -v v="## $NEW " 'index($0,v)==1{f=1;next} /^## /&&f{exit} f' plugins/runpod/CHANGELOG.md || true)"
  [ -n "$extracted" ] && NOTES="$extracted"
fi
case "$NOTES" in *"_describe changes_"*) echo "warning: release notes still contain the '_describe changes_' placeholder — edit CHANGELOG and re-run (idempotent) for a real body." ;; esac

# --- Ensure the GitHub Release exists (idempotent) ---
if [ "$DRY" = 1 ]; then
  echo "+ gh release create $TAG (if missing), notes:"
  printf '%s\n' "--- notes ---" "$NOTES" "-------------"
elif gh release view "$TAG" >/dev/null 2>&1; then
  echo "GitHub Release $TAG already exists — ok"
else
  printf '%s\n' "$NOTES" | gh release create "$TAG" --title "$TAG" --notes-file -
fi
echo "Done: $TAG released."
