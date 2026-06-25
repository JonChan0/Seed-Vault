"""Shared pytest fixtures and helpers for the Seed Vault test suite.

Two test modes are supported, because every engine resolves its vault via a
module-level constant computed at import time:

    VAULT_ROOT = Path(__file__).resolve().parent.parent.parent

1. **In-process** (fast, for unit tests): import the engine module and call
   ``point_engine(monkeypatch, module, vault)`` to repoint its ``VAULT_ROOT`` and
   every derived dir constant at a temporary dummy vault.

2. **Subprocess** (true black-box, for e2e + lint + migrate): copy the repo's
   ``_vault/`` into the dummy vault and run the engine script from there with
   ``run_engine`` / ``run_migrate``. NOTE: ``Path.resolve()`` follows symlinks, so
   the framework must be **copied**, never symlinked, or ``VAULT_ROOT`` would
   resolve back to the real repo.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# --- Locations --------------------------------------------------------------
TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
CLEAN_FIXTURE = FIXTURES_DIR / "clean"

# Make `from _vault.lib import <engine>` importable in test modules.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# --- Dummy vault construction ----------------------------------------------

def _populate_clean(vault_root: Path) -> None:
    """Copy the clean fixture mini-vault (raw/ + wiki/) into vault_root."""
    for sub in ("raw", "wiki"):
        src = CLEAN_FIXTURE / sub
        if src.exists():
            shutil.copytree(src, vault_root / sub)
    # Ensure the standard skeleton dirs exist even if a fixture omitted one.
    (vault_root / "raw").mkdir(exist_ok=True)
    (vault_root / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
    (vault_root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)


@pytest.fixture
def dummy_vault(tmp_path: Path) -> Path:
    """A temp vault populated from tests/fixtures/clean (raw/ + wiki/)."""
    _populate_clean(tmp_path)
    return tmp_path


@pytest.fixture
def empty_vault(tmp_path: Path) -> Path:
    """A temp vault with the dir skeleton but no articles."""
    (tmp_path / "raw").mkdir()
    (tmp_path / "wiki" / "concepts").mkdir(parents=True)
    (tmp_path / "wiki" / "sources").mkdir(parents=True)
    return tmp_path


# --- In-process repointing --------------------------------------------------

# Standard derived paths, keyed by the constant name engines use.
def _derived_paths(vault_root: Path) -> dict[str, Path]:
    return {
        "VAULT_ROOT": vault_root,
        "WIKI_DIR": vault_root / "wiki",
        "RAW_DIR": vault_root / "raw",
        "SOURCES_DIR": vault_root / "wiki" / "sources",
        "CONCEPTS_DIR": vault_root / "wiki" / "concepts",
        "INDEX_FILE": vault_root / "wiki" / "_index.md",
        "LOG_FILE": vault_root / "wiki" / "_log.md",
    }


def clear_lru_caches(module) -> None:
    """Clear every functools.lru_cache defined on a module (e.g. lint.py)."""
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and hasattr(obj, "cache_clear"):
            obj.cache_clear()


def point_engine(monkeypatch, module, vault_root: Path) -> None:
    """Repoint an engine module's path constants at vault_root (in-process).

    Sets VAULT_ROOT plus every derived dir constant the module actually defines,
    and clears any lru_caches so cached file reads from a prior vault don't leak.
    """
    for name, value in _derived_paths(vault_root).items():
        if hasattr(module, name):
            monkeypatch.setattr(module, name, value, raising=False)
    clear_lru_caches(module)


# --- Subprocess framework copy ----------------------------------------------

def copy_framework(vault_root: Path) -> None:
    """Copy the repo's _vault/ into vault_root (real files, not a symlink).

    Skill dirs (vault-*) and caches are skipped for speed — only the Python
    engines, migrate.py, migrations, and VERSION are needed to run the pipeline.
    """
    shutil.copytree(
        REPO_ROOT / "_vault",
        vault_root / "_vault",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "vault-*", "hooks"),
    )


@pytest.fixture
def subprocess_vault(dummy_vault: Path) -> Path:
    """A clean dummy vault with the framework copied in, ready for script runs."""
    copy_framework(dummy_vault)
    return dummy_vault


# --- Subprocess runners -----------------------------------------------------

def run_engine(vault_root: Path, engine: str, *args: str) -> subprocess.CompletedProcess:
    """Run `python <vault>/_vault/lib/<engine>.py <args>` with cwd=vault_root."""
    script = vault_root / "_vault" / "lib" / f"{engine}.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=vault_root,
        capture_output=True,
        text=True,
    )


def run_migrate(vault_root: Path, *args: str) -> subprocess.CompletedProcess:
    """Run `python <vault>/_vault/migrate.py <args>` with cwd=vault_root."""
    script = vault_root / "_vault" / "migrate.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=vault_root,
        capture_output=True,
        text=True,
    )


def engine_json(result: subprocess.CompletedProcess) -> object:
    """Parse the stdout of an engine run invoked with --json."""
    return json.loads(result.stdout)


# --- Small authoring helper -------------------------------------------------

def write_article(path: Path, frontmatter: dict, body: str = "") -> Path:
    """Write a markdown file with YAML frontmatter from a dict. For crafting
    one-off lint scenarios inline in tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            rendered = "[" + ", ".join(str(v) for v in value) + "]"
            lines.append(f"{key}: {rendered}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
