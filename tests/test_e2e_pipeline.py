"""
End-to-end tests for the Seed Vault pipeline engines.

Drives the full pipeline on the clean fixture vault (2 raw files,
2 concept articles, 2 source summaries).  Uses the subprocess_vault
fixture so every engine resolves VAULT_ROOT to the temp directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import (
    engine_json,
    run_engine,
)

# ---------------------------------------------------------------------------
# qmd availability guard
# ---------------------------------------------------------------------------

_QMD_AVAILABLE = shutil.which("qmd") is not None

requires_qmd = pytest.mark.skipif(
    not _QMD_AVAILABLE,
    reason="qmd is not installed in this environment",
)


# ---------------------------------------------------------------------------
# Stage 1 — Pipeline detection
# ---------------------------------------------------------------------------

class TestPipelineDetect:
    """pipeline.py --json: detect raw files and produce a manifest."""

    def test_pipeline_detect_returncode(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "pipeline", "--json")
        assert result.returncode == 0, (
            f"pipeline --json exited {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_pipeline_detect_stats_keys_present(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "pipeline", "--json")
        manifest = engine_json(result)
        stats = manifest.get("stats")
        assert isinstance(stats, dict), f"Expected 'stats' dict in manifest, got: {manifest}"
        for key in ("total_raw", "new", "updated", "unchanged"):
            assert key in stats, f"Missing key '{key}' in stats: {stats}"

    def test_pipeline_detect_total_raw(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "pipeline", "--json")
        manifest = engine_json(result)
        assert manifest["stats"]["total_raw"] == 2, (
            f"Expected total_raw == 2, got {manifest['stats']['total_raw']}"
        )


# ---------------------------------------------------------------------------
# Stage 2 — Index generation (non-qmd variant always runs)
# ---------------------------------------------------------------------------

class TestIndexNonQmd:
    """index.py --no-cleanup: write _index.md without touching qmd."""

    def test_index_no_cleanup_returncode(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "index", "--no-cleanup")
        assert result.returncode == 0, (
            f"index --no-cleanup exited {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_index_no_cleanup_writes_file(self, subprocess_vault: Path) -> None:
        run_engine(subprocess_vault, "index", "--no-cleanup")
        assert (subprocess_vault / "wiki" / "_index.md").exists()

    def test_index_no_cleanup_total(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "index", "--no-cleanup")
        assert "Total: 4" in result.stdout, (
            f"Expected 'Total: 4' in stdout.\nstdout: {result.stdout}"
        )

    def test_index_no_cleanup_aliased_links(self, subprocess_vault: Path) -> None:
        run_engine(subprocess_vault, "index", "--no-cleanup")
        index_text = (subprocess_vault / "wiki" / "_index.md").read_text(encoding="utf-8")
        expected_links = [
            "[[dummy-human-genome|Dummy Human Genome]]",
            "[[dummy-gene-editing|Dummy Gene Editing]]",
            "[[summary-dummy-crispr|Summary - Dummy CRISPR Notes]]",
            "[[summary-dummy-genome-project|Summary - Dummy Genome Project]]",
        ]
        for link in expected_links:
            assert link in index_text, (
                f"Expected aliased link {link!r} not found in _index.md.\n"
                f"_index.md contents:\n{index_text}"
            )


# ---------------------------------------------------------------------------
# Stage 2 (qmd variant) — Index generation with qmd rebuild
# ---------------------------------------------------------------------------

@requires_qmd
class TestIndexWithQmd:
    """index.py --rebuild-qmd: write _index.md and rebuild the qmd collection."""

    def test_index_rebuild_qmd_returncode(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "index", "--rebuild-qmd")
        assert result.returncode == 0, (
            f"index --rebuild-qmd exited {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_index_rebuild_qmd_writes_file(self, subprocess_vault: Path) -> None:
        run_engine(subprocess_vault, "index", "--rebuild-qmd")
        assert (subprocess_vault / "wiki" / "_index.md").exists()

    def test_index_rebuild_qmd_total(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "index", "--rebuild-qmd")
        assert "Total: 4" in result.stdout, (
            f"Expected 'Total: 4' in stdout.\nstdout: {result.stdout}"
        )

    def test_index_rebuild_qmd_completion_message(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "index", "--rebuild-qmd")
        assert "qmd rebuild complete." in result.stdout, (
            f"Expected 'qmd rebuild complete.' in stdout.\nstdout: {result.stdout}"
        )

    def test_index_rebuild_qmd_aliased_links(self, subprocess_vault: Path) -> None:
        run_engine(subprocess_vault, "index", "--rebuild-qmd")
        index_text = (subprocess_vault / "wiki" / "_index.md").read_text(encoding="utf-8")
        expected_links = [
            "[[dummy-human-genome|Dummy Human Genome]]",
            "[[dummy-gene-editing|Dummy Gene Editing]]",
            "[[summary-dummy-crispr|Summary - Dummy CRISPR Notes]]",
            "[[summary-dummy-genome-project|Summary - Dummy Genome Project]]",
        ]
        for link in expected_links:
            assert link in index_text, (
                f"Expected aliased link {link!r} not found in _index.md.\n"
                f"_index.md contents:\n{index_text}"
            )


# ---------------------------------------------------------------------------
# Stage 3 — Verify
# ---------------------------------------------------------------------------

class TestVerify:
    """verify.py: claim extraction and source matching for dummy-human-genome."""

    def test_verify_returncode(self, subprocess_vault: Path) -> None:
        result = run_engine(
            subprocess_vault,
            "verify",
            "wiki/concepts/dummy-human-genome.md",
            "--json",
        )
        assert result.returncode == 0, (
            f"verify exited {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_verify_claims_found(self, subprocess_vault: Path) -> None:
        result = run_engine(
            subprocess_vault,
            "verify",
            "wiki/concepts/dummy-human-genome.md",
            "--json",
        )
        report = engine_json(result)
        assert report["claims_found"] == 6, (
            f"Expected claims_found == 6, got {report['claims_found']}"
        )

    def test_verify_exact_matches(self, subprocess_vault: Path) -> None:
        result = run_engine(
            subprocess_vault,
            "verify",
            "wiki/concepts/dummy-human-genome.md",
            "--json",
        )
        report = engine_json(result)
        assert report["summary"]["exact_matches"] == 5, (
            f"Expected exact_matches == 5, got {report['summary']['exact_matches']}"
        )

    def test_verify_unmatched_claims(self, subprocess_vault: Path) -> None:
        result = run_engine(
            subprocess_vault,
            "verify",
            "wiki/concepts/dummy-human-genome.md",
            "--json",
        )
        report = engine_json(result)
        assert report["summary"]["unmatched_claims"] == 1, (
            f"Expected unmatched_claims == 1, got {report['summary']['unmatched_claims']}"
        )

    def test_verify_confidence(self, subprocess_vault: Path) -> None:
        result = run_engine(
            subprocess_vault,
            "verify",
            "wiki/concepts/dummy-human-genome.md",
            "--json",
        )
        report = engine_json(result)
        assert report["summary"]["confidence"] == "HIGH", (
            f"Expected confidence == 'HIGH', got {report['summary']['confidence']!r}"
        )


# ---------------------------------------------------------------------------
# Stage 4 — Lint (requires index to be built first)
# ---------------------------------------------------------------------------

class TestLint:
    """lint.py --json: structural checks on the clean fixture vault."""

    def _build_index(self, vault: Path) -> None:
        """Build the index so index_sync check passes."""
        result = run_engine(vault, "index", "--no-cleanup")
        assert result.returncode == 0, (
            f"index --no-cleanup failed before lint.\nstderr: {result.stderr}"
        )

    def test_lint_returncode(self, subprocess_vault: Path) -> None:
        self._build_index(subprocess_vault)
        result = run_engine(subprocess_vault, "lint", "--json")
        assert result.returncode == 0, (
            f"lint exited {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_lint_broken_wikilinks_empty(self, subprocess_vault: Path) -> None:
        self._build_index(subprocess_vault)
        result = run_engine(subprocess_vault, "lint", "--json")
        checks = engine_json(result)
        broken = next(
            (c for c in checks if c["check"] == "broken_wikilinks"), None
        )
        assert broken is not None, "broken_wikilinks check not found in lint output"
        assert broken["issues"] == [], (
            f"Expected broken_wikilinks issues == [], got: {broken['issues']}"
        )

    def test_lint_all_checks_empty(self, subprocess_vault: Path) -> None:
        """On the clean fixture all seven checks should produce no issues."""
        self._build_index(subprocess_vault)
        result = run_engine(subprocess_vault, "lint", "--json")
        checks = engine_json(result)
        for check in checks:
            assert check["issues"] == [], (
                f"Check '{check['check']}' unexpectedly has issues: {check['issues']}"
            )


# ---------------------------------------------------------------------------
# Stage 5 — Digest
# ---------------------------------------------------------------------------

class TestDigest:
    """digest.py --json: vault statistics on the clean fixture."""

    def test_digest_returncode(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "digest", "--json")
        assert result.returncode == 0, (
            f"digest --json exited {result.returncode}\n"
            f"stderr: {result.stderr}"
        )

    def test_digest_total(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "digest", "--json")
        stats = engine_json(result)
        assert stats["total"] == 4, (
            f"Expected total == 4, got {stats['total']}"
        )

    def test_digest_type_counts(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "digest", "--json")
        stats = engine_json(result)
        assert stats["type_counts"] == {"concept": 2, "source-summary": 2}, (
            f"Unexpected type_counts: {stats['type_counts']}"
        )

    def test_digest_no_orphans(self, subprocess_vault: Path) -> None:
        result = run_engine(subprocess_vault, "digest", "--json")
        stats = engine_json(result)
        assert stats["orphans"] == [], (
            f"Expected no orphans, got: {stats['orphans']}"
        )
