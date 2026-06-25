"""Behavioural tests for the framework installer (bootstrap.sh) and the
framework/content separation it guarantees.

These exercise bootstrap's own logic — manifest-scoped sync, README templating,
the framework-root guard, dry-run inertness, and content safety — without the
heavy side effects of the real _vault/install.sh. The framework source built per
test stubs install.sh to a no-op and omits _vault/lib so no `uv sync` or index
rebuild runs; migrate.py (stdlib-only) still runs for real.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

VAULT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = VAULT_ROOT / "_vault" / "manifest.txt"
BOOTSTRAP = VAULT_ROOT / "bootstrap.sh"
CONTENT_DIRS = ("wiki/", "raw/", "viz/", "outputs/")


def _manifest_paths() -> list[str]:
    out = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _build_src(dst: Path) -> Path:
    """Assemble a minimal, non-git framework source from the working tree."""
    dst.mkdir(parents=True)
    # README is templated by `new`; it is NOT a manifest path, so copy it explicitly.
    shutil.copy(VAULT_ROOT / "README.md", dst / "README.md")
    for rel in _manifest_paths():
        src = VAULT_ROOT / rel
        if not src.exists():
            continue
        tgt = dst / rel
        if src.is_dir():
            shutil.copytree(src, tgt, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, tgt)
    # Neutralise heavy steps: stub install.sh, drop lib/ so the index rebuild is skipped.
    (dst / "_vault" / "install.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    shutil.rmtree(dst / "_vault" / "lib", ignore_errors=True)
    return dst


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(BOOTSTRAP), *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def src(tmp_path: Path) -> Path:
    return _build_src(tmp_path / "fwsrc")


# ── Manifest contract: the structural guarantee behind "content is safe" ──────

def test_manifest_excludes_all_content_dirs():
    """Content dirs must never be framework-owned, or update could clobber notes."""
    paths = _manifest_paths()
    for content in CONTENT_DIRS:
        assert content not in paths, f"{content} must not be in the manifest (it is user content)"


def test_manifest_includes_core_framework_paths():
    paths = _manifest_paths()
    for core in ("_vault/", "_templates/", "CLAUDE.md"):
        assert core in paths, f"{core} should be framework-owned"


def test_manifest_includes_installer_so_it_self_updates():
    """bootstrap.sh must ship in the manifest, else vaults can never receive installer fixes."""
    assert "bootstrap.sh" in _manifest_paths()


def test_readme_not_in_manifest():
    """README is templated per-vault on `new`; force-overwriting it on update would wipe the title."""
    assert "README.md" not in _manifest_paths()


# ── new: fresh vault creation ─────────────────────────────────────────────────

def test_new_creates_vault_with_root_version_and_templated_readme(src, tmp_path):
    vault = tmp_path / "genomics-wiki"
    r = _run(["new", str(vault), "--version", "3.0.0", "--source-dir", str(src)])
    assert r.returncode == 0, r.stderr
    assert (vault / "_vault" / "manifest.txt").is_file()
    assert (vault / ".vault_version").read_text().strip() == "3.0.0"
    # README templated to the dir's display name; never carries the legacy version file location.
    assert "Genomics Wiki" in (vault / "README.md").read_text()
    assert not (vault / "wiki" / ".vault_version").exists()
    # The framework-source marker must not leak into an installed vault.
    assert not (vault / ".seed-vault-framework").exists()


def test_new_refuses_nonempty_target(src, tmp_path):
    vault = tmp_path / "occupied"
    vault.mkdir()
    (vault / "something").write_text("x")
    r = _run(["new", str(vault), "--version", "3.0.0", "--source-dir", str(src)])
    assert r.returncode != 0
    assert "not empty" in (r.stderr + r.stdout)


# ── update: content safety, the crown-jewel guarantee ─────────────────────────

def _make_vault(src: Path, vault: Path, version: str = "3.0.0") -> None:
    vault.mkdir(parents=True)
    for rel in _manifest_paths():
        s = src / rel
        if not s.exists():
            continue
        t = vault / rel
        if s.is_dir():
            shutil.copytree(s, t)
        else:
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(s, t)
    (vault / ".vault_version").write_text(version + "\n")


def test_update_leaves_content_byte_identical(src, tmp_path):
    vault = tmp_path / "vault"
    _make_vault(src, vault)
    foo = vault / "wiki" / "concepts" / "foo.md"
    bar = vault / "raw" / "bar.md"
    foo.parent.mkdir(parents=True)
    bar.parent.mkdir(parents=True)
    foo.write_text("---\ntitle: Foo\n---\n# do not touch\n")
    bar.write_text("raw source bytes\n")
    before = (_sha(foo), _sha(bar))

    r = _run(["update", "--version", "3.0.0", "--source-dir", str(src)], cwd=vault)
    assert r.returncode == 0, r.stderr
    assert (_sha(foo), _sha(bar)) == before, "update must not modify user content"
    assert (vault / "_vault" / "manifest.txt").is_file()


def test_update_holds_version_when_llm_migration_pending(src, tmp_path):
    """The 2.0.0→3.0.0 migration has a requires_llm step. After update, .vault_version
    must stay at 2.0.0 (held) — NOT jump to 3.0.0 — until vault-migrate finishes the
    manual step. Stamping 3.0.0 here is the bug that masks a half-finished update."""
    vault = tmp_path / "vault"
    _make_vault(src, vault, version="2.0.0")
    r = _run(["update", "--version", "3.0.0", "--source-dir", str(src)], cwd=vault)
    assert r.returncode == 0, r.stderr
    assert (vault / ".vault_version").read_text().strip() == "2.0.0", \
        "version must be held while a requires_llm migration is pending"
    assert "vault-migrate" in (r.stdout + r.stderr).lower(), "the pending step must be surfaced"


def test_rerun_update_resurfaces_pending_llm_migration(src, tmp_path):
    """Reported bug: once .vault_version reached the target, re-running update silently
    skipped the unfinished migration ('doesn't actually pull'). With the version held
    back, a second update must STILL flag the pending LLM step, not hide it."""
    vault = tmp_path / "vault"
    _make_vault(src, vault, version="2.0.0")
    _run(["update", "--version", "3.0.0", "--source-dir", str(src)], cwd=vault)
    r2 = _run(["update", "--version", "3.0.0", "--source-dir", str(src)], cwd=vault)
    assert r2.returncode == 0, r2.stderr
    assert (vault / ".vault_version").read_text().strip() == "2.0.0"
    assert "vault-migrate" in (r2.stdout + r2.stderr).lower()


def test_complete_flag_finalizes_version_after_llm_step(src, tmp_path):
    """vault-migrate calls `migrate.py --complete` after the manual step; only then
    does .vault_version advance to the framework version."""
    vault = tmp_path / "vault"
    _make_vault(src, vault, version="2.0.0")
    _run(["update", "--version", "3.0.0", "--source-dir", str(src)], cwd=vault)
    assert (vault / ".vault_version").read_text().strip() == "2.0.0"
    done = subprocess.run(
        ["python3", "_vault/migrate.py", "--complete"],
        cwd=str(vault), capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stderr
    assert (vault / ".vault_version").read_text().strip() == "3.0.0"


def test_update_refuses_in_framework_source_repo(src, tmp_path):
    """A dir bearing the .seed-vault-framework marker must refuse self-update."""
    vault = tmp_path / "vault"
    _make_vault(src, vault)
    (vault / ".seed-vault-framework").write_text("marker\n")
    r = _run(["update", "--version", "3.0.0", "--source-dir", str(src)], cwd=vault)
    assert r.returncode != 0
    assert "framework SOURCE repo" in (r.stderr + r.stdout)


def test_update_dry_run_writes_nothing(src, tmp_path):
    vault = tmp_path / "vault"
    _make_vault(src, vault)
    marker = vault / "_vault" / "VERSION"
    original = marker.read_text()
    # Corrupt a framework file; a dry-run must NOT restore/overwrite it.
    marker.write_text("9.9.9")
    r = _run(["update", "--version", "3.0.0", "--source-dir", str(src), "--dry-run"], cwd=vault)
    assert r.returncode == 0, r.stderr
    assert marker.read_text() == "9.9.9", "dry-run must not write framework files"
    marker.write_text(original)
