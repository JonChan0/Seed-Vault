"""Tests for _vault/lib/lint.py CLI behaviour — subprocess only (lru_cache safety)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

VAULT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VAULT_ROOT))

from _vault.lib import lint  # noqa: E402

from conftest import (
    engine_json,
    run_engine,
    write_article,
)


# ---------------------------------------------------------------------------
# Legacy smoke tests (kept from original file)
# ---------------------------------------------------------------------------


def _result(check: str, severity: str, issues: list[str]) -> dict:
    return {"check": check, "severity": severity, "issues": issues, "auto_fixable": False}


def _run_main(argv: list[str], fake_results: list[dict]) -> int:
    with (
        patch.object(sys, "argv", ["lint.py", *argv]),
        patch.object(lint, "run_all_checks", return_value=fake_results),
    ):
        return lint.main()


def test_main_returns_1_when_error_issue_present():
    fake_results = [_result("broken_wikilinks", "error", ["wiki/x.md: broken [[Foo]]"])]
    assert _run_main([], fake_results) == 1


def test_main_returns_0_on_clean():
    fake_results = [_result("broken_wikilinks", "error", [])]
    assert _run_main([], fake_results) == 0


def test_summary_line_always_present_even_when_clean(capsys):
    fake_results = [
        _result("broken_wikilinks", "error", []),
        _result("orphan_pages", "warning", []),
        _result("tag_frequency", "info", []),
    ]
    _run_main([], fake_results)
    out = capsys.readouterr().out
    assert "Summary:" in out
    assert "0 error" in out
    assert "0 warning" in out
    assert "0 info" in out


def test_fix_backlinks_flag_removed():
    """Flag implementation deleted; CLI should reject the option."""
    try:
        _run_main(["--fix-backlinks"], [])
    except SystemExit as e:
        assert e.code == 2
        return
    raise AssertionError("--fix-backlinks should have been removed")


# ---------------------------------------------------------------------------
# Helper: run lint on a subprocess_vault and return results keyed by check name
# ---------------------------------------------------------------------------


def _lint_results(vault_root: Path) -> dict[str, dict]:
    result = run_engine(vault_root, "lint", "--json")
    checks = engine_json(result)
    return {c["check"]: c for c in checks}, result


# ---------------------------------------------------------------------------
# Check names and severities
# ---------------------------------------------------------------------------

_EXPECTED_CHECKS = {
    "broken_wikilinks": "error",
    "orphan_pages": "warning",
    "missing_backlinks": "warning",
    "stale_articles": "info",
    "index_sync": "warning",
    "raw_coverage": "info",
    "tag_frequency": "info",
}


def test_all_checks_present_in_output(subprocess_vault):
    """All 7 checks must appear in the JSON output with correct severities."""
    by_check, _ = _lint_results(subprocess_vault)
    for check_name, expected_severity in _EXPECTED_CHECKS.items():
        assert check_name in by_check, f"Check {check_name!r} missing from lint output"
        assert by_check[check_name]["severity"] == expected_severity, (
            f"{check_name}: expected severity {expected_severity!r}, "
            f"got {by_check[check_name]['severity']!r}"
        )


# ---------------------------------------------------------------------------
# 1. Clean vault passes all checks
# ---------------------------------------------------------------------------


def test_clean_vault_all_checks_pass(subprocess_vault):
    """After indexing, every check on the clean fixture returns issues==[]."""
    # Populate _index.md first (otherwise index_sync warns)
    idx_result = run_engine(subprocess_vault, "index", "--no-cleanup")
    assert idx_result.returncode == 0, f"index failed:\n{idx_result.stderr}"

    by_check, result = _lint_results(subprocess_vault)
    assert result.returncode == 0, f"lint returned non-zero:\n{result.stderr}"

    for check_name in _EXPECTED_CHECKS:
        issues = by_check[check_name]["issues"]
        assert issues == [], (
            f"Check {check_name!r} had unexpected issues on clean vault:\n"
            + "\n".join(f"  - {i}" for i in issues)
        )


# ---------------------------------------------------------------------------
# 2. broken_wikilinks fires on a dangling wikilink in body
# ---------------------------------------------------------------------------


def test_broken_wikilinks_fires(subprocess_vault):
    write_article(
        subprocess_vault / "wiki" / "concepts" / "dangling-link-article.md",
        {
            "title": "Dangling Link Article",
            "type": "concept",
            "created": "2026-06-25",
            "updated": "2026-06-25",
            "sources": ["[[summary-dummy-genome-project|Summary - Dummy Genome Project]]"],
            "tags": ["dummy/genomics"],
            "status": "draft",
            "llm_model": "claude-sonnet-4-6",
            "framework_version": "3.0.0",
        },
        body="This article references [[nonexistent-article]] which does not exist.",
    )
    by_check, result = _lint_results(subprocess_vault)
    assert by_check["broken_wikilinks"]["issues"], (
        "Expected broken_wikilinks issues for dangling [[nonexistent-article]]"
    )
    assert result.returncode == 1, (
        "Expected exit code 1 when broken_wikilinks has issues"
    )


# ---------------------------------------------------------------------------
# 3. raw/ links in frontmatter do NOT fire broken_wikilinks
# ---------------------------------------------------------------------------


def test_raw_links_not_flagged_as_broken(subprocess_vault):
    """Regression: raw/ wikilinks in frontmatter must not be reported as broken."""
    # The clean fixture already contains summary-dummy-genome-project.md with
    # original_source: "[[raw/dummy-genome-project|Dummy Genome Project]]"
    # which points at a real raw file. No broken link should be reported for it.
    by_check, _ = _lint_results(subprocess_vault)
    raw_issues = [
        issue
        for issue in by_check["broken_wikilinks"]["issues"]
        if "raw/" in issue
    ]
    assert raw_issues == [], (
        "broken_wikilinks should not flag valid raw/ links:\n"
        + "\n".join(f"  - {i}" for i in raw_issues)
    )


# ---------------------------------------------------------------------------
# 4. orphan_pages fires for an unlinked article
# ---------------------------------------------------------------------------


def test_orphan_pages_fires(subprocess_vault):
    # Article with no inbound links and no outbound links
    write_article(
        subprocess_vault / "wiki" / "concepts" / "totally-isolated-article.md",
        {
            "title": "Totally Isolated Article",
            "type": "concept",
            "created": "2026-06-25",
            "updated": "2026-06-25",
            "tags": ["dummy/isolated"],
            "status": "draft",
            "llm_model": "claude-sonnet-4-6",
            "framework_version": "3.0.0",
        },
        body="This article exists in isolation with no links to or from it.",
    )
    by_check, _ = _lint_results(subprocess_vault)
    orphan_issues = by_check["orphan_pages"]["issues"]
    assert any("totally-isolated-article" in issue for issue in orphan_issues), (
        f"Expected totally-isolated-article in orphan_pages issues, got: {orphan_issues}"
    )


# ---------------------------------------------------------------------------
# 5. missing_backlinks fires; _index.md NOT blamed
# ---------------------------------------------------------------------------


def test_missing_backlinks_fires(subprocess_vault):
    """Article A links to dummy-human-genome but dummy-human-genome doesn't link back."""
    write_article(
        subprocess_vault / "wiki" / "concepts" / "one-way-link-article.md",
        {
            "title": "One Way Link Article",
            "type": "concept",
            "created": "2026-06-25",
            "updated": "2026-06-25",
            "sources": ["[[summary-dummy-genome-project|Summary - Dummy Genome Project]]"],
            "tags": ["dummy/genomics"],
            "status": "draft",
            "llm_model": "claude-sonnet-4-6",
            "framework_version": "3.0.0",
        },
        body=(
            "This article links to [[dummy-human-genome|Dummy Human Genome]] "
            "but that article does not link back here."
        ),
    )
    by_check, _ = _lint_results(subprocess_vault)
    mb_issues = by_check["missing_backlinks"]["issues"]
    assert mb_issues, "Expected missing_backlinks issues for one-way link"

    # Regression: _index.md must never be cited as a backlink source
    index_blamed = [i for i in mb_issues if "_index.md" in i]
    assert index_blamed == [], (
        "missing_backlinks must not blame _index.md as a link source:\n"
        + "\n".join(f"  - {i}" for i in index_blamed)
    )


# ---------------------------------------------------------------------------
# 6. raw_coverage fires for an uncovered raw file
# ---------------------------------------------------------------------------


def test_raw_coverage_fires(subprocess_vault):
    # Drop a new raw file that no summary references
    orphan_raw = subprocess_vault / "raw" / "orphan-raw.md"
    orphan_raw.write_text(
        "---\ntitle: Orphan Raw\n---\nNo summary covers this file.\n",
        encoding="utf-8",
    )
    by_check, _ = _lint_results(subprocess_vault)
    rc_issues = by_check["raw_coverage"]["issues"]
    assert any("orphan-raw" in issue for issue in rc_issues), (
        f"Expected orphan-raw.md in raw_coverage issues, got: {rc_issues}"
    )


# ---------------------------------------------------------------------------
# 7. tag_frequency fires for a singleton tag
# ---------------------------------------------------------------------------


def test_tag_frequency_fires_for_singleton_tag(subprocess_vault):
    write_article(
        subprocess_vault / "wiki" / "concepts" / "singleton-tag-article.md",
        {
            "title": "Singleton Tag Article",
            "type": "concept",
            "created": "2026-06-25",
            "updated": "2026-06-25",
            "sources": ["[[summary-dummy-genome-project|Summary - Dummy Genome Project]]"],
            "tags": ["dummy/genomics", "unique/singleton-xyz-tag"],
            "status": "draft",
            "llm_model": "claude-sonnet-4-6",
            "framework_version": "3.0.0",
        },
        body=(
            "This article has a unique singleton tag used nowhere else.\n\n"
            "## See Also\n\n- [[dummy-human-genome|Dummy Human Genome]]"
        ),
    )
    by_check, _ = _lint_results(subprocess_vault)
    tf_issues = by_check["tag_frequency"]["issues"]
    assert any("singleton-xyz-tag" in issue for issue in tf_issues), (
        f"Expected singleton-xyz-tag in tag_frequency issues, got: {tf_issues}"
    )


# ---------------------------------------------------------------------------
# 8. index_sync: missing → fires; after index run → clear
# ---------------------------------------------------------------------------


def test_index_sync_fires_when_index_missing(subprocess_vault):
    """index_sync should warn when _index.md does not exist."""
    index_file = subprocess_vault / "wiki" / "_index.md"
    if index_file.exists():
        index_file.unlink()

    by_check, _ = _lint_results(subprocess_vault)
    is_issues = by_check["index_sync"]["issues"]
    assert is_issues, "Expected index_sync to warn when _index.md is absent"
    assert any("_index.md" in issue for issue in is_issues), (
        f"Expected _index.md mention in index_sync issues, got: {is_issues}"
    )


def test_index_sync_clears_after_rebuild(subprocess_vault):
    """After running index --no-cleanup, index_sync issues should be empty."""
    idx_result = run_engine(subprocess_vault, "index", "--no-cleanup")
    assert idx_result.returncode == 0, f"index failed:\n{idx_result.stderr}"

    by_check, _ = _lint_results(subprocess_vault)
    is_issues = by_check["index_sync"]["issues"]
    assert is_issues == [], (
        f"Expected no index_sync issues after index rebuild, got: {is_issues}"
    )
