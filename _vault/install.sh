#!/usr/bin/env bash
# ============================================================
# Seed Vault — Skill Installer (v2.0)
# Symlinks all vault-* skills into ~/.claude/skills/
# Checks for uv and qmd dependencies
# Run this once after cloning, then /reload-plugins in Claude Code
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_ROOT="$(dirname "$SCRIPT_DIR")"
SKILLS_DIR="$HOME/.claude/skills"

# Ensure skills directory exists
mkdir -p "$SKILLS_DIR"

echo "Installing Seed Vault skills to $SKILLS_DIR..."
echo ""

# ── Remove old seed-* symlinks ──────────────────────────────────────
old_removed=0
for old_link in "$SKILLS_DIR"/seed-*.md; do
    [ -L "$old_link" ] || continue
    rm "$old_link"
    echo "  ✗ Removed old: $(basename "$old_link")"
    old_removed=$((old_removed + 1))
done
if [ "$old_removed" -gt 0 ]; then
    echo "  Cleaned up $old_removed old seed-* symlinks"
    echo ""
fi

# ── Install vault-* skills ──────────────────────────────────────────
installed=0
updated=0

for skill_dir in "$SCRIPT_DIR"/vault-*/; do
    [ -d "$skill_dir" ] || continue
    skill_name=$(basename "$skill_dir")
    skill_md="$skill_dir/SKILL.md"
    target="$SKILLS_DIR/$skill_name.md"

    [ -f "$skill_md" ] || { echo "  ⚠ Skipped:   $skill_name (no SKILL.md found)"; continue; }

    if [ -L "$target" ]; then
        rm "$target"
        ln -s "$skill_md" "$target"
        echo "  ↻ Updated:   $skill_name"
        updated=$((updated + 1))
    elif [ -f "$target" ]; then
        echo "  ⚠ Skipped:   $skill_name (real file exists at $target — remove manually to replace)"
    else
        ln -s "$skill_md" "$target"
        echo "  ✓ Installed: $skill_name"
        installed=$((installed + 1))
    fi
done

echo ""
echo "Done. Installed: $installed  Updated: $updated"

# ── Vault name substitution ──────────────────────────────────────
REPO_NAME="$(basename "$VAULT_ROOT")"
VAULT_DISPLAY="$(echo "$REPO_NAME" | sed 's/[-_]/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1')"

README="$VAULT_ROOT/README.md"
if [ -f "$README" ] && [ "$VAULT_DISPLAY" != "Seed Vault" ]; then
    sed -i "s/Seed Vault/$VAULT_DISPLAY/g" "$README"
    echo "Updated README.md: 'Seed Vault' → '$VAULT_DISPLAY'"
fi
# ─────────────────────────────────────────────────────────────────

echo ""

# ── Dependency checks ────────────────────────────────────────────────

# Check for uv
if command -v uv &>/dev/null; then
    echo "✓ uv found: $(uv --version)"
    # Sync Python dependencies
    if [ -f "$VAULT_ROOT/pyproject.toml" ]; then
        echo "  Syncing Python dependencies..."
        (cd "$VAULT_ROOT" && uv sync --quiet 2>/dev/null) && echo "  ✓ Dependencies synced" || echo "  ⚠ uv sync failed — run 'uv sync' manually in the vault root"
    fi
else
    echo "⚠ uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/"
    echo "  uv is needed for deterministic Python engines (_vault/lib/)"
fi

# Check for qmd
if command -v qmd &>/dev/null; then
    echo "✓ qmd found"
else
    echo "⚠ qmd not found. Install it: npm install -g @tobilu/qmd"
    echo "  qmd provides fast search indexing for vault-qa and vault-index"
fi

# Check for pandoc (optional, for PDF/DOCX conversion)
if command -v pandoc &>/dev/null; then
    echo "✓ pandoc found: $(pandoc --version | head -1)"
else
    echo "ℹ pandoc not found (optional — needed for PDF/DOCX conversion in vault-ingest)"
fi

echo ""

# ── Version check ────────────────────────────────────────────────────────────
VERSION_FILE="$SCRIPT_DIR/VERSION"
INDEX_FILE="$VAULT_ROOT/wiki/_index.md"
if [ -f "$VERSION_FILE" ] && [ -f "$INDEX_FILE" ]; then
    fw_ver=$(cat "$VERSION_FILE" | tr -d '[:space:]')
    vault_ver=$(grep 'framework_version:' "$INDEX_FILE" 2>/dev/null | sed 's/.*: *["\x27]*\([^"'\'']*\)["\x27]*.*/\1/' | tr -d '[:space:]')
    if [ -z "$vault_ver" ]; then
        echo "⚠ This vault predates framework versioning (framework is now v$fw_ver)."
        echo "  Run vault-migrate in Claude Code to update your wiki articles."
    elif [ "$vault_ver" != "$fw_ver" ]; then
        echo "⚠ Framework updated to v$fw_ver (vault is at v$vault_ver)."
        echo "  Run vault-migrate in Claude Code to update your wiki articles."
    else
        echo "✓ Vault is current (framework v$fw_ver)."
    fi
fi
# ─────────────────────────────────────────────────────────────────────────────

echo "Next step: run /reload-plugins in Claude Code to activate the skills."
