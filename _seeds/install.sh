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
    target="$SKILLS_DIR/$skill_name"

    if [ -L "$target" ]; then
        # Already a symlink — update it
        rm "$target"
        ln -s "$skill_dir" "$target"
        echo "  ↻ Updated:   $skill_name"
        ((updated++))
    elif [ -d "$target" ]; then
        # Exists as a real directory — warn, don't overwrite
        echo "  ⚠ Skipped:   $skill_name (real directory exists at $target — remove manually to replace)"
    else
        ln -s "$skill_dir" "$target"
        echo "  ✓ Installed: $skill_name"
        ((installed++))
    fi
done

echo ""
echo "Done. Installed: $installed  Updated: $updated"
echo ""
echo "Next step: run /reload-plugins in Claude Code to activate the skills."
