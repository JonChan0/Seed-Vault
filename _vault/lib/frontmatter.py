"""
frontmatter.py — Shared utility for parsing and writing YAML frontmatter
in markdown files for the Seed Vault wiki framework.

Depends on: python-frontmatter
"""

import os
from pathlib import Path
from typing import Any

import frontmatter


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
