"""Unit tests for _vault/lib/pipeline.py (in-process)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

# Import the engine module
from _vault.lib import pipeline

# Import conftest helpers
from conftest import point_engine, write_article


# ---------------------------------------------------------------------------
# scan_raw
# ---------------------------------------------------------------------------

class TestScanRaw:
    def test_returns_empty_for_missing_dir(self, tmp_path):
        result = pipeline.scan_raw(tmp_path / "nonexistent")
        assert result == []

    def test_returns_files_in_raw_dir(self, tmp_path):
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "file-a.md").write_text("hello")
        (raw / "file-b.pdf").write_text("pdf")
        result = pipeline.scan_raw(raw)
        assert len(result) == 2
        assert all(p.is_file() for p in result)

    def test_is_sorted(self, tmp_path):
        raw = tmp_path / "raw"
        raw.mkdir()
        for name in ["zzz.md", "aaa.md", "mmm.md"]:
            (raw / name).write_text("x")
        result = pipeline.scan_raw(raw)
        names = [p.name for p in result]
        assert names == sorted(names)

    def test_excludes_subdirectories(self, tmp_path):
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "file.md").write_text("x")
        (raw / "subdir").mkdir()
        result = pipeline.scan_raw(raw)
        assert len(result) == 1
        assert result[0].name == "file.md"


# ---------------------------------------------------------------------------
# needs_conversion
# ---------------------------------------------------------------------------

class TestNeedsConversion:
    @pytest.mark.parametrize("ext", [".md", ".txt"])
    def test_passthrough_extensions(self, tmp_path, ext):
        p = tmp_path / f"file{ext}"
        p.write_text("x")
        assert pipeline.needs_conversion(p) is False

    @pytest.mark.parametrize("ext", [".pdf", ".html", ".docx", ".epub"])
    def test_conversion_extensions(self, tmp_path, ext):
        p = tmp_path / f"file{ext}"
        p.write_text("x")
        assert pipeline.needs_conversion(p) is True

    def test_case_insensitive(self, tmp_path):
        p = tmp_path / "file.PDF"
        p.write_text("x")
        assert pipeline.needs_conversion(p) is True


# ---------------------------------------------------------------------------
# classify_files — controlled mtime scenario
# ---------------------------------------------------------------------------

class TestClassifyFiles:
    def _setup_vault(self, vault_root: Path):
        """Create raw/ and wiki/sources/ directories under vault_root."""
        (vault_root / "raw").mkdir(exist_ok=True)
        (vault_root / "wiki" / "sources").mkdir(parents=True, exist_ok=True)

    def test_new_no_summary(self, monkeypatch, empty_vault):
        """A raw file with no matching summary is classified as 'new'."""
        point_engine(monkeypatch, pipeline, empty_vault)

        raw = empty_vault / "raw" / "new-topic.md"
        raw.write_text("body")

        result = pipeline.classify_files([raw])
        assert len(result["new"]) == 1
        assert result["updated"] == []
        assert result["unchanged"] == []
        assert "raw/new-topic.md" in result["new"][0]["raw"]

    def test_updated_raw_newer_than_summary(self, monkeypatch, empty_vault):
        """A raw file newer than its summary is classified as 'updated'."""
        point_engine(monkeypatch, pipeline, empty_vault)

        raw = empty_vault / "raw" / "updated-topic.md"
        raw.write_text("body")

        summary = empty_vault / "wiki" / "sources" / "summary-updated-topic.md"
        write_article(summary, {"title": "Updated Topic", "type": "source-summary",
                                "created": "2026-01-01", "updated": "2026-01-01",
                                "sources": [], "tags": [], "status": "draft"})

        # Raw is newer: set summary mtime to past, raw mtime to present+1
        past = time.time() - 100
        now = time.time() + 1
        os.utime(summary, (past, past))
        os.utime(raw, (now, now))

        result = pipeline.classify_files([raw])
        assert len(result["updated"]) == 1
        assert result["new"] == []
        assert result["unchanged"] == []

    def test_unchanged_summary_newer_than_raw(self, monkeypatch, empty_vault):
        """A raw file older than its summary is classified as 'unchanged'."""
        point_engine(monkeypatch, pipeline, empty_vault)

        raw = empty_vault / "raw" / "old-topic.md"
        raw.write_text("body")

        summary = empty_vault / "wiki" / "sources" / "summary-old-topic.md"
        write_article(summary, {"title": "Old Topic", "type": "source-summary",
                                "created": "2026-01-01", "updated": "2026-01-01",
                                "sources": [], "tags": [], "status": "draft"})

        # Summary is newer
        past = time.time() - 100
        future = time.time() + 100
        os.utime(raw, (past, past))
        os.utime(summary, (future, future))

        result = pipeline.classify_files([raw])
        assert result["new"] == []
        assert result["updated"] == []
        assert len(result["unchanged"]) == 1

    def test_all_three_buckets(self, monkeypatch, empty_vault):
        """Three raw files cover new/updated/unchanged simultaneously."""
        point_engine(monkeypatch, pipeline, empty_vault)

        raw_dir = empty_vault / "raw"
        sources_dir = empty_vault / "wiki" / "sources"
        past = time.time() - 200
        now_ts = time.time()

        # New: no summary at all
        r_new = raw_dir / "brand-new.md"
        r_new.write_text("new")

        # Updated: raw is newer
        r_updated = raw_dir / "stale-summary.md"
        r_updated.write_text("updated")
        s_updated = sources_dir / "summary-stale-summary.md"
        write_article(s_updated, {"title": "T", "type": "source-summary",
                                  "created": "2026-01-01", "updated": "2026-01-01",
                                  "sources": [], "tags": [], "status": "draft"})
        os.utime(s_updated, (past, past))
        os.utime(r_updated, (now_ts + 50, now_ts + 50))

        # Unchanged: summary is newer
        r_unchanged = raw_dir / "fresh-summary.md"
        r_unchanged.write_text("unchanged")
        s_unchanged = sources_dir / "summary-fresh-summary.md"
        write_article(s_unchanged, {"title": "T2", "type": "source-summary",
                                    "created": "2026-01-01", "updated": "2026-01-01",
                                    "sources": [], "tags": [], "status": "draft"})
        os.utime(r_unchanged, (past, past))
        os.utime(s_unchanged, (now_ts + 100, now_ts + 100))

        result = pipeline.classify_files([r_new, r_updated, r_unchanged])
        assert len(result["new"]) == 1
        assert len(result["updated"]) == 1
        assert len(result["unchanged"]) == 1

    def test_new_pdf_has_needs_conversion_flag(self, monkeypatch, empty_vault):
        """A new PDF file gets needs_conversion=True in its entry."""
        point_engine(monkeypatch, pipeline, empty_vault)

        raw = empty_vault / "raw" / "report.pdf"
        raw.write_text("pdf content")

        result = pipeline.classify_files([raw])
        assert len(result["new"]) == 1
        assert result["new"][0].get("needs_conversion") is True

    def test_new_md_has_no_needs_conversion_flag(self, monkeypatch, empty_vault):
        """A new .md file does NOT get needs_conversion in its entry."""
        point_engine(monkeypatch, pipeline, empty_vault)

        raw = empty_vault / "raw" / "article.md"
        raw.write_text("content")

        result = pipeline.classify_files([raw])
        assert len(result["new"]) == 1
        assert "needs_conversion" not in result["new"][0]


# ---------------------------------------------------------------------------
# build_manifest
# ---------------------------------------------------------------------------

class TestBuildManifest:
    def test_stats_math(self):
        classified = {
            "new": [{"raw": "raw/a.pdf", "needs_conversion": True},
                    {"raw": "raw/b.md"}],
            "updated": [{"raw": "raw/c.md", "summary": "wiki/sources/summary-c.md"}],
            "unchanged": [{"raw": "raw/d.md", "summary": "wiki/sources/summary-d.md"},
                          {"raw": "raw/e.md", "summary": "wiki/sources/summary-e.md"}],
        }
        manifest = pipeline.build_manifest(classified)
        stats = manifest["stats"]
        assert stats["total_raw"] == 5
        assert stats["new"] == 2
        assert stats["updated"] == 1
        assert stats["unchanged"] == 2

    def test_manifest_has_timestamp(self):
        classified = {"new": [], "updated": [], "unchanged": []}
        manifest = pipeline.build_manifest(classified)
        assert "timestamp" in manifest
        # Should look like ISO format
        assert "T" in manifest["timestamp"]

    def test_manifest_preserves_entries(self):
        entry = {"raw": "raw/x.md"}
        classified = {"new": [entry], "updated": [], "unchanged": []}
        manifest = pipeline.build_manifest(classified)
        assert manifest["new"] == [entry]


# ---------------------------------------------------------------------------
# format_human
# ---------------------------------------------------------------------------

class TestFormatHuman:
    def test_returns_string(self):
        classified = {"new": [], "updated": [], "unchanged": []}
        manifest = pipeline.build_manifest(classified)
        result = pipeline.format_human(manifest)
        assert isinstance(result, str)

    def test_contains_counts(self):
        classified = {
            "new": [{"raw": "raw/a.md"}],
            "updated": [],
            "unchanged": [{"raw": "raw/b.md", "summary": "wiki/sources/summary-b.md"}],
        }
        manifest = pipeline.build_manifest(classified)
        text = pipeline.format_human(manifest)
        # Stats numbers should appear somewhere in the output
        assert "1" in text
        assert "2" in text  # total_raw

    def test_mentions_new_none_when_empty(self):
        classified = {"new": [], "updated": [], "unchanged": []}
        manifest = pipeline.build_manifest(classified)
        text = pipeline.format_human(manifest)
        assert "none" in text.lower()

    def test_lists_new_files(self):
        classified = {
            "new": [{"raw": "raw/interesting.pdf", "needs_conversion": True}],
            "updated": [],
            "unchanged": [],
        }
        manifest = pipeline.build_manifest(classified)
        text = pipeline.format_human(manifest)
        assert "interesting.pdf" in text
        assert "needs conversion" in text.lower()


# ---------------------------------------------------------------------------
# append_log
# ---------------------------------------------------------------------------

class TestAppendLog:
    def test_creates_log_with_frontmatter(self, tmp_path):
        (tmp_path / "wiki").mkdir()
        pipeline.append_log(tmp_path, "first message")

        log_path = tmp_path / "wiki" / "_log.md"
        assert log_path.exists()
        content = log_path.read_text()
        assert content.startswith("---")

    def test_log_contains_pipeline_tag(self, tmp_path):
        (tmp_path / "wiki").mkdir()
        pipeline.append_log(tmp_path, "something happened")

        log_path = tmp_path / "wiki" / "_log.md"
        content = log_path.read_text()
        assert "pipeline" in content

    def test_log_contains_message(self, tmp_path):
        (tmp_path / "wiki").mkdir()
        pipeline.append_log(tmp_path, "custom event logged")

        log_path = tmp_path / "wiki" / "_log.md"
        content = log_path.read_text()
        assert "custom event logged" in content

    def test_second_call_appends(self, tmp_path):
        (tmp_path / "wiki").mkdir()
        pipeline.append_log(tmp_path, "first")
        pipeline.append_log(tmp_path, "second")

        log_path = tmp_path / "wiki" / "_log.md"
        content = log_path.read_text()
        assert "first" in content
        assert "second" in content
        # Both appear after the frontmatter block
        fm_end = content.index("---", 3) + 3  # skip second ---
        body = content[fm_end:]
        assert "first" in body
        assert "second" in body

    def test_creates_wiki_dir_if_missing(self, tmp_path):
        # No wiki/ directory at all
        pipeline.append_log(tmp_path, "auto-create")
        log_path = tmp_path / "wiki" / "_log.md"
        assert log_path.exists()


# ---------------------------------------------------------------------------
# raw_stem / expected_summary_path
# ---------------------------------------------------------------------------

class TestNamingHelpers:
    def test_raw_stem_strips_extension(self, tmp_path):
        p = tmp_path / "my-article.pdf"
        assert pipeline.raw_stem(p) == "my-article"

    def test_raw_stem_md(self, tmp_path):
        p = tmp_path / "genome-notes.md"
        assert pipeline.raw_stem(p) == "genome-notes"

    def test_expected_summary_path(self, monkeypatch, empty_vault):
        point_engine(monkeypatch, pipeline, empty_vault)
        raw = empty_vault / "raw" / "big-paper.md"
        expected = pipeline.expected_summary_path(raw)
        assert expected.name == "summary-big-paper.md"
        assert "sources" in str(expected)
