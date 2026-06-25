#!/usr/bin/env bash
# ============================================================
# Seed Vault — Framework Installer / Updater (bootstrap.sh)
#
# Installs the Seed Vault FRAMEWORK into any directory and updates it later
# to a pinned version — without touching your vault content (wiki/, raw/, ...).
#
# The framework is whatever _vault/manifest.txt lists. Update overwrites EXACTLY
# those paths and nothing else, so notes are safe by construction.
#
# Usage:
#   bootstrap.sh new <target-dir> [--version vX.Y.Z] [--dry-run] [--source-dir DIR]
#       Create a fresh vault in <target-dir>.
#
#   bootstrap.sh update [--version vX.Y.Z] [--dry-run] [--source-dir DIR] [--no-push]
#       Update the vault in the current directory. Default version = latest tag.
#
# Options:
#   --version vX.Y.Z   Pin to a specific release tag (default: latest tag on origin).
#   --dry-run          Show what would change; write nothing.
#   --source-dir DIR   Install from a local framework checkout instead of downloading
#                      (DIR must contain _vault/manifest.txt). Useful offline / for testing.
#   --no-push          Accepted for back-compat; no effect (update never pushes).
#
# One-liner (remote):
#   curl -fsSL https://raw.githubusercontent.com/JonChan0/Seed-Vault/main/bootstrap.sh | bash -s -- new ~/my-vault
# ============================================================

set -euo pipefail

REPO_URL="https://github.com/JonChan0/Seed-Vault"

# ── Output helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${CYAN}→${NC} $*"; }
success() { echo -e "${GREEN}✓${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC} $*"; }
error()   { echo -e "${RED}✗${NC} $*" >&2; }
header()  { echo -e "\n${BOLD}$*${NC}"; echo "$(printf '─%.0s' {1..60})"; }
die()     { error "$1"; exit 1; }

# ── Arg parsing ───────────────────────────────────────────────────────────────
SUBCMD="${1:-}"; shift || true

VERSION=""
DRY_RUN=false
SOURCE_DIR=""
TARGET_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        --version)    VERSION="${2:-}"; shift 2 ;;
        --dry-run)    DRY_RUN=true; shift ;;
        --source-dir) SOURCE_DIR="${2:-}"; shift 2 ;;
        --no-push)    shift ;;  # back-compat no-op
        -*)           die "Unknown option: $1" ;;
        *)            TARGET_DIR="$1"; shift ;;
    esac
done

DRY_LABEL=""
$DRY_RUN && DRY_LABEL=" (DRY RUN)"

case "$SUBCMD" in
    new|update) ;;
    ""|-h|--help|help) grep '^#' "$0" | grep -v '^#!' | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "Unknown subcommand: '$SUBCMD'. Use 'new <dir>' or 'update'." ;;
esac

# ── Version resolution ────────────────────────────────────────────────────────
# Bare semver (e.g. 3.0.0) is recorded in .vault_version; the matching tag is vX.Y.Z.
resolve_latest_tag() {
    git ls-remote --tags "$REPO_URL" 2>/dev/null \
        | sed -n 's#.*refs/tags/v\([0-9]*\.[0-9]*\.[0-9]*\)$#\1#p' \
        | sort -t. -k1,1n -k2,2n -k3,3n | tail -1
}

# Strip optional leading 'v' → bare semver
to_bare() { echo "${1#v}"; }

# ── Fetch framework into a temp dir; echo the extracted root path ─────────────
fetch_framework() {
    local bare="$1" tmp root
    # Extract into a temp dir under $TMPDIR; left for the OS to reap (matches prior behavior).
    tmp="$(mktemp -d)"

    if [ -n "$SOURCE_DIR" ]; then
        [ -f "$SOURCE_DIR/_vault/manifest.txt" ] || die "--source-dir has no _vault/manifest.txt: $SOURCE_DIR"
        # Copy tracked-ish tree; if it's a git repo use archive (only tracked files), else cp.
        if git -C "$SOURCE_DIR" rev-parse --git-dir >/dev/null 2>&1; then
            (cd "$SOURCE_DIR" && git archive --format=tar HEAD) | tar -x -C "$tmp"
        else
            cp -a "$SOURCE_DIR/." "$tmp/"
        fi
        root="$tmp"
    else
        local tag="v$bare" url="$REPO_URL/archive/refs/tags/v$bare.tar.gz"
        info "Downloading framework $tag from $REPO_URL" >&2
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL "$url" | tar -xz -C "$tmp" || die "Download/extract failed for tag $tag"
        elif command -v wget >/dev/null 2>&1; then
            wget -qO- "$url" | tar -xz -C "$tmp" || die "Download/extract failed for tag $tag"
        else
            command -v git >/dev/null 2>&1 || die "Need curl, wget, or git to fetch the framework."
            git clone --depth 1 --branch "$tag" "$REPO_URL" "$tmp/clone" >/dev/null 2>&1 \
                || die "git clone of tag $tag failed."
            root="$tmp/clone"; echo "$root"; return
        fi
        # tarball extracts to a single Seed-Vault-<bare>/ dir
        root="$(find "$tmp" -maxdepth 1 -type d -name 'Seed-Vault-*' | head -1)"
        [ -n "$root" ] || root="$tmp"
    fi
    echo "$root"
}

# ── Read manifest → newline list of paths (strip comments/blanks) ─────────────
read_manifest() {
    local root="$1"
    [ -f "$root/_vault/manifest.txt" ] || die "Framework manifest missing: $root/_vault/manifest.txt"
    grep -vE '^\s*(#|$)' "$root/_vault/manifest.txt" | sed 's/[[:space:]]*$//'
}

# ── Sync one manifest path from src→dest (dir = mirror with delete; file = copy)
sync_one() {
    local src="$1" dest="$2" path="$3"
    local from="$src/$path" to="$dest/$path"
    [ -e "$from" ] || { warn "manifest path not in framework, skipping: $path"; return; }

    if [ -d "$from" ]; then
        if command -v rsync >/dev/null 2>&1; then
            if $DRY_RUN; then rsync -ai --delete --dry-run "$from/" "$to/" | sed 's/^/    /'
            else mkdir -p "$to"; rsync -a --delete "$from/" "$to/"; fi
        else
            if $DRY_RUN; then echo "    [dry-run] replace dir $path/"
            else rm -rf "$to"; mkdir -p "$(dirname "$to")"; cp -a "$from" "$to"; fi
        fi
    else
        if $DRY_RUN; then
            if cmp -s "$from" "$to" 2>/dev/null; then :; else echo "    [dry-run] write file $path"; fi
        else
            # Atomic: write temp then rename → new inode. A running script that is itself
            # being updated (bootstrap.sh) keeps executing from its original inode.
            mkdir -p "$(dirname "$to")"
            cp -a "$from" "$to.tmp.$$" && mv -f "$to.tmp.$$" "$to"
        fi
    fi
}

sync_manifest() {
    local src="$1" dest="$2"
    while IFS= read -r path; do
        [ -n "$path" ] && sync_one "$src" "$dest" "$path"
    done < <(read_manifest "$src")
}

# ── Derive a display name from a directory basename ───────────────────────────
display_name() {
    basename "$1" | sed 's/[-_]/ /g' \
        | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1'
}

# ============================================================================
# Subcommand: new
# ============================================================================
if [ "$SUBCMD" = "new" ]; then
    [ -n "$TARGET_DIR" ] || die "Usage: bootstrap.sh new <target-dir> [--version vX.Y.Z]"
    if [ -e "$TARGET_DIR" ] && [ -n "$(ls -A "$TARGET_DIR" 2>/dev/null)" ]; then
        die "Target '$TARGET_DIR' exists and is not empty. Use 'update' inside an existing vault."
    fi

    BARE="$(to_bare "${VERSION:-$(resolve_latest_tag)}")"
    [ -n "$BARE" ] || die "Could not resolve a version. Pass --version vX.Y.Z."
    header "Seed Vault — new vault @ $BARE$DRY_LABEL"

    SRC="$(fetch_framework "$BARE")"
    info "Framework source: $SRC"

    if $DRY_RUN; then
        info "Would install into: $TARGET_DIR"
        sync_manifest "$SRC" "$TARGET_DIR"
        info "[dry-run] would template + copy README.md (name: $(display_name "$TARGET_DIR"))"
        warn "DRY RUN — nothing written."; exit 0
    fi

    mkdir -p "$TARGET_DIR"
    TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"
    sync_manifest "$SRC" "$TARGET_DIR"

    # README is install-once + templated; never in the always-overwrite manifest.
    if [ -f "$SRC/README.md" ]; then
        NAME="$(display_name "$TARGET_DIR")"
        sed "s/Seed Vault/$NAME/g" "$SRC/README.md" > "$TARGET_DIR/README.md"
        info "Templated README.md → '$NAME'"
    fi

    # A vault is NOT the framework source — drop the marker if it tagged along.
    rm -f "$TARGET_DIR/.seed-vault-framework"

    echo "$BARE" > "$TARGET_DIR/.vault_version"
    ( cd "$TARGET_DIR" && bash _vault/install.sh )
    success "New vault ready at $TARGET_DIR (framework $BARE)"
    exit 0
fi

# ============================================================================
# Subcommand: update
# ============================================================================
if [ "$SUBCMD" = "update" ]; then
    VAULT="$(pwd)"
    [ -d "$VAULT/_vault" ] || die "Not a Seed Vault (no _vault/). cd into your vault first."
    if [ -f "$VAULT/.seed-vault-framework" ]; then
        die "This is the framework SOURCE repo, not a vault — refusing to self-update. Tag a release instead."
    fi

    BARE="$(to_bare "${VERSION:-$(resolve_latest_tag)}")"
    [ -n "$BARE" ] || die "Could not resolve a version. Pass --version vX.Y.Z."
    CUR="unknown"; [ -f "$VAULT/.vault_version" ] && CUR="$(tr -d '[:space:]' < "$VAULT/.vault_version")"
    [ "$CUR" = "unknown" ] && [ -f "$VAULT/wiki/.vault_version" ] && CUR="$(tr -d '[:space:]' < "$VAULT/wiki/.vault_version")"

    header "Seed Vault — update $CUR → $BARE$DRY_LABEL"

    SRC="$(fetch_framework "$BARE")"
    info "Syncing framework paths (manifest-scoped — content untouched)"
    sync_manifest "$SRC" "$VAULT"

    if $DRY_RUN; then warn "DRY RUN — nothing written, migrations/index skipped."; exit 0; fi

    info "Re-installing skills + deps"
    ( cd "$VAULT" && bash _vault/install.sh )
    # migrate.py reads the OLD vault version (root or legacy wiki/.vault_version), applies
    # pending migrations, and records progress — so it must run BEFORE we stamp the new
    # version. Then stamp root .vault_version authoritatively (covers the no-migration case).
    info "Applying content migrations"
    ( cd "$VAULT" && python3 _vault/migrate.py ) || warn "migrate.py reported an issue — review above."
    echo "$BARE" > "$VAULT/.vault_version"
    if command -v uv >/dev/null 2>&1 && [ -f "$VAULT/_vault/lib/index.py" ]; then
        info "Rebuilding index"
        ( cd "$VAULT" && uv run python _vault/lib/index.py --rebuild-qmd ) || warn "Index rebuild failed — run vault-index manually."
    fi
    success "Vault updated to framework $BARE"
    exit 0
fi
