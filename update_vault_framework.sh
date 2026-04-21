#!/usr/bin/env bash
# ============================================================
# Seed Vault — Framework Updater
#
# Deterministically pulls upstream framework changes and
# applies all structural migrations.
#
# Steps (in order):
#   1. Pre-flight: verify remotes, tools, clean working tree
#   2. git fetch upstream
#   3. git merge upstream/main -X theirs  (upstream wins all conflicts;
#      local uncommitted changes are stashed first)
#   4. uv sync
#   5. bash _vault/install.sh   (re-link skills, check deps)
#   6. python3 _vault/migrate.py (apply structural migrations)
#   7. Rebuild index (_vault/lib/index.py)
#   8. Push updated origin/main
#   9. Summary report
#
# Usage:
#   bash update_vault_framework.sh          # full update
#   bash update_vault_framework.sh --dry-run  # show what would change, no writes
#   bash update_vault_framework.sh --no-push  # skip pushing to origin
# ============================================================

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_ROOT="$SCRIPT_DIR"
VAULT_LIB="$VAULT_ROOT/_vault/lib"
LOG_FILE="$VAULT_ROOT/wiki/_log.md"

DRY_RUN=false
NO_PUSH=false
for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY_RUN=true  ;;
        --no-push)  NO_PUSH=true  ;;
    esac
done

MIGRATE_FLAGS=""
$DRY_RUN && MIGRATE_FLAGS="--dry-run"

TODAY=$(date +%Y-%m-%d)
TIMESTAMP=$(date +"%Y-%m-%d %H:%M")

# ── Helpers ───────────────────────────────────────────────────────────────────

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}→${NC} $*"; }
success() { echo -e "${GREEN}✓${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC} $*"; }
error()   { echo -e "${RED}✗${NC} $*" >&2; }
header()  { echo -e "\n${BOLD}$*${NC}"; echo "$(printf '─%.0s' {1..60})"; }
step()    { echo -e "\n${BOLD}[$1/8]${NC} $2"; }

append_log() {
    local msg="$1"
    if $DRY_RUN; then return; fi
    if [ -f "$LOG_FILE" ]; then
        printf "\n[%s update] %s" "$TIMESTAMP" "$msg" >> "$LOG_FILE"
    fi
}

die() { error "$1"; exit 1; }

# ── 0. Pre-flight ─────────────────────────────────────────────────────────────

header "Seed Vault — Framework Updater${DRY_RUN:+ (DRY RUN)}"

# Must run from vault root
[ -f "$VAULT_ROOT/_vault/VERSION" ] || die "Not a Seed Vault directory. Run from vault root."

cd "$VAULT_ROOT"

# Read current versions
FW_VERSION=$(cat _vault/VERSION | tr -d '[:space:]')
VAULT_VERSION_FILE="wiki/.vault_version"
if [ -f "$VAULT_VERSION_FILE" ]; then
    VAULT_VERSION=$(cat "$VAULT_VERSION_FILE" | tr -d '[:space:]')
else
    VAULT_VERSION="0.0.0 (unrecorded)"
fi

info "Framework version : $FW_VERSION  (_vault/VERSION)"
info "Vault version     : $VAULT_VERSION  (wiki/.vault_version)"
$DRY_RUN && warn "DRY RUN — no files will be written, no git operations performed"

# Check required tools
MISSING_TOOLS=()
command -v git  &>/dev/null || MISSING_TOOLS+=("git")
command -v uv   &>/dev/null || MISSING_TOOLS+=("uv")
if [ ${#MISSING_TOOLS[@]} -gt 0 ]; then
    die "Missing required tools: ${MISSING_TOOLS[*]}"
fi

# Check upstream remote exists
if ! git remote get-url upstream &>/dev/null; then
    die "No 'upstream' remote found. Add it:\n  git remote add upstream https://github.com/JonChan0/Seed-Vault"
fi

# ── 1. Stash local changes if any ─────────────────────────────────────────────

step 1 "Checking working tree"

STASHED=false
if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "Uncommitted local changes detected — stashing"
    if ! $DRY_RUN; then
        git stash push -m "update_vault_framework.sh auto-stash $TIMESTAMP"
        STASHED=true
        success "Stashed local changes"
    else
        info "[dry-run] would stash local changes"
    fi
else
    success "Working tree clean"
fi

# Restore stash on exit (even on error)
restore_stash() {
    if $STASHED; then
        warn "Restoring stashed changes..."
        git stash pop || warn "Could not restore stash — run: git stash pop"
    fi
}
trap restore_stash EXIT

# ── 2. Fetch upstream ─────────────────────────────────────────────────────────

step 2 "Fetching upstream"

if $DRY_RUN; then
    info "[dry-run] git fetch upstream"
    git fetch upstream 2>&1 | sed 's/^/  /' || true
else
    git fetch upstream
fi
success "Fetched upstream"

# Check if there's anything new
UPSTREAM_AHEAD=$(git rev-list --count HEAD..upstream/main 2>/dev/null || echo "?")
if [ "$UPSTREAM_AHEAD" = "0" ]; then
    info "Already up to date with upstream/main ($UPSTREAM_AHEAD commits ahead)"
    # Still run install.sh and migrate.py in case a previous update was incomplete
fi

FW_VERSION_BEFORE="$FW_VERSION"

# ── 3. Merge upstream/main ────────────────────────────────────────────────────

step 3 "Merging upstream/main (upstream wins conflicts)"

if $DRY_RUN; then
    info "[dry-run] git merge upstream/main -X theirs --no-edit"
    git log --oneline HEAD..upstream/main 2>/dev/null | sed 's/^/  incoming: /' || true
else
    # -X theirs: on conflicting hunks, take upstream side and discard local.
    # Non-conflicting local commits (e.g. wiki content) are preserved.
    if ! git merge upstream/main -X theirs --no-edit; then
        error "Merge failed (non-content reason: unrelated histories, binary conflict, etc.)."
        error "Inspect with: git status"
        exit 1
    fi
fi

# Re-read framework version after merge
FW_VERSION_AFTER=$(cat _vault/VERSION | tr -d '[:space:]')
if [ "$FW_VERSION_AFTER" != "$FW_VERSION_BEFORE" ]; then
    success "Framework updated: $FW_VERSION_BEFORE → $FW_VERSION_AFTER"
else
    success "Merge complete (framework version unchanged: $FW_VERSION_AFTER)"
fi

# ── 4. uv sync ────────────────────────────────────────────────────────────────

step 4 "Syncing Python dependencies (uv sync)"

if $DRY_RUN; then
    info "[dry-run] uv sync"
else
    uv sync --quiet && success "Dependencies synced" || warn "uv sync failed — run 'uv sync' manually"
fi

# ── 5. Re-install skills ──────────────────────────────────────────────────────

step 5 "Installing skills (install.sh)"

if $DRY_RUN; then
    info "[dry-run] bash _vault/install.sh"
else
    bash _vault/install.sh 2>&1 | sed 's/^/  /'
    success "Skills installed"
fi

# ── 6. Apply migrations ───────────────────────────────────────────────────────

step 6 "Applying framework migrations (migrate.py)"

MIGRATION_OUTPUT=""
if $DRY_RUN; then
    MIGRATION_OUTPUT=$(python3 _vault/migrate.py --dry-run 2>&1 || true)
    echo "$MIGRATION_OUTPUT" | sed 's/^/  /'
else
    MIGRATION_OUTPUT=$(python3 _vault/migrate.py 2>&1 || true)
    echo "$MIGRATION_OUTPUT" | sed 's/^/  /'
fi

# Detect LLM step requirement
if echo "$MIGRATION_OUTPUT" | grep -q "requires a semantic LLM step"; then
    warn "One or more migrations require an LLM step."
    warn "Open Claude Code in this vault and run: vault-migrate"
fi

# ── 7. Rebuild index ──────────────────────────────────────────────────────────

step 7 "Rebuilding index"

if $DRY_RUN; then
    info "[dry-run] uv run python _vault/lib/index.py --rebuild-qmd"
elif [ -f "$VAULT_LIB/index.py" ]; then
    uv run python _vault/lib/index.py --rebuild-qmd 2>&1 | sed 's/^/  /' || warn "Index rebuild failed — run vault-index manually"
    success "Index rebuilt"
else
    warn "_vault/lib/index.py not found — skip index rebuild"
fi

# ── 8. Push to origin ─────────────────────────────────────────────────────────

step 8 "Pushing to origin"

if $DRY_RUN || $NO_PUSH; then
    info "[skipped] git push origin main  (${DRY_RUN:+dry-run}${NO_PUSH:+--no-push})"
elif git remote get-url origin &>/dev/null; then
    git push origin main 2>&1 | sed 's/^/  /'
    success "Pushed to origin/main"
else
    warn "No 'origin' remote — skipping push"
fi

# ── 9. Summary ────────────────────────────────────────────────────────────────

# Re-read final vault version
FW_VERSION_FINAL=$(cat _vault/VERSION | tr -d '[:space:]')
VAULT_VERSION_FINAL="unknown"
[ -f "$VAULT_VERSION_FILE" ] && VAULT_VERSION_FINAL=$(cat "$VAULT_VERSION_FILE" | tr -d '[:space:]')

append_log "Framework $FW_VERSION_BEFORE → $FW_VERSION_FINAL | Vault $VAULT_VERSION → $VAULT_VERSION_FINAL"

header "Update complete${DRY_RUN:+ (DRY RUN)}"
echo ""
echo "  Framework : $FW_VERSION_BEFORE → $FW_VERSION_FINAL"
echo "  Vault     : $VAULT_VERSION → $VAULT_VERSION_FINAL"
echo ""

if $DRY_RUN; then
    warn "DRY RUN complete — no changes written. Re-run without --dry-run to apply."
elif echo "$MIGRATION_OUTPUT" | grep -q "requires a semantic LLM step"; then
    warn "ACTION REQUIRED: Run vault-migrate in Claude Code to complete LLM migration steps."
else
    success "Vault is fully up to date."
fi

echo ""
