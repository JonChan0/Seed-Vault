"""
summary_scaffold.py — Deterministic source-summary scaffolder for vault-ingest.

The wiki-graph edges from a source summary back to its raw document are purely
mechanical: given the raw file ``raw/<stem>.md`` they are always
``[[raw/<stem>|<Title>]]``. Letting the LLM author those backlinks invites
typos (wrong stem, missing alias) that silently break the graph, so this engine
fills them deterministically instead.

Run during ingest after ``raw/<stem>.md`` is finalized:

    uv run python _vault/lib/summary_scaffold.py raw/<stem>.md

- If ``wiki/sources/summary-<stem>.md`` does not exist, a scaffold is written
  with the deterministic ``sources`` / ``original_source`` backlinks plus an
  empty body template for the LLM to fill (Key Takeaways / Detailed Summary /
  Concepts Extracted).
- If it already exists, only the ``sources`` and ``original_source`` fields are
  (re)written — the LLM-authored body and other metadata are left untouched.

The display alias (``<Title>``) is read deterministically from the raw file's
``title:`` frontmatter, falling back to a Title-Cased version of the stem.
"""

import re
import sys
from datetime import date
from pathlib import Path

import frontmatter


# Chars that break the `[[raw/<stem>|<alias>]]` wikilink itself: the alias
# separator, bracket delimiters, and Obsidian anchor markers. Stripped from the
# display alias (SKILL Step 3). Filename-only invalid chars (: " < > ? * / \) are
# fine in an alias and kept for display fidelity.
_ALIAS_BREAKING = re.compile(r"[\[\]|#^]")

# Vault layout — repointed by tests via conftest.point_engine.
VAULT_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = VAULT_ROOT / "wiki"
RAW_DIR = VAULT_ROOT / "raw"
SOURCES_DIR = WIKI_DIR / "sources"

# Reuse the shared frontmatter utilities (python-frontmatter under the hood).
sys.path.append(str(VAULT_ROOT))
from _vault.lib.vault_frontmatter import parse_file, update_field  # noqa: E402
from _vault.lib.convert import _title_from_stem  # noqa: E402


def _framework_version() -> str:
    """Read the framework version from _vault/VERSION ('' if unavailable)."""
    try:
        return (VAULT_ROOT / "_vault" / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def raw_title(raw_path: Path) -> str:
    """Display title for backlinks: raw `title:` frontmatter, else stem-derived."""
    title = parse_file(raw_path).get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return _title_from_stem(raw_path.stem)


def _sanitize_alias(title: str) -> str:
    """Strip wikilink-breaking chars from a display alias, collapse whitespace."""
    return re.sub(r"\s+", " ", _ALIAS_BREAKING.sub("", title)).strip()


def _raw_ref(raw_path: Path) -> str:
    """The `raw/<ref>` path used in the backlink — relative to RAW_DIR (no
    suffix) so links to nested raw files still resolve in Obsidian. Falls back
    to the bare stem for paths outside RAW_DIR.
    """
    try:
        rel = raw_path.resolve().relative_to(RAW_DIR.resolve())
    except ValueError:
        return raw_path.stem
    return rel.with_suffix("").as_posix()


def backlink(ref: str, title: str) -> str:
    """The single deterministic raw backlink: `[[raw/<ref>|<Title>]]`.

    *ref* is the raw path relative to RAW_DIR (see `_raw_ref`); for a flat
    `raw/` it equals the stem. The alias is sanitized so a title containing
    `| [ ] # ^` cannot break the wikilink syntax.
    """
    return f"[[raw/{ref}|{_sanitize_alias(title)}]]"


_BODY_TEMPLATE = (
    "## Key Takeaways\n"
    "*(3–7 bullet points — the most important claims or findings)*\n\n"
    "-\n\n"
    "## Detailed Summary\n"
    "*(2–4 paragraphs synthesizing the content)*\n\n"
    "## Concepts Extracted\n"
    "*(List concepts this source informs, as [[wikilinks]])*\n\n"
    "-\n"
)


def _scaffold_body(title: str, link: str, today: str, version: str) -> str:
    """Full scaffold for a summary that does not exist yet. No `## Raw Source`
    section — the raw link lives in the deterministic frontmatter only.

    Serialized via the frontmatter library so titles/aliases containing YAML
    metacharacters (e.g. a straight `"`) are escaped correctly rather than
    corrupting the block.
    """
    post = frontmatter.Post(
        f"# Summary - {title}\n\n{_BODY_TEMPLATE}",
        title=f"Summary - {title}",
        type="source-summary",
        created=today,
        updated=today,
        sources=[link],
        original_source=link,
        tags=[],
        status="draft",
        llm_model="TODO-set-by-llm",
        framework_version=version,
    )
    return frontmatter.dumps(post) + "\n"


def scaffold_summary(raw_path: str | Path) -> Path:
    """Ensure the summary for *raw_path* carries deterministic raw backlinks.

    Returns the path to ``wiki/sources/summary-<stem>.md``. Creates it from a
    template if absent; otherwise patches only ``sources`` / ``original_source``.
    """
    raw_path = Path(raw_path)
    if not raw_path.exists():
        # Scaffolding from a missing raw file would emit a dangling backlink.
        raise FileNotFoundError(f"raw source not found: {raw_path}")

    title = raw_title(raw_path)
    link = backlink(_raw_ref(raw_path), title)

    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = SOURCES_DIR / f"summary-{raw_path.stem}.md"

    if summary_path.exists():
        # Deterministic fields win; LLM body and other metadata are preserved.
        # Skip the write entirely when both are already correct — avoids
        # re-serializing (and reordering) an already-good summary on every run.
        current = parse_file(summary_path)
        if current.get("sources") != [link] or current.get("original_source") != link:
            update_field(summary_path, "sources", [link])
            update_field(summary_path, "original_source", link)
    else:
        summary_path.write_text(
            _scaffold_body(title, link, date.today().isoformat(), _framework_version()),
            encoding="utf-8",
        )
    return summary_path


def _resolve_raw_arg(arg: str) -> Path:
    """Resolve a CLI arg (bare stem, filename, or path) to a raw/*.md file.

    - non-`.md` (bare stem or other suffix) → ``raw/<name>.md``
    - a real `.md` path (absolute, or existing relative) → used as given
    - a relative `.md` that isn't here → ``raw/<name>``
    """
    candidate = Path(arg)
    if candidate.suffix != ".md":
        return RAW_DIR / f"{candidate.name}.md"
    if candidate.is_absolute() or candidate.exists():
        return candidate
    return RAW_DIR / candidate.name


if __name__ == "__main__":
    # Usage: uv run python _vault/lib/summary_scaffold.py <raw_path_or_stem>
    if len(sys.argv) < 2:
        print(
            "Usage: uv run python _vault/lib/summary_scaffold.py <raw_path_or_stem>",
            file=sys.stderr,
        )
        sys.exit(1)

    result = scaffold_summary(_resolve_raw_arg(sys.argv[1]))
    print(f"Scaffolded: {result}")
