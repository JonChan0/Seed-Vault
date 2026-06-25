#!/usr/bin/env bash
# ============================================================
# Seed Vault — Framework Updater  [DEPRECATED SHIM]
#
# The old fork-merge updater (git fetch upstream && merge -X theirs && push)
# is gone. Updates now run through the version-pinned installer:
#
#     bootstrap.sh update [--version vX.Y.Z] [--dry-run]
#
# This file remains only so existing muscle memory / scripts keep working.
# It forwards to bootstrap.sh update. --no-push is accepted and ignored
# (update no longer pushes — content is local and untracked).
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "⚠ update_vault_framework.sh is deprecated — forwarding to: bootstrap.sh update" >&2
exec bash "$SCRIPT_DIR/bootstrap.sh" update "$@"
