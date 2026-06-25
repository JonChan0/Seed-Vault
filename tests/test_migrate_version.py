"""Unit tests for vault-version detection in _vault/migrate.py.

The .vault_version file moved from wiki/.vault_version (pre-3.x) to the vault root.
read_vault_version() must prefer the root file, fall back to the legacy location,
and default to 0.0.0 when neither exists — this back-compat is what lets a legacy
vault be detected and migrated on its first `bootstrap.sh update`.
"""
from __future__ import annotations

import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VAULT_ROOT))

from _vault import migrate  # noqa: E402


def _patch_paths(monkeypatch, root_file: Path, legacy_file: Path):
    monkeypatch.setattr(migrate, "VAULT_VERSION_FILE", root_file)
    monkeypatch.setattr(migrate, "LEGACY_VAULT_VERSION_FILE", legacy_file)


def test_prefers_root_over_legacy(monkeypatch, tmp_path):
    root = tmp_path / ".vault_version"
    legacy = tmp_path / "wiki" / ".vault_version"
    legacy.parent.mkdir()
    root.write_text("3.0.0\n")
    legacy.write_text("2.0.0\n")
    _patch_paths(monkeypatch, root, legacy)
    assert migrate.read_vault_version() == "3.0.0"


def test_falls_back_to_legacy_when_root_absent(monkeypatch, tmp_path):
    root = tmp_path / ".vault_version"
    legacy = tmp_path / "wiki" / ".vault_version"
    legacy.parent.mkdir()
    legacy.write_text("2.0.0\n")
    _patch_paths(monkeypatch, root, legacy)
    assert migrate.read_vault_version() == "2.0.0", "legacy vaults must still be detected"


def test_defaults_to_baseline_when_neither_exists(monkeypatch, tmp_path):
    root = tmp_path / ".vault_version"
    legacy = tmp_path / "wiki" / ".vault_version"
    _patch_paths(monkeypatch, root, legacy)
    assert migrate.read_vault_version() == "0.0.0"


def test_write_targets_root_not_legacy(monkeypatch, tmp_path):
    root = tmp_path / ".vault_version"
    legacy = tmp_path / "wiki" / ".vault_version"
    legacy.parent.mkdir()
    legacy.write_text("2.0.0\n")
    _patch_paths(monkeypatch, root, legacy)
    migrate.write_vault_version("3.0.0", dry_run=False)
    assert root.read_text().strip() == "3.0.0"
    # Legacy file is left untouched (we don't delete user files); reads now prefer root.
    assert legacy.read_text().strip() == "2.0.0"
