"""Unit tests for _vault/lib/vault_frontmatter.py (pure functions)."""
from __future__ import annotations

from pathlib import Path


from _vault.lib.vault_frontmatter import (
    build_vault_map,
    parse_file,
    parse_str,
    resolve_link,
    scan_directory,
    slugify,
    update_field,
)

# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic_title_case(self):
        assert slugify("Uncontrolled Hypertension") == "uncontrolled-hypertension"

    def test_already_kebab(self):
        assert slugify("summary-lilly-ai-collab") == "summary-lilly-ai-collab"

    def test_apostrophe_stripped_not_dashed(self):
        assert slugify("don't") == "dont"

    def test_curly_apostrophe_stripped(self):
        # Right single quotation mark (U+2019)
        assert slugify("it’s") == "its"

    def test_multiple_spaces_collapsed(self):
        result = slugify("Hello   World")
        assert result == "hello-world"

    def test_special_chars_become_dash(self):
        result = slugify("Hello, World!")
        assert result == "hello-world"

    def test_lowercase_output(self):
        assert slugify("UPPER CASE") == "upper-case"

    def test_leading_trailing_dashes_stripped(self):
        result = slugify("-bad-")
        assert not result.startswith("-")
        assert not result.endswith("-")


# ---------------------------------------------------------------------------
# parse_str
# ---------------------------------------------------------------------------


class TestParseStr:
    def test_basic_frontmatter(self):
        text = "---\ntitle: X\n---\nbody"
        result = parse_str(text)
        assert result == {"title": "X"}

    def test_multiple_fields(self):
        text = "---\ntitle: My Title\ntype: concept\nstatus: draft\n---\n"
        result = parse_str(text)
        assert result["title"] == "My Title"
        assert result["type"] == "concept"
        assert result["status"] == "draft"

    def test_no_frontmatter_returns_empty(self):
        text = "Just plain text with no frontmatter."
        result = parse_str(text)
        assert result == {}

    def test_empty_string_returns_empty(self):
        assert parse_str("") == {}

    def test_malformed_frontmatter_returns_empty(self):
        # Only one --- delimiter
        text = "---\ntitle: broken\n"
        result = parse_str(text)
        # Should not raise, may return {} or partial
        assert isinstance(result, dict)

    def test_list_field(self):
        text = "---\ntags: [a, b, c]\n---\n"
        result = parse_str(text)
        assert result["tags"] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# parse_file
# ---------------------------------------------------------------------------


class TestParseFile:
    def test_reads_frontmatter_from_file(self, tmp_path):
        md = tmp_path / "article.md"
        md.write_text("---\ntitle: File Title\nstatus: draft\n---\nBody text.\n")
        result = parse_file(md)
        assert result["title"] == "File Title"
        assert result["status"] == "draft"

    def test_missing_file_returns_empty(self, tmp_path):
        result = parse_file(tmp_path / "nonexistent.md")
        assert result == {}

    def test_no_frontmatter_returns_empty(self, tmp_path):
        md = tmp_path / "plain.md"
        md.write_text("# Just a heading\n\nNo frontmatter here.\n")
        result = parse_file(md)
        assert result == {}

    def test_body_not_in_metadata(self, tmp_path):
        md = tmp_path / "article.md"
        md.write_text("---\ntitle: Only Title\n---\nBody content here.\n")
        result = parse_file(md)
        assert "Body content here" not in str(result)


# ---------------------------------------------------------------------------
# update_field
# ---------------------------------------------------------------------------


class TestUpdateField:
    def test_updates_existing_field(self, tmp_path):
        md = tmp_path / "article.md"
        md.write_text("---\ntitle: Old Title\nstatus: draft\n---\nBody.\n")

        update_field(md, "title", "New Title")

        result = parse_file(md)
        assert result["title"] == "New Title"

    def test_body_preserved_after_update(self, tmp_path):
        md = tmp_path / "article.md"
        md.write_text("---\ntitle: Title\n---\nImportant body text.\n")

        update_field(md, "title", "Changed")

        content = md.read_text()
        assert "Important body text." in content

    def test_adds_new_field(self, tmp_path):
        md = tmp_path / "article.md"
        md.write_text("---\ntitle: Title\n---\nBody.\n")

        update_field(md, "new_field", "new_value")

        result = parse_file(md)
        assert result["new_field"] == "new_value"

    def test_updates_to_list(self, tmp_path):
        md = tmp_path / "article.md"
        md.write_text("---\ntitle: T\ntags: []\n---\nBody.\n")

        update_field(md, "tags", ["tag1", "tag2"])

        result = parse_file(md)
        assert "tag1" in result["tags"]
        assert "tag2" in result["tags"]

    def test_other_fields_preserved(self, tmp_path):
        md = tmp_path / "article.md"
        md.write_text("---\ntitle: Title\nstatus: draft\ntype: concept\n---\nBody.\n")

        update_field(md, "status", "verified")

        result = parse_file(md)
        assert result["title"] == "Title"
        assert result["type"] == "concept"
        assert result["status"] == "verified"


# ---------------------------------------------------------------------------
# scan_directory
# ---------------------------------------------------------------------------


class TestScanDirectory:
    def _write_md(self, path: Path, title: str, status: str = "draft") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\ntitle: {title}\nstatus: {status}\n---\nBody.\n",
            encoding="utf-8",
        )

    def test_returns_list_of_dicts(self, tmp_path):
        self._write_md(tmp_path / "a.md", "Article A")
        result = scan_directory(tmp_path)
        assert isinstance(result, list)
        assert all("path" in r and "metadata" in r for r in result)

    def test_scans_recursively(self, tmp_path):
        self._write_md(tmp_path / "top.md", "Top")
        self._write_md(tmp_path / "sub" / "nested.md", "Nested")
        result = scan_directory(tmp_path)
        assert len(result) == 2

    def test_fields_filter(self, tmp_path):
        self._write_md(tmp_path / "a.md", "Article A", "reviewed")
        result = scan_directory(tmp_path, fields=["title"])
        assert len(result) == 1
        assert result[0]["metadata"] == {"title": "Article A"}
        # status should NOT appear when not requested
        assert "status" not in result[0]["metadata"]

    def test_fields_missing_key_omitted(self, tmp_path):
        self._write_md(tmp_path / "a.md", "A")
        # Request a field that doesn't exist in frontmatter
        result = scan_directory(tmp_path, fields=["nonexistent_key"])
        assert result[0]["metadata"] == {}

    def test_empty_dir_returns_empty(self, tmp_path):
        assert scan_directory(tmp_path) == []

    def test_path_is_string(self, tmp_path):
        self._write_md(tmp_path / "a.md", "A")
        result = scan_directory(tmp_path)
        assert isinstance(result[0]["path"], str)


# ---------------------------------------------------------------------------
# build_vault_map and resolve_link
# ---------------------------------------------------------------------------


class TestBuildVaultMapAndResolveLink:
    def test_build_vault_map_returns_dict(self, dummy_vault):
        wiki_dir = dummy_vault / "wiki"
        vault_map = build_vault_map(wiki_dir)
        assert isinstance(vault_map, dict)
        assert len(vault_map) > 0

    def test_resolve_by_stem(self, dummy_vault):
        wiki_dir = dummy_vault / "wiki"
        vault_map = build_vault_map(wiki_dir)
        result = resolve_link("dummy-human-genome", vault_map)
        assert result is not None
        assert result.stem == "dummy-human-genome"

    def test_resolve_by_title(self, dummy_vault):
        wiki_dir = dummy_vault / "wiki"
        vault_map = build_vault_map(wiki_dir)
        # Title is "Dummy Human Genome" from frontmatter
        result = resolve_link("Dummy Human Genome", vault_map)
        assert result is not None
        assert "dummy-human-genome" in result.stem

    def test_resolve_by_slugified_title(self, dummy_vault):
        wiki_dir = dummy_vault / "wiki"
        vault_map = build_vault_map(wiki_dir)
        result = resolve_link("dummy-gene-editing", vault_map)
        assert result is not None

    def test_resolve_unknown_returns_none(self, dummy_vault):
        wiki_dir = dummy_vault / "wiki"
        vault_map = build_vault_map(wiki_dir)
        result = resolve_link("absolutely-nonexistent-article", vault_map)
        assert result is None

    def test_resolve_case_insensitive(self, dummy_vault):
        wiki_dir = dummy_vault / "wiki"
        vault_map = build_vault_map(wiki_dir)
        # Try mixed-case version of the stem
        result = resolve_link("DUMMY-HUMAN-GENOME", vault_map)
        assert result is not None

    def test_all_fixture_articles_resolvable(self, dummy_vault):
        """Every article in the fixture can be resolved by its stem."""
        wiki_dir = dummy_vault / "wiki"
        vault_map = build_vault_map(wiki_dir)
        stems = [
            "dummy-human-genome",
            "dummy-gene-editing",
            "summary-dummy-genome-project",
            "summary-dummy-crispr",
        ]
        for stem in stems:
            result = resolve_link(stem, vault_map)
            assert result is not None, f"Could not resolve '{stem}'"
