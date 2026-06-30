"""Real-article tests for the vault-ingest deterministic layer.

Unlike ``test_convert.py`` (synthetic ``tmp_path`` inputs), this module runs the
conversion engine against the **real** clipped articles in ``tests/local/raw/``.
Those files are gitignored (``.gitignore``: ``tests/local/*``), so CI and fresh
clones won't have them — every test here skips cleanly when the dir is empty.

Coverage is parametrized over whatever ``.md`` files are present, so dropping a new
article into ``tests/local/raw/`` extends coverage with no edits here. All cases
hit ``convert_file``'s ``.md`` passthrough path (``_vault/lib/convert.py``).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from _vault.lib.convert import _kebab_from_path, convert_file

# --- Collect real articles at import time -----------------------------------
LOCAL_RAW_DIR = Path(__file__).resolve().parent / "local" / "raw"
LOCAL_RAW_FILES = sorted(LOCAL_RAW_DIR.glob("*.md")) if LOCAL_RAW_DIR.is_dir() else []

# Mark the whole module: it's local-data-only, and skips when that data is absent.
pytestmark = [
    pytest.mark.local,
    pytest.mark.skipif(
        not LOCAL_RAW_FILES,
        reason=f"no local articles in {LOCAL_RAW_DIR} (gitignored; absent in CI)",
    ),
]


def _ids(paths: list[Path]) -> list[str]:
    return [p.name for p in paths]


# --- Passthrough conversion of real articles --------------------------------

@pytest.mark.parametrize("src", LOCAL_RAW_FILES, ids=_ids(LOCAL_RAW_FILES))
class TestLocalArticlePassthrough:
    def test_produces_md_output(self, src: Path, tmp_path: Path):
        out = convert_file(src, tmp_path / "out")
        assert out.exists()
        assert out.suffix == ".md"
        assert out.parent.is_dir()  # output dir auto-created

    def test_filename_is_kebab_of_source(self, src: Path, tmp_path: Path):
        # Locks in unicode handling: spaces and curly quote (U+2019) → hyphens.
        out = convert_file(src, tmp_path / "out")
        assert out.name == f"{_kebab_from_path(src)}.md"

    def test_engine_frontmatter_prepended(self, src: Path, tmp_path: Path):
        out = convert_file(src, tmp_path / "out")
        content = out.read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "original_format: md" in content

    def test_full_body_preserved(self, src: Path, tmp_path: Path):
        # .md passthrough embeds the *entire* source file (its own frontmatter
        # included) as the body verbatim — nothing truncated or summarized.
        out = convert_file(src, tmp_path / "out")
        content = out.read_text(encoding="utf-8")
        original = src.read_text(encoding="utf-8")
        assert original in content

    def test_unicode_integrity(self, src: Path, tmp_path: Path):
        # Guard encoding regressions: any curly quote in the source must survive.
        original = src.read_text(encoding="utf-8")
        if "’" not in original:
            pytest.skip("source has no curly apostrophe to check")
        out = convert_file(src, tmp_path / "out")
        assert "’" in out.read_text(encoding="utf-8")


# --- Gitignore guard --------------------------------------------------------

@pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git not on PATH",
)
def test_local_articles_are_gitignored():
    """The real clippings must stay out of git — a `.gitignore` regression that
    starts tracking them should fail the suite, not silently leak sources."""
    result = subprocess.run(
        ["git", "check-ignore", *[str(p) for p in LOCAL_RAW_FILES]],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
    )
    if result.returncode == 128:
        pytest.skip("not a git work tree")
    # check-ignore exits 0 when every path given is ignored.
    assert result.returncode == 0, (
        "tests/local/raw articles are NOT gitignored:\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    ignored = set(result.stdout.split("\n")) - {""}
    assert len(ignored) == len(LOCAL_RAW_FILES)
