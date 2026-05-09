#!/usr/bin/env bash
# Symlinks every hook in .git-hooks/ into .git/hooks/.
# Safe to re-run; skips hooks that were installed manually (non-symlinks).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_SRC="${ROOT}/.git-hooks"
HOOKS_DST="${ROOT}/.git/hooks"

for hook in "${HOOKS_SRC}"/*; do
  name="$(basename "${hook}")"
  target="${HOOKS_DST}/${name}"
  if [[ -e "${target}" && ! -L "${target}" ]]; then
    echo "SKIP: .git/hooks/${name} already exists and is not a symlink — leaving it alone."
    continue
  fi
  ln -sf "${hook}" "${target}"
  chmod +x "${hook}"
  echo "Installed: .git/hooks/${name}"
done

echo
echo "Done. Staged-file secrets scan will run automatically on each commit."
echo "For a full-history scan run: bash scripts/secrets_scan_local.sh"
