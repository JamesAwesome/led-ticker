#!/usr/bin/env bash
# Fail if a non-pnpm lockfile sneaks under docs/site/.
# Wired up as a pre-commit hook in .pre-commit-config.yaml. The
# `preinstall: npx only-allow pnpm` script in docs/site/package.json
# is the primary block; this script is the belt-and-suspenders catch
# for the case where someone bypasses lifecycle hooks (e.g. via
# `npm install --ignore-scripts` or by hand-editing the file in).
set -euo pipefail

bad=0
for f in docs/site/package-lock.json docs/site/yarn.lock; do
  if [ -f "$f" ]; then
    echo "ERROR: $f is present. led-ticker uses pnpm — delete the file and run pnpm install."
    bad=1
  fi
done
exit "$bad"
