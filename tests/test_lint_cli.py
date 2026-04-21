"""Smoke tests for _vault/lib/lint.py CLI behaviour."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

VAULT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VAULT_ROOT))

from _vault.lib import lint  # noqa: E402


def _result(check: str, severity: str, issues: list[str]) -> dict:
    return {"check": check, "severity": severity, "issues": issues, "auto_fixable": False}


def _run_main(argv: list[str], fake_results: list[dict]) -> int:
    with patch.object(sys, "argv", ["lint.py", *argv]), \
         patch.object(lint, "run_all_checks", return_value=fake_results):
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
