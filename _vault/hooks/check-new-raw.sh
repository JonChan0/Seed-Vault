#!/bin/bash
# Detect new files in raw/ since last session.
# Outputs a directive to Claude to auto-ingest via vault-ingest.
# Manifest: .claude/raw-manifest.txt (gitignored, local state)

PROJECT_ROOT="$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$PROJECT_ROOT" ]; then
    exit 0
fi

RAW_DIR="$PROJECT_ROOT/raw"
MANIFEST="$PROJECT_ROOT/.claude/raw-manifest.txt"

if [ ! -d "$RAW_DIR" ]; then
    exit 0
fi

mkdir -p "$(dirname "$MANIFEST")"
touch "$MANIFEST"

new_files=()
while IFS= read -r -d '' file; do
    relpath="${file#$PROJECT_ROOT/}"
    if ! grep -qxF "$relpath" "$MANIFEST"; then
        new_files+=("$relpath")
        echo "$relpath" >> "$MANIFEST"
    fi
done < <(find "$RAW_DIR" -type f \( \
    -name "*.md" -o -name "*.pdf" -o -name "*.txt" \
    -o -name "*.html" -o -name "*.htm" -o -name "*.docx" \
\) ! -name ".gitkeep" -print0 | sort -z)

count=${#new_files[@]}

if [ "$count" -eq 0 ]; then
    printf '{"suppressOutput":true,"continue":true}'
    exit 0
fi

echo "AUTO-INGEST: $count new source(s) detected in raw/ since last session:"
echo ""
for f in "${new_files[@]}"; do
    echo "  - $f"
done
echo ""
echo "Per vault ownership rules (CLAUDE.md): run vault-ingest on each file above"
echo "immediately using one parallel Agent subagent per file. Do not wait for user confirmation."
