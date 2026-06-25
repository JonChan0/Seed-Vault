"""
End-to-end tests for the Seed Vault migration runner (_vault/migrate.py).

Tests the full update / migrate path including:
  - Simple forward migration (no LLM step)
  - Dry-run writes nothing
  - requires_llm hold-back and --complete finalization
  - Already-current vault (no migrations needed)

Uses subprocess_vault so migrate.py resolves paths to the temp vault.
"""

from __future__ import annotations

from pathlib import Path


from conftest import (
    run_migrate,
    write_article,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_vault_version(vault: Path, version: str) -> None:
    """Write .vault_version at vault root."""
    (vault / ".vault_version").write_text(version + "\n", encoding="utf-8")


def _read_vault_version(vault: Path) -> str:
    """Read .vault_version from vault root, return stripped string."""
    return (vault / ".vault_version").read_text(encoding="utf-8").strip()


def _set_framework_version(vault: Path, version: str) -> None:
    """Overwrite _vault/VERSION to the given version string."""
    (vault / "_vault" / "VERSION").write_text(version + "\n", encoding="utf-8")


def _make_article(vault: Path, name: str, framework_version: str) -> Path:
    """Create a minimal wiki article at the given framework_version."""
    path = vault / "wiki" / "concepts" / f"{name}.md"
    return write_article(
        path,
        frontmatter={
            "title": f'"{name.replace("-", " ").title()}"',
            "type": "concept",
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "sources": [],
            "tags": ["test"],
            "status": "draft",
            "llm_model": '"claude-sonnet-4-6"',
            "framework_version": f'"{framework_version}"',
        },
        body="# Body\n\nTest article body.",
    )


def _get_framework_version_in_file(path: Path) -> str:
    """Read the framework_version field from an article's frontmatter."""
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("framework_version"):
            _, _, value = line.partition(":")
            return value.strip().strip('"\'')
    raise AssertionError(f"framework_version field not found in {path}")


# ---------------------------------------------------------------------------
# Test 1: Simple forward migration (no LLM)
# ---------------------------------------------------------------------------

class TestSimpleForwardMigration:
    """1.0.0 → 2.0.0 via the shipped 1.0.0-to-2.0.0.json (requires_llm: false)."""

    def test_returncode(self, subprocess_vault: Path) -> None:
        _set_framework_version(subprocess_vault, "2.0.0")
        _write_vault_version(subprocess_vault, "1.0.0")
        _make_article(subprocess_vault, "article-one", "1.0.0")
        _make_article(subprocess_vault, "article-two", "1.0.0")

        result = run_migrate(subprocess_vault)
        assert result.returncode == 0, (
            f"migrate exited {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    def test_vault_version_bumped(self, subprocess_vault: Path) -> None:
        _set_framework_version(subprocess_vault, "2.0.0")
        _write_vault_version(subprocess_vault, "1.0.0")
        _make_article(subprocess_vault, "article-one", "1.0.0")
        _make_article(subprocess_vault, "article-two", "1.0.0")

        run_migrate(subprocess_vault)
        assert _read_vault_version(subprocess_vault) == "2.0.0", (
            f".vault_version should be '2.0.0' after migration, "
            f"got {_read_vault_version(subprocess_vault)!r}"
        )

    def test_article_framework_version_updated(self, subprocess_vault: Path) -> None:
        _set_framework_version(subprocess_vault, "2.0.0")
        _write_vault_version(subprocess_vault, "1.0.0")
        art1 = _make_article(subprocess_vault, "article-one", "1.0.0")
        art2 = _make_article(subprocess_vault, "article-two", "1.0.0")

        run_migrate(subprocess_vault)
        for path in (art1, art2):
            fv = _get_framework_version_in_file(path)
            assert fv == "2.0.0", (
                f"Expected framework_version '2.0.0' in {path.name}, got {fv!r}"
            )

    def test_migration_log_created(self, subprocess_vault: Path) -> None:
        _set_framework_version(subprocess_vault, "2.0.0")
        _write_vault_version(subprocess_vault, "1.0.0")
        _make_article(subprocess_vault, "article-one", "1.0.0")

        run_migrate(subprocess_vault)
        log_path = subprocess_vault / "wiki" / "_migration-log.md"
        assert log_path.exists(), "_migration-log.md was not created"
        log_text = log_path.read_text(encoding="utf-8")
        # Log should contain a table row for this migration
        assert "1.0.0" in log_text and "2.0.0" in log_text, (
            f"Migration log does not contain expected version row.\n"
            f"Log contents:\n{log_text}"
        )


# ---------------------------------------------------------------------------
# Test 2: Dry-run writes nothing
# ---------------------------------------------------------------------------

class TestDryRun:
    """--dry-run must not write any files and must mention DRY RUN in output."""

    def test_dry_run_returncode(self, subprocess_vault: Path) -> None:
        _set_framework_version(subprocess_vault, "2.0.0")
        # No .vault_version → defaults to 0.0.0
        _make_article(subprocess_vault, "article-alpha", "1.0.0")

        result = run_migrate(subprocess_vault, "--dry-run")
        assert result.returncode == 0, (
            f"migrate --dry-run exited {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_dry_run_mentions_dry_run(self, subprocess_vault: Path) -> None:
        _set_framework_version(subprocess_vault, "2.0.0")
        _make_article(subprocess_vault, "article-alpha", "1.0.0")

        result = run_migrate(subprocess_vault, "--dry-run")
        assert "DRY RUN" in result.stdout, (
            f"Expected 'DRY RUN' in stdout.\nstdout: {result.stdout}"
        )

    def test_dry_run_vault_version_absent(self, subprocess_vault: Path) -> None:
        """With no .vault_version pre-existing, dry-run must not create it."""
        _set_framework_version(subprocess_vault, "2.0.0")
        _make_article(subprocess_vault, "article-alpha", "1.0.0")

        version_file = subprocess_vault / ".vault_version"
        assert not version_file.exists(), "Pre-condition: .vault_version should not exist"

        run_migrate(subprocess_vault, "--dry-run")
        assert not version_file.exists(), (
            ".vault_version must not be created by --dry-run"
        )

    def test_dry_run_article_unchanged(self, subprocess_vault: Path) -> None:
        _set_framework_version(subprocess_vault, "2.0.0")
        art = _make_article(subprocess_vault, "article-alpha", "1.0.0")
        original = art.read_text(encoding="utf-8")

        run_migrate(subprocess_vault, "--dry-run")
        after = art.read_text(encoding="utf-8")
        assert original == after, (
            f"Article content changed during --dry-run.\n"
            f"Before:\n{original}\n\nAfter:\n{after}"
        )

    def test_dry_run_no_migration_log(self, subprocess_vault: Path) -> None:
        _set_framework_version(subprocess_vault, "2.0.0")
        _make_article(subprocess_vault, "article-alpha", "1.0.0")

        run_migrate(subprocess_vault, "--dry-run")
        log_path = subprocess_vault / "wiki" / "_migration-log.md"
        assert not log_path.exists(), (
            "_migration-log.md must not be created by --dry-run"
        )


# ---------------------------------------------------------------------------
# Test 3: requires_llm hold-back + --complete
# ---------------------------------------------------------------------------

class TestRequiresLlmHoldback:
    """2.0.0 → 3.0.0 migration has requires_llm: true — version must be held back."""

    def test_holdback_returncode(self, subprocess_vault: Path) -> None:
        # framework is already 3.0.0 by default; just set vault to 2.0.0
        _write_vault_version(subprocess_vault, "2.0.0")
        _make_article(subprocess_vault, "article-beta", "2.0.0")

        result = run_migrate(subprocess_vault)
        assert result.returncode == 0, (
            f"migrate exited {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_holdback_stdout_mentions_llm(self, subprocess_vault: Path) -> None:
        _write_vault_version(subprocess_vault, "2.0.0")
        _make_article(subprocess_vault, "article-beta", "2.0.0")

        result = run_migrate(subprocess_vault)
        stdout = result.stdout
        # The output should mention that a manual/semantic/LLM step is required
        has_require = "require" in stdout.lower()
        has_llm_ref = any(
            word in stdout
            for word in ("LLM", "semantic", "vault-migrate", "manual")
        )
        assert has_require and has_llm_ref, (
            f"stdout should mention a required LLM/semantic step.\n"
            f"stdout: {stdout}"
        )

    def test_holdback_vault_version_not_advanced(self, subprocess_vault: Path) -> None:
        _write_vault_version(subprocess_vault, "2.0.0")
        _make_article(subprocess_vault, "article-beta", "2.0.0")

        run_migrate(subprocess_vault)
        version = _read_vault_version(subprocess_vault)
        assert version == "2.0.0", (
            f".vault_version should remain '2.0.0' (held back), got {version!r}"
        )

    def test_complete_advances_version(self, subprocess_vault: Path) -> None:
        _write_vault_version(subprocess_vault, "2.0.0")
        _make_article(subprocess_vault, "article-beta", "2.0.0")

        # First: regular run that holds back
        run_migrate(subprocess_vault)
        assert _read_vault_version(subprocess_vault) == "2.0.0"

        # Then: --complete to finalize
        result = run_migrate(subprocess_vault, "--complete")
        assert result.returncode == 0, (
            f"migrate --complete exited {result.returncode}\n"
            f"stderr: {result.stderr}"
        )
        version = _read_vault_version(subprocess_vault)
        assert version == "3.0.0", (
            f"After --complete, .vault_version should be '3.0.0', got {version!r}"
        )


# ---------------------------------------------------------------------------
# Test 4: Already current
# ---------------------------------------------------------------------------

class TestAlreadyCurrent:
    """When .vault_version == _vault/VERSION, no migrations should run."""

    def test_already_current_returncode(self, subprocess_vault: Path) -> None:
        # Default _vault/VERSION is 3.0.0; write matching .vault_version
        _write_vault_version(subprocess_vault, "3.0.0")

        result = run_migrate(subprocess_vault)
        assert result.returncode == 0, (
            f"migrate exited {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_already_current_stdout_says_current(self, subprocess_vault: Path) -> None:
        _write_vault_version(subprocess_vault, "3.0.0")

        result = run_migrate(subprocess_vault)
        stdout = result.stdout.lower()
        assert "current" in stdout or "no migrations" in stdout, (
            f"Expected 'current' or 'no migrations' in stdout.\n"
            f"stdout: {result.stdout}"
        )

    def test_already_current_no_log_written(self, subprocess_vault: Path) -> None:
        _write_vault_version(subprocess_vault, "3.0.0")

        run_migrate(subprocess_vault)
        log_path = subprocess_vault / "wiki" / "_migration-log.md"
        assert not log_path.exists(), (
            "_migration-log.md should not be written when vault is already current"
        )
