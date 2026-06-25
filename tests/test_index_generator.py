"""Tests for _vault/lib/index.py build_index_text output."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VAULT_ROOT))

from _vault.lib import index  # noqa: E402


def test_index_begins_with_frontmatter():
    """_index.md must start with YAML frontmatter — CLAUDE.md rule applies."""
    text = index.build_index_text({}, today="2026-04-21")
    assert text.startswith("---\n"), f"expected frontmatter, got:\n{text[:80]}"
    # First --- block must close before the heading.
    _, fm_block, _rest = text.split("---", 2)
    assert 'title: "Wiki Index"' in fm_block
    assert "type: index" in fm_block
    assert "updated: 2026-04-21" in fm_block


def test_index_uses_aliased_wikilinks():
    groups = {
        "concept": [{"title": "Test Concept", "stem": "test-concept", "tags": ["a"], "status": "draft"}],
    }
    text = index.build_index_text(groups, today="2026-04-21")
    assert "[[test-concept|Test Concept]]" in text


def test_index_total_article_count_in_footer():
    groups = {
        "concept": [
            {"title": "A", "stem": "a", "tags": [], "status": "draft"},
            {"title": "B", "stem": "b", "tags": [], "status": "draft"},
        ],
    }
    text = index.build_index_text(groups, today="2026-04-21")
    assert "Total articles: 2" in text


def _fake_completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr=stderr)


def test_qmd_rebuild_tolerates_existing_collection(monkeypatch, capsys):
    """On update re-runs the 'vault' collection already exists; embed must still run."""
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["qmd", "collection", "add"]:
            return _fake_completed(
                cmd, returncode=1, stderr="Collection 'vault' already exists.\n"
            )
        return _fake_completed(cmd)

    monkeypatch.setattr(index.subprocess, "run", fake_run)
    index.run_qmd_rebuild(Path("wiki"))

    # add was attempted, the "already exists" error was swallowed, and embed ran.
    assert ["qmd", "embed"] in calls
    out = capsys.readouterr().out
    assert "already exists" in out
    assert "qmd rebuild complete." in out


def test_qmd_rebuild_aborts_on_unexpected_add_failure(monkeypatch, capsys):
    """A genuine add failure must NOT proceed to embed."""
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["qmd", "collection", "add"]:
            return _fake_completed(cmd, returncode=2, stderr="boom: disk full\n")
        return _fake_completed(cmd)

    monkeypatch.setattr(index.subprocess, "run", fake_run)
    index.run_qmd_rebuild(Path("wiki"))

    assert ["qmd", "embed"] not in calls
    err = capsys.readouterr().err
    assert "qmd collection add failed" in err
