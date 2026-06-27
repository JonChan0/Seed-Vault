"""
frontmatter.py — Shared utility for parsing and writing YAML frontmatter
in markdown files for the Seed Vault wiki framework.

Depends on: python-frontmatter
"""

import re
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import frontmatter

# Meta/system files that are not content articles. Shared by every engine so a
# new exclusion only has to be added once.
EXCLUDED_NAMES = {"_index.md", "_log.md", "_migration-log.md", "_catalog.md"}
EXCLUDED_SUFFIXES = {".base"}

# Captures a [[wikilink]] target: the text before any "|" alias or "#" anchor.
WIKILINK_RE = re.compile(r"\[\[([^\]\n#|]+)")


def slugify(text: str) -> str:
    """Convert Title Case or spaces into kebab-case.

    Example: "Uncontrolled Hypertension" -> "uncontrolled-hypertension"
    Example: "summary-lilly-ai-collab" -> "summary-lilly-ai-collab"
    """
    # Remove apostrophes (don't replace with dash)
    s = text.replace("'", "").replace("’", "")
    # Replace non-alphanumeric with dashes
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s)
    # Strip leading/trailing dashes and lowercase
    return s.strip("-").lower()


def normalize_key(text: str) -> str:
    """Normalized lookup key for link/title matching.

    Lowercases and collapses hyphens, underscores, and runs of whitespace to a
    single space, so an aliased wikilink target like ``dummy-human-genome`` and
    the article title ``Dummy Human Genome`` map to the same key. Distinct from
    :func:`slugify` (which produces kebab-case) — do not conflate the two.
    """
    s = text.strip().lower().replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", s).strip()


def is_meta_file(path: Path) -> bool:
    """Return True for index/log/catalog/.base files that are not articles."""
    return path.name in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES


def parse_date(value: Any) -> date | None:
    """Parse a frontmatter date value into a ``date``.

    Accepts ``datetime`` (→ ``.date()``), ``date``, or an ISO-8601 string.
    Returns None for empty/unparseable values.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def extract_wikilinks(text: str) -> list[str]:
    """Return raw wikilink targets (text before any | or #) from markdown text.

    Targets are returned unstripped, exactly as captured; callers that need a
    clean key should ``.strip()`` or pass through :func:`normalize_key`.
    """
    return WIKILINK_RE.findall(text)


def extract_frontmatter_links(fm: dict, field: str, prefix: str = "") -> list[str]:
    """Extract wikilink targets from a frontmatter field (scalar or list).

    If ``prefix`` is given, only links whose target starts with that prefix are
    returned, with the prefix stripped (e.g. prefix='raw/' returns the stem
    after 'raw/'). Targets are stripped of surrounding whitespace.
    """
    val = fm.get(field)
    if not val:
        return []
    candidates = val if isinstance(val, list) else [val]
    pattern = re.compile(r"\[\[" + re.escape(prefix) + r"([^\]\n#|]+)")
    targets: list[str] = []
    for cand in candidates:
        m = pattern.search(str(cand))
        if m:
            targets.append(m.group(1).strip())
    return targets


def build_vault_map(wiki_dir: Path) -> dict[str, Path]:
    """Build a mapping of identifiers to absolute file paths."""
    vault_map: dict[str, Path] = {}
    if not wiki_dir.exists():
        return vault_map

    for md_file in wiki_dir.rglob("*.md"):
        # 1. Filename stem
        stem = md_file.stem.lower()
        vault_map[stem] = md_file
        
        # 2. Slugified stem
        vault_map[slugify(md_file.stem)] = md_file

        # 3. Frontmatter title
        metadata = parse_file(md_file)
        title = metadata.get("title", "")
        if title:
            vault_map[title.lower()] = md_file
            vault_map[slugify(title)] = md_file
            
        # 4. Handle files with underscores like _index.md
        if md_file.name.startswith("_"):
            stripped_name = md_file.stem.lstrip("_").lower()
            vault_map[stripped_name] = md_file
            vault_map[slugify(stripped_name)] = md_file
            
    return vault_map


def resolve_link(link_target: str, vault_map: dict[str, Path]) -> Path | None:
    """Resolve a wikilink target string to a file path.
    
    Matches against stems, titles, or slugified variants.
    """
    t = link_target.strip().lower()
    
    # Try direct match (stem or title)
    if t in vault_map:
        return vault_map[t]
    
    # Try slugified match
    slug = slugify(t)
    if slug in vault_map:
        return vault_map[slug]
        
    return None


def parse_file(filepath: str | os.PathLike) -> dict:
    """Parse YAML frontmatter from a markdown file.

    Returns a dict of YAML fields, or an empty dict if the file has no
    frontmatter, is empty, or cannot be read.
    """
    try:
        with open(filepath, encoding="utf-8") as fh:
            post = frontmatter.load(fh)
        return dict(post.metadata)
    except (OSError, UnicodeDecodeError):
        return {}
    except Exception:
        # Catch YAML parse errors and any other unexpected issues
        return {}


def parse_str(text: str) -> dict:
    """Parse YAML frontmatter from a string.

    Returns a dict of YAML fields, or an empty dict if there is no
    frontmatter or parsing fails.
    """
    try:
        post = frontmatter.loads(text)
        return dict(post.metadata)
    except Exception:
        return {}


def update_field(filepath: str | os.PathLike, field: str, value: Any) -> None:
    """Modify a single frontmatter field in-place, preserving the rest of the file.

    If the file has no frontmatter, a new frontmatter block is created with
    only the specified field. The file body (content below the frontmatter) is
    always preserved exactly as-is.
    """
    try:
        with open(filepath, encoding="utf-8") as fh:
            post = frontmatter.load(fh)
    except (OSError, UnicodeDecodeError) as exc:
        raise OSError(f"Could not read {filepath}: {exc}") from exc

    post[field] = value

    updated = frontmatter.dumps(post)
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(updated)


def scan_directory(
    dirpath: str | os.PathLike,
    fields: list[str] | None = None,
) -> list[dict]:
    """Scan a directory recursively for .md files and return their metadata.

    Args:
        dirpath: Root directory to scan.
        fields:  Optional list of metadata keys to include. When provided,
                 only those keys are returned (missing keys are omitted).
                 When None, all metadata keys are returned.

    Returns:
        A list of dicts, each with:
            {
                "path": str,           # absolute path to the file
                "metadata": dict,      # (filtered) frontmatter fields
            }
        Files with no frontmatter are included with an empty metadata dict
        (or are omitted entirely if all requested fields are absent).
    """
    results = []
    root = Path(dirpath)

    for md_file in sorted(root.rglob("*.md")):
        metadata = parse_file(md_file)

        if fields is not None:
            metadata = {k: metadata[k] for k in fields if k in metadata}

        results.append({"path": str(md_file), "metadata": metadata})

    return results
