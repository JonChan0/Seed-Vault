#!/usr/bin/env bash
# ============================================================
# Seed Vault — Skill Installer (v2.1)
#
# Claude Code: project-local skills → .claude/skills/
#   Relative symlinks so they're portable and git-tracked.
#   Auto-loaded by Claude Code when you open this directory.
#   No /reload-plugins needed.
#
# Gemini CLI: workspace skills → skills/
#   Hard links to _vault/vault-*/SKILL.md.
#   Auto-loaded by Gemini CLI when you run `gemini` here.
#
# Run once after cloning (or after pulling framework updates).
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_ROOT="$(dirname "$SCRIPT_DIR")"

# Framework SOURCE repo vs an installed vault. The marker means "this is the
# framework being developed, not a content vault" — skip vault-only bootstrap
# (wiki skeleton, version record) so the framework repo stays clean.
IS_FRAMEWORK_REPO=false
[ -f "$VAULT_ROOT/.seed-vault-framework" ] && IS_FRAMEWORK_REPO=true

# ── Claude Code: project-local skills (.claude/skills/) ──────────────────────
CLAUDE_SKILLS_DIR="$VAULT_ROOT/.claude/skills"
mkdir -p "$CLAUDE_SKILLS_DIR"

echo "Installing Claude Code project skills to .claude/skills/..."
echo ""

# Clean up any old global seed-* symlinks that a previous install may have left
GLOBAL_SKILLS_DIR="$HOME/.claude/skills"
old_removed=0
if [ -d "$GLOBAL_SKILLS_DIR" ]; then
    for old_link in "$GLOBAL_SKILLS_DIR"/seed-*.md "$GLOBAL_SKILLS_DIR"/vault-*.md; do
        [ -L "$old_link" ] || continue
        # Only remove if it points back into this vault
        target_path="$(readlink "$old_link" 2>/dev/null || true)"
        case "$target_path" in
            "$SCRIPT_DIR"*) rm "$old_link"; echo "  ✗ Removed global: $(basename "$old_link")"; old_removed=$((old_removed + 1)) ;;
        esac
    done
fi
[ "$old_removed" -gt 0 ] && echo "  Cleaned up $old_removed old global symlink(s)" && echo ""

claude_installed=0
claude_updated=0

# Clean up stale flat-file skill links from older installers
# (.claude/skills/<name>.md). Claude Code only loads the directory layout
# .claude/skills/<name>/SKILL.md, so those flat links never registered.
stale_removed=0
for stale in "$CLAUDE_SKILLS_DIR"/vault-*.md; do
    [ -e "$stale" ] || [ -L "$stale" ] || continue
    rm -f "$stale"; echo "  ✗ Removed stale flat link: $(basename "$stale")"
    stale_removed=$((stale_removed + 1))
done
[ "$stale_removed" -gt 0 ] && echo ""

for skill_dir in "$SCRIPT_DIR"/vault-*/; do
    [ -d "$skill_dir" ] || continue
    skill_name=$(basename "$skill_dir")
    skill_md="$skill_dir/SKILL.md"
    target_dir="$CLAUDE_SKILLS_DIR/$skill_name"
    target="$target_dir/SKILL.md"

    [ -f "$skill_md" ] || { echo "  ⚠ Skipped:   $skill_name (no SKILL.md found)"; continue; }

    mkdir -p "$target_dir"

    # Relative path from .claude/skills/<name>/ to _vault/<name>/SKILL.md.
    # .claude/skills/<name>/ is three levels below VAULT_ROOT; _vault/ is one.
    rel_path="../../../_vault/$skill_name/SKILL.md"

    if [ -L "$target" ]; then
        current="$(readlink "$target" 2>/dev/null || true)"
        if [ "$current" = "$rel_path" ]; then
            echo "  = Current:   $skill_name"
            continue
        fi
        rm "$target"
        ln -s "$rel_path" "$target"
        echo "  ↻ Updated:   $skill_name"
        claude_updated=$((claude_updated + 1))
    elif [ -f "$target" ]; then
        echo "  ⚠ Skipped:   $skill_name (real file at $target — remove manually to replace)"
    else
        ln -s "$rel_path" "$target"
        echo "  ✓ Installed: $skill_name"
        claude_installed=$((claude_installed + 1))
    fi
done

echo ""
echo "Claude skills ready in .claude/skills/ (installed: $claude_installed  updated: $claude_updated)."
echo "Skills are project-local and auto-loaded — no /reload-plugins needed."
# ─────────────────────────────────────────────────────────────────────────────

echo ""

# ── Vault name templating ─────────────────────────────────────────────────────
# README is templated ONCE by bootstrap.sh when creating a vault (`bootstrap.sh new`),
# not here — install.sh re-runs on every update and would re-clobber a vault's title.
# ─────────────────────────────────────────────────────────────────────────────

# ── Dependency checks ─────────────────────────────────────────────────────────

# Check for uv
if command -v uv &>/dev/null; then
    echo "✓ uv found: $(uv --version)"
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

# Check for pandoc (optional — pypandoc wraps the pandoc binary)
if command -v pandoc &>/dev/null; then
    echo "✓ pandoc found: $(pandoc --version | head -1)"
    echo "  pypandoc (Python wrapper) will use this installation"
else
    echo "ℹ pandoc binary not found (optional — needed for PDF/DOCX conversion in vault-ingest)"
    echo "  pypandoc can download it automatically: python -c \"import pypandoc; pypandoc.download_pandoc()\""
fi

echo ""

# ── Wiki bootstrap ────────────────────────────────────────────────────────────
# wiki/ is fully gitignored — create the minimum skeleton if this is a fresh clone.
# Skipped in the framework SOURCE repo (no content vault there).
WIKI_DIR="$VAULT_ROOT/wiki"
if $IS_FRAMEWORK_REPO; then
    echo "ℹ Framework source repo (.seed-vault-framework present) — skipping wiki bootstrap."
    echo ""
else
mkdir -p "$WIKI_DIR/concepts" "$WIKI_DIR/sources" "$WIKI_DIR/topics"

INDEX_FILE="$WIKI_DIR/_index.md"
if [ ! -f "$INDEX_FILE" ]; then
    TODAY=$(date +%Y-%m-%d)
    cat > "$INDEX_FILE" <<EOF
---
title: "Wiki Index"
type: index
updated: $TODAY
---

# Wiki Index

## Concepts
*(No concepts yet — ingest sources and use vault-compile)*

## Source Summaries
*(No sources yet — drop files into \`raw/\` and use vault-ingest)*

## Topics
*(No topics yet — topics are created automatically during compilation)*

## Visualizations
*(No visualizations yet — use vault-visualize)*

## Outputs
*(No outputs yet)*

---
*Last updated: $TODAY | Total articles: 0*
EOF
    echo "Created wiki/_index.md (fresh vault)"
fi

LOG_FILE="$WIKI_DIR/_log.md"
if [ ! -f "$LOG_FILE" ]; then
    cat > "$LOG_FILE" <<EOF
---
title: "Operation Log"
type: log
updated: $(date +%Y-%m-%d)
---

# Operation Log

EOF
    echo "Created wiki/_log.md"
fi
fi  # end IS_FRAMEWORK_REPO guard
# ─────────────────────────────────────────────────────────────────────────────

# ── Version check ─────────────────────────────────────────────────────────────
# .vault_version lives at vault root (an install-state file — not wiki content).
# Back-compat: fall back to the legacy wiki/.vault_version if the root file is absent.
VERSION_FILE="$SCRIPT_DIR/VERSION"
VAULT_VERSION_FILE="$VAULT_ROOT/.vault_version"
[ -f "$VAULT_VERSION_FILE" ] || VAULT_VERSION_FILE="$WIKI_DIR/.vault_version"
if ! $IS_FRAMEWORK_REPO && [ -f "$VERSION_FILE" ]; then
    fw_ver=$(cat "$VERSION_FILE" | tr -d '[:space:]')
    if [ -f "$VAULT_VERSION_FILE" ]; then
        vault_ver=$(cat "$VAULT_VERSION_FILE" | tr -d '[:space:]')
    else
        vault_ver=""
    fi
    if [ -z "$vault_ver" ]; then
        echo "⚠ This vault has no version record (framework is now v$fw_ver)."
        echo "  Run vault-migrate in Claude Code or Gemini CLI to update your wiki articles."
    elif [ "$vault_ver" != "$fw_ver" ]; then
        echo "⚠ Framework updated to v$fw_ver (vault articles are at v$vault_ver)."
        echo "  Run vault-migrate in Claude Code or Gemini CLI to update your wiki articles."
    else
        echo "✓ Vault is current (framework v$fw_ver)."
    fi
fi
echo ""
# ─────────────────────────────────────────────────────────────────────────────

# ── Gemini CLI: workspace skills (.gemini/skills/) with hard links ────────────
echo "Setting up Gemini CLI skills directory (.gemini/skills/)..."
echo ""

GEMINI_SKILLS_DIR="$VAULT_ROOT/.gemini/skills"
mkdir -p "$GEMINI_SKILLS_DIR"

gemini_installed=0

for skill_dir in "$SCRIPT_DIR"/vault-*/; do
    [ -d "$skill_dir" ] || continue
    skill_name=$(basename "$skill_dir")
    skill_md="$skill_dir/SKILL.md"
    gemini_skill_dir="$GEMINI_SKILLS_DIR/$skill_name"
    target="$gemini_skill_dir/SKILL.md"

    [ -f "$skill_md" ] || continue

    mkdir -p "$gemini_skill_dir"

    if [ -f "$target" ]; then
        src_inode=$(stat -c '%i' "$skill_md" 2>/dev/null || stat -f '%i' "$skill_md" 2>/dev/null)
        tgt_inode=$(stat -c '%i' "$target"   2>/dev/null || stat -f '%i' "$target"   2>/dev/null)
        if [ "$src_inode" = "$tgt_inode" ]; then
            echo "  = Current:   $skill_name (hard link up to date)"
            continue
        fi
        rm "$target"
    fi

    # Hard link first; fall back to symlink if cross-filesystem
    if ln "$skill_md" "$target" 2>/dev/null; then
        echo "  ✓ Hard-linked: $skill_name → .gemini/skills/$skill_name/SKILL.md"
    else
        ln -sf "$skill_md" "$target"
        echo "  ~ Symlinked:   $skill_name (cross-filesystem fallback)"
    fi
    gemini_installed=$((gemini_installed + 1))
done

echo ""
echo "Gemini skills ready in .gemini/skills/ ($gemini_installed installed/updated)."

if command -v gemini &>/dev/null; then
    echo "✓ gemini CLI found: $(gemini --version 2>/dev/null | head -1)"
else
    echo "ℹ gemini CLI not found (optional — install: npm install -g @google/gemini-cli)"
fi
echo ""
echo "Gemini CLI users: run 'gemini' in this directory — GEMINI.md and .gemini/skills/ are auto-loaded."
# ─────────────────────────────────────────────────────────────────────────────
