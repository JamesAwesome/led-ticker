#!/bin/sh
# scripts/compute-version.sh — print led-ticker-core's PEP 440 version from git.
#
# Single source of truth for the version the build entry points (Makefile
# build/update, scripts/setup.sh, CI docker-build) pass to Docker as
# SETUPTOOLS_SCM_PRETEND_VERSION. No uv, no Python — git only.
# The image has no .git, so the host must compute this; an empty/0.0.0 core
# blocks every plugin install (plugins require led-ticker-core>=2.x).
#
# Success: prints the version to stdout, exit 0.
# Failure: prints actionable guidance to stderr, nothing to stdout, exit 1.
set -u

# Resolve to the repo root regardless of caller CWD.
cd "$(dirname "$0")/.." || exit 1

REPO_URL="https://github.com/JamesAwesome/led-ticker.git"

fail() {
    for line in "$@"; do
        printf '%s\n' "$line" >&2
    done
    exit 1
}

if [ ! -e .git ]; then
    fail \
        "Couldn't determine the led-ticker version — this folder isn't a git clone." \
        "Plugins need version info that a ZIP download doesn't include." \
        "Re-install with:  git clone $REPO_URL"
fi

desc="$(git describe --tags --long --match 'v[0-9]*' 2>/dev/null || true)"
if [ -z "$desc" ]; then
    hint="git fetch --tags"
    git_dir="$(git rev-parse --git-dir 2>/dev/null || true)"
    if [ -n "$git_dir" ] && [ -f "$git_dir/shallow" ]; then
        hint="git fetch --tags --unshallow"
    fi
    fail \
        "Couldn't determine the led-ticker version — no release tags found." \
        "Run this, then retry:  $hint"
fi

# desc looks like: v2.4.0-3-g6d65f8d9
ver="${desc#v}"      # 2.4.0-3-g6d65f8d9
ver="${ver%-g*}"     # 2.4.0-3
dist="${ver##*-}"    # 3
base="${ver%-*}"     # 2.4.0

if [ "$dist" = "0" ]; then
    # HEAD is exactly on a tag — clean release version.
    printf '%s\n' "$base"
else
    # Match setuptools-scm guess-next-dev: bump the last numeric component of
    # the base, then append .dev<distance>.  2.4.0 + 3 commits -> 2.4.1.dev3
    # Assumes numeric vX.Y.Z release tags. A pre-release tag (e.g. v3.0.0rc1)
    # with commits past it would make `last` non-numeric and the arithmetic
    # below error out — loudly (the build then fails the guard), not silently.
    last="${base##*.}"   # 0
    prefix="${base%.*}"  # 2.4
    next=$((last + 1))   # 1
    printf '%s.%s.dev%s\n' "$prefix" "$next" "$dist"
fi
