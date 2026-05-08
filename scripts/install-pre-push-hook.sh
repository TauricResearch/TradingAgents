#!/bin/bash
# Install a pre-push hook that regenerates GitNexus diagrams before every push.
#
# Usage:
#   bash scripts/install-pre-push-hook.sh
#   # or: just install-hooks

set -e

HOOK_DIR="$(git rev-parse --git-dir)/hooks"
HOOK_FILE="${HOOK_DIR}/pre-push"

cat > "${HOOK_FILE}" << 'HOOK'
#!/bin/bash
# Pre-push hook: regenerate GitNexus diagrams if pushed commits change source files.
#
# The hook receives pushed refs on stdin:
#   <local_ref> <local_sha> <remote_ref> <remote_sha>

HAS_SOURCE_CHANGES=false

while read -r local_ref local_sha remote_ref remote_sha; do
    # Skip empty or deleted refs
    [ "$local_sha" = "0000000000000000000000000000000000000000" ] && continue
    [ "$remote_sha" = "0000000000000000000000000000000000000000" ] && remote_sha=""

    # Determine the range of commits being pushed
    if [ -z "$remote_sha" ]; then
        # New branch: compare against empty tree
        range="$local_sha"
    else
        range="${remote_sha}..${local_sha}"
    fi

    # Check if any source files (not docs/diagrams) changed in this range
    CHANGED=$(git diff --name-only "$range" | grep -v "^docs/diagrams/" | grep -v "\.svg$" | grep -v "\.png$" | grep -v "\.dot$" | grep -v "\.md$" | grep -v "^\.git" || true)

    if [ -n "$CHANGED" ]; then
        HAS_SOURCE_CHANGES=true
        break
    fi
done

if [ "$HAS_SOURCE_CHANGES" = false ]; then
    echo "[pre-push] No source changes in pushed commits. Skipping diagram regen."
    exit 0
fi

echo "[pre-push] Source files changed in pushed commits. Regenerating diagrams..."

# Run diagram regeneration (suppressing most output)
if command -v just >/dev/null 2>&1; then
    just regen-diagrams >/dev/null 2>&1 || true
else
    echo "[pre-push] Warning: 'just' not found. Install with: brew install just"
    exit 0
fi

# Check if any generated diagrams changed
NEW_DIAGRAMS=$(git status --porcelain docs/diagrams/gn-* docs/diagrams/*.svg 2>/dev/null \
  | grep -E '^( M|M |A |AM|MM| D|D |\?\?)' || true)

if [ -n "$NEW_DIAGRAMS" ]; then
    echo "[pre-push] Diagrams updated. Auto-committing..."
    git add docs/diagrams/gn-*.dot docs/diagrams/gn-*.svg docs/diagrams/gn-*.png 2>/dev/null || true
    git add docs/diagrams/*.svg 2>/dev/null || true
    git commit -m "chore(diagrams): auto-regenerate from pre-push hook" --no-verify || true
    echo "[pre-push] Diagrams committed. Push will now proceed."
else
    echo "[pre-push] Diagrams unchanged."
fi

exit 0
HOOK

chmod +x "${HOOK_FILE}"
echo "Installed pre-push hook to: ${HOOK_FILE}"
echo ""
echo "This hook will auto-regenerate GitNexus diagrams on every push"
echo "where source files have changed in the commits being pushed."
