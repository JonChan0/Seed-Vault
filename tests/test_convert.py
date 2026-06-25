"""Unit tests for _vault/lib/convert.py."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from _vault.lib.convert import (
    _kebab_from_path,
    _title_from_stem,
    _frontmatter,
    convert_file,
)


# ---------------------------------------------------------------------------
# _kebab_from_path
# ---------------------------------------------------------------------------

class TestKebabFromPath:
    def test_basic_spaces(self):
        assert _kebab_from_path(Path("My Document.pdf")) == "my-document"

    def test_parentheses_stripped(self):
        assert _kebab_from_path(Path("My Document (final).pdf")) == "my-document-final"

    def test_all_lower(self):
        assert _kebab_from_path(Path("UPPER.md")) == "upper"

    def test_multiple_special_chars(self):
        result = _kebab_from_path(Path("Hello   World--test.md"))
        assert result == "hello-world-test"

    def test_already_kebab(self):
        assert _kebab_from_path(Path("my-document.md")) == "my-document"

    def test_leading_trailing_hyphens_stripped(self):
        result = _kebab_from_path(Path("-bad-name-.txt"))
        # Leading/trailing hyphens should be removed
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_empty_stem_fallback(self):
        # Edge: a stem that is all special chars → "document"
        result = _kebab_from_path(Path("---.pdf"))
        assert result == "document"


# ---------------------------------------------------------------------------
# _title_from_stem
# ---------------------------------------------------------------------------

class TestTitleFromStem:
    def test_basic(self):
        assert _title_from_stem("my-doc") == "My Doc"

    def test_single_word(self):
        assert _title_from_stem("genome") == "Genome"

    def test_multi_word(self):
        assert _title_from_stem("human-genome-project") == "Human Genome Project"

    def test_already_capitalized(self):
        # Each word capitalized independently
        assert _title_from_stem("crispr-cas9") == "Crispr Cas9"


# ---------------------------------------------------------------------------
# _frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_contains_title(self):
        fm = _frontmatter("My Title", "pdf", "2026-01-01")
        assert "My Title" in fm

    def test_contains_original_format(self):
        fm = _frontmatter("Doc", "html", "2026-01-01")
        assert "html" in fm

    def test_starts_with_dashes(self):
        fm = _frontmatter("Doc", "md", "2026-06-01")
        assert fm.startswith("---")

    def test_ends_with_blank_line(self):
        fm = _frontmatter("Doc", "txt", "2026-06-01")
        # Should end with "---\n\n" so body follows cleanly
        assert "---\n\n" in fm

    def test_ingested_date_present(self):
        today = "2026-06-25"
        fm = _frontmatter("X", "md", today)
        assert today in fm


# ---------------------------------------------------------------------------
# convert_file — passthrough (.md and .txt)
# ---------------------------------------------------------------------------

class TestConvertFilePassthrough:
    def test_md_passthrough_returns_path(self, tmp_path):
        src = tmp_path / "src" / "article.md"
        src.parent.mkdir()
        src.write_text("# Hello\n\nSome content here.", encoding="utf-8")

        out = convert_file(src, tmp_path / "out")
        assert out.exists()
        assert out.suffix == ".md"

    def test_md_passthrough_has_frontmatter(self, tmp_path):
        src = tmp_path / "article.md"
        src.write_text("# Hello\n\nContent.", encoding="utf-8")

        out = convert_file(src, tmp_path / "out")
        content = out.read_text(encoding="utf-8")
        assert content.startswith("---")

    def test_md_passthrough_includes_body(self, tmp_path):
        body = "# My Heading\n\nSome content here.\n"
        src = tmp_path / "my-article.md"
        src.write_text(body, encoding="utf-8")

        out = convert_file(src, tmp_path / "out")
        content = out.read_text(encoding="utf-8")
        assert "My Heading" in content
        assert "Some content here" in content

    def test_txt_passthrough_returns_path(self, tmp_path):
        src = tmp_path / "notes.txt"
        src.write_text("Plain text notes.", encoding="utf-8")

        out = convert_file(src, tmp_path / "out")
        assert out.exists()
        assert out.suffix == ".md"

    def test_txt_passthrough_has_frontmatter(self, tmp_path):
        src = tmp_path / "notes.txt"
        src.write_text("Plain text notes.", encoding="utf-8")

        out = convert_file(src, tmp_path / "out")
        content = out.read_text(encoding="utf-8")
        assert content.startswith("---")

    def test_txt_passthrough_includes_body(self, tmp_path):
        src = tmp_path / "notes.txt"
        src.write_text("A unique phrase in the body.", encoding="utf-8")

        out = convert_file(src, tmp_path / "out")
        content = out.read_text(encoding="utf-8")
        assert "A unique phrase in the body." in content

    def test_output_dir_created_automatically(self, tmp_path):
        src = tmp_path / "doc.md"
        src.write_text("x")
        out_dir = tmp_path / "nested" / "output"

        out = convert_file(src, out_dir)
        assert out_dir.exists()
        assert out.exists()

    def test_output_filename_is_kebab(self, tmp_path):
        src = tmp_path / "My Cool Doc.md"
        src.write_text("content")

        out = convert_file(src, tmp_path / "out")
        assert out.name == "my-cool-doc.md"


# ---------------------------------------------------------------------------
# convert_file — unsupported extension raises ValueError
# ---------------------------------------------------------------------------

class TestConvertFileUnsupported:
    def test_xyz_raises_value_error(self, tmp_path):
        src = tmp_path / "file.xyz"
        src.write_text("data")

        with pytest.raises(ValueError, match="Unsupported file format"):
            convert_file(src, tmp_path / "out")

    def test_json_raises_value_error(self, tmp_path):
        src = tmp_path / "data.json"
        src.write_text("{}")

        with pytest.raises(ValueError):
            convert_file(src, tmp_path / "out")


# ---------------------------------------------------------------------------
# convert_file — HTML→md (requires pandoc)
# ---------------------------------------------------------------------------

@pytest.mark.requires_pandoc
@pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="pandoc not available on PATH",
)
class TestConvertFileHTML:
    def test_html_to_md(self, tmp_path):
        src = tmp_path / "page.html"
        src.write_text(
            "<html><body><h1>Hello</h1><p>World</p></body></html>",
            encoding="utf-8",
        )
        out = convert_file(src, tmp_path / "out")

        assert out.exists()
        assert out.suffix == ".md"
        content = out.read_text(encoding="utf-8")
        # Must have frontmatter
        assert content.startswith("---")
        # Must contain some converted text
        assert "Hello" in content
