#!/usr/bin/env bash
# ============================================================
# Seed Vault — Skill Installer
# Symlinks all seed-* skills into ~/.claude/skills/
# Run this once after cloning, then /reload-plugins in Claude Code
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills"

# Ensure skills directory exists
mkdir -p "$SKILLS_DIR"

echo "Installing Seed Vault skills to $SKILLS_DIR..."
echo ""

installed=0
updated=0

for skill_dir in "$SCRIPT_DIR"/seed-*/; do
    [ -d "$skill_dir" ] || continue
    skill_name=$(basename "$skill_dir")
    skill_md="$skill_dir/SKILL.md"
    target="$SKILLS_DIR/$skill_name.md"

    [ -f "$skill_md" ] || { echo "  ⚠ Skipped:   $skill_name (no SKILL.md found)"; continue; }

    if [ -L "$target" ]; then
        # Already a symlink — update it
        rm "$target"
        ln -s "$skill_md" "$target"
        echo "  ↻ Updated:   $skill_name"
        updated=$((updated + 1))
    elif [ -f "$target" ]; then
        # Exists as a real file — warn, don't overwrite
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
# Replace "Seed Vault" in README.md with the actual vault name,
# derived from the repository/folder name.
VAULT_ROOT="$(dirname "$SCRIPT_DIR")"
REPO_NAME="$(basename "$VAULT_ROOT")"

# Convert hyphens/underscores to spaces, then title-case each word
VAULT_DISPLAY="$(echo "$REPO_NAME" | sed 's/[-_]/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1')"

README="$VAULT_ROOT/README.md"
if [ -f "$README" ] && [ "$VAULT_DISPLAY" != "Seed Vault" ]; then
    sed -i "s/Seed Vault/$VAULT_DISPLAY/g" "$README"
    echo "Updated README.md: 'Seed Vault' → '$VAULT_DISPLAY'"
fi
# ─────────────────────────────────────────────────────────────────

echo ""

# ── Version check ────────────────────────────────────────────────────────────
VERSION_FILE="$SCRIPT_DIR/VERSION"
INDEX_FILE="$VAULT_ROOT/wiki/_index.md"
if [ -f "$VERSION_FILE" ] && [ -f "$INDEX_FILE" ]; then
    fw_ver=$(cat "$VERSION_FILE" | tr -d '[:space:]')
    vault_ver=$(grep 'framework_version:' "$INDEX_FILE" 2>/dev/null | sed 's/.*: *["\x27]*\([^"'\'']*\)["\x27]*.*/\1/' | tr -d '[:space:]')
    if [ -z "$vault_ver" ]; then
        echo "⚠ This vault predates framework versioning (framework is now v$fw_ver)."
        echo "  Run seed-migrate in Claude Code to update your wiki articles."
    elif [ "$vault_ver" != "$fw_ver" ]; then
        echo "⚠ Framework updated to v$fw_ver (vault is at v$vault_ver)."
        echo "  Run seed-migrate in Claude Code to update your wiki articles."
    else
        echo "✓ Vault is current (framework v$fw_ver)."
    fi
fi
# ─────────────────────────────────────────────────────────────────────────────

echo "Next step: run /reload-plugins in Claude Code to activate the skills."
