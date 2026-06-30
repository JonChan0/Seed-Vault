"""Unit tests for _vault/lib/summary_scaffold.py.

The scaffolder owns the deterministic raw backlinks (`sources` /
`original_source`) of a source summary. Tests repoint its path constants at a
temp vault via ``conftest.point_engine`` (in-process), then assert it creates a
correct scaffold and idempotently patches an existing summary without clobbering
the LLM-authored body.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from _vault.lib import summary_scaffold
from _vault.lib.vault_frontmatter import parse_file
from tests.conftest import point_engine, run_engine


def _write_raw(vault: Path, stem: str, title: str | None, body: str = "Body text.") -> Path:
    raw = vault / "raw" / f"{stem}.md"
    fm = f'---\ntitle: "{title}"\n---\n\n' if title is not None else ""
    raw.write_text(fm + body, encoding="utf-8")
    return raw


# --- Pure helpers -----------------------------------------------------------

class TestHelpers:
    def test_backlink_format(self):
        assert summary_scaffold.backlink("foo-bar", "Foo Bar") == "[[raw/foo-bar|Foo Bar]]"

    def test_backlink_alias_strips_wikilink_breaking_chars(self):
        # A raw title with pipe / brackets / anchor markers must not break the
        # [[raw/<stem>|<alias>]] syntax — those chars are stripped from the alias
        # (SKILL Step 3: sanitize wikilink text), whitespace collapsed.
        link = summary_scaffold.backlink("doc", "A | B [x] #c ^d")
        assert link == "[[raw/doc|A B x c d]]"
        assert link.count("|") == 1  # exactly the alias separator

    def test_backlink_alias_keeps_safe_punctuation(self):
        # Colons, apostrophes, $, & are valid in aliases — keep them (e.g. the
        # real "AACR: ..." clipping title).
        link = summary_scaffold.backlink("doc", "AACR: R&D worth $2.75B — it's fine")
        assert link == "[[raw/doc|AACR: R&D worth $2.75B — it's fine]]"

    def test_raw_title_from_frontmatter(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = _write_raw(empty_vault, "my-doc", "My Real Title")
        assert summary_scaffold.raw_title(raw) == "My Real Title"

    def test_raw_title_falls_back_to_stem(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = _write_raw(empty_vault, "my-doc", None)  # no title frontmatter
        assert summary_scaffold.raw_title(raw) == "My Doc"


# --- New scaffold -----------------------------------------------------------

class TestScaffoldNew:
    def test_creates_summary_at_expected_path(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = _write_raw(empty_vault, "crispr-revolution", "The CRISPR Revolution")
        out = summary_scaffold.scaffold_summary(raw)
        assert out == empty_vault / "wiki" / "sources" / "summary-crispr-revolution.md"
        assert out.exists()

    def test_deterministic_backlinks_use_raw_title(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = _write_raw(empty_vault, "crispr-revolution", "The CRISPR Revolution")
        out = summary_scaffold.scaffold_summary(raw)
        fm = parse_file(out)
        link = "[[raw/crispr-revolution|The CRISPR Revolution]]"
        assert fm["original_source"] == link
        assert fm["sources"] == [link]

    def test_title_with_double_quote_stays_valid_yaml(self, empty_vault, monkeypatch):
        # A straight quote in the raw title must not corrupt the summary's YAML
        # frontmatter — sources/original_source/title must still parse.
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = empty_vault / "raw" / "doc.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        # Single-quoted YAML so the raw file itself is valid with a " in the title.
        raw.write_text("---\ntitle: 'He said \"hi\" to R&D'\n---\n\nbody", encoding="utf-8")
        out = summary_scaffold.scaffold_summary(raw)
        fm = parse_file(out)
        link = '[[raw/doc|He said "hi" to R&D]]'
        assert fm["sources"] == [link]
        assert fm["original_source"] == link
        assert fm["title"] == 'Summary - He said "hi" to R&D'

    def test_no_raw_source_section(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = _write_raw(empty_vault, "doc", "Doc Title")
        out = summary_scaffold.scaffold_summary(raw)
        assert "## Raw Source" not in out.read_text(encoding="utf-8")

    def test_has_body_template_for_llm(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = _write_raw(empty_vault, "doc", "Doc Title")
        content = summary_scaffold.scaffold_summary(raw).read_text(encoding="utf-8")
        assert "## Key Takeaways" in content
        assert "## Detailed Summary" in content
        assert "## Concepts Extracted" in content

    def test_type_and_framework_version(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        # _framework_version reads <VAULT_ROOT>/_vault/VERSION; provide one.
        (empty_vault / "_vault").mkdir()
        (empty_vault / "_vault" / "VERSION").write_text("9.9.9", encoding="utf-8")
        raw = _write_raw(empty_vault, "doc", "Doc Title")
        fm = parse_file(summary_scaffold.scaffold_summary(raw))
        assert fm["type"] == "source-summary"
        assert fm["framework_version"] == "9.9.9"


# --- Idempotent patch of an existing summary --------------------------------

class TestScaffoldExisting:
    def test_patches_backlinks_preserving_body(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = _write_raw(empty_vault, "doc", "Corrected Title")
        summary = empty_vault / "wiki" / "sources" / "summary-doc.md"
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text(
            "---\n"
            'title: "Summary - Doc"\n'
            "type: source-summary\n"
            "tags: [bio/genomics]\n"
            'sources: ["[[raw/doc|WRONG ALIAS]]"]\n'
            'original_source: "[[raw/wrong-stem|WRONG]]"\n'
            'llm_model: "claude-opus-4-8"\n'
            "---\n\n"
            "# Summary - Doc\n\n"
            "## Key Takeaways\n\n- A hand-written takeaway.\n",
            encoding="utf-8",
        )
        out = summary_scaffold.scaffold_summary(raw)
        fm = parse_file(out)
        link = "[[raw/doc|Corrected Title]]"
        # Deterministic fields corrected...
        assert fm["original_source"] == link
        assert fm["sources"] == [link]
        # ...other metadata and LLM body untouched.
        assert fm["tags"] == ["bio/genomics"]
        assert fm["llm_model"] == "claude-opus-4-8"
        assert "A hand-written takeaway." in out.read_text(encoding="utf-8")

    def test_idempotent_backlinks_and_convergence(self, empty_vault, monkeypatch):
        # The deterministic fields stay identical across runs (semantic
        # idempotency); after the first patch the file is byte-stable (the
        # create-template normalizes to the patched form on run 2, then holds).
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = _write_raw(empty_vault, "doc", "Doc Title")
        link = "[[raw/doc|Doc Title]]"
        for _ in range(3):
            fm = parse_file(summary_scaffold.scaffold_summary(raw))
            assert fm["original_source"] == link
            assert fm["sources"] == [link]
        second = summary_scaffold.scaffold_summary(raw).read_text(encoding="utf-8")
        third = summary_scaffold.scaffold_summary(raw).read_text(encoding="utf-8")
        assert second == third


# --- Nested raw path: backlink must use the full relpath, not the bare stem ---

class TestNestedRawPath:
    def test_backlink_uses_relpath_under_raw(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = empty_vault / "raw" / "sub" / "doc.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text('---\ntitle: "Nested Doc"\n---\nbody', encoding="utf-8")
        out = summary_scaffold.scaffold_summary(raw)
        fm = parse_file(out)
        link = "[[raw/sub/doc|Nested Doc]]"
        assert fm["sources"] == [link]
        assert fm["original_source"] == link


# --- Error / fallback paths -------------------------------------------------

class TestRawTitleFallback:
    def test_non_string_title_falls_back_to_stem(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = empty_vault / "raw" / "my-doc.md"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text("---\ntitle: 123\n---\nbody", encoding="utf-8")  # int, not str
        assert summary_scaffold.raw_title(raw) == "My Doc"

    def test_whitespace_only_title_falls_back_to_stem(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        raw = _write_raw(empty_vault, "my-doc", "   ")
        assert summary_scaffold.raw_title(raw) == "My Doc"


def test_missing_raw_file_raises(empty_vault, monkeypatch):
    # Scaffolding from a non-existent raw file would emit a dangling backlink —
    # refuse instead (locks the intended behavior).
    point_engine(monkeypatch, summary_scaffold, empty_vault)
    with pytest.raises(FileNotFoundError):
        summary_scaffold.scaffold_summary(empty_vault / "raw" / "ghost.md")


def test_framework_version_empty_when_version_absent(empty_vault, monkeypatch):
    # No _vault/VERSION under the temp vault → '' and the YAML still parses.
    point_engine(monkeypatch, summary_scaffold, empty_vault)
    raw = _write_raw(empty_vault, "doc", "Doc Title")
    fm = parse_file(summary_scaffold.scaffold_summary(raw))
    assert fm["framework_version"] == ""


def test_existing_correct_summary_not_rewritten(empty_vault, monkeypatch):
    # A hand-authored summary whose backlinks are already correct must be left
    # byte-for-byte untouched (no re-serialization / key reorder → no git churn),
    # even when its field order differs from what the engine would emit.
    point_engine(monkeypatch, summary_scaffold, empty_vault)
    raw = _write_raw(empty_vault, "doc", "Doc Title")
    link = "[[raw/doc|Doc Title]]"
    summary = empty_vault / "wiki" / "sources" / "summary-doc.md"
    summary.parent.mkdir(parents=True, exist_ok=True)
    original = (
        "---\n"
        "type: source-summary\n"             # deliberately not alphabetical
        f'original_source: "{link}"\n'
        f'sources: ["{link}"]\n'
        'title: "Summary - Doc Title"\n'
        "---\n\n# Summary - Doc Title\n\nHand-written body.\n"
    )
    summary.write_text(original, encoding="utf-8")
    summary_scaffold.scaffold_summary(raw)
    assert summary.read_text(encoding="utf-8") == original


# --- CLI arg-resolver (the __main__ entrypoint) -----------------------------

class TestResolveRawArg:
    @pytest.mark.parametrize(
        "arg, expected",
        [
            ("crispr", "RAW/crispr.md"),            # bare stem
            ("crispr.md", "RAW/crispr.md"),         # filename, not present → raw/
            ("raw/crispr.md", "RAW/crispr.md"),     # relative .md, not present → raw/
        ],
    )
    def test_resolves_to_raw_dir(self, empty_vault, monkeypatch, arg, expected):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        got = summary_scaffold._resolve_raw_arg(arg)
        assert got == empty_vault / "raw" / Path(expected).name

    def test_absolute_md_used_as_given(self, empty_vault, monkeypatch):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        abs_path = empty_vault / "elsewhere" / "x.md"
        assert summary_scaffold._resolve_raw_arg(str(abs_path)) == abs_path

    def test_existing_relative_md_used_as_given(self, empty_vault, monkeypatch, tmp_path):
        point_engine(monkeypatch, summary_scaffold, empty_vault)
        rel = Path("present.md")
        (empty_vault / "present.md").write_text("x", encoding="utf-8")
        monkeypatch.chdir(empty_vault)
        assert summary_scaffold._resolve_raw_arg(str(rel)) == rel


# --- CLI black-box (real subprocess, real VAULT_ROOT) -----------------------

def test_cli_scaffolds_from_bare_stem(subprocess_vault):
    raw = subprocess_vault / "raw" / "crispr.md"
    raw.write_text('---\ntitle: "CRISPR"\n---\nbody', encoding="utf-8")
    result = run_engine(subprocess_vault, "summary_scaffold", "crispr")
    assert result.returncode == 0, result.stderr
    assert (subprocess_vault / "wiki" / "sources" / "summary-crispr.md").exists()


def test_cli_no_arg_exits_1(subprocess_vault):
    result = run_engine(subprocess_vault, "summary_scaffold")
    assert result.returncode == 1
    assert "Usage" in result.stderr
