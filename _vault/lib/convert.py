"""
convert.py — File conversion engine for vault-ingest.

Converts non-markdown files to markdown using pypandoc, then prepends
minimal YAML frontmatter. The LLM layer handles semantic extraction.

Supported input formats: PDF, HTML, DOCX, EPUB, RTF, and passthrough for
.md / .txt files.

Depends on: pypandoc (and a Pandoc binary reachable on PATH)
"""

import re
import shutil
import sys
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kebab_from_path(input_path: Path) -> str:
    """Derive a kebab-case stem from the input filename.

    'My Document (final).pdf' → 'my-document-final'
    """
    stem = input_path.stem
    # Lower-case, replace runs of non-alphanumeric chars with a hyphen
    kebab = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return kebab or "document"


def _title_from_stem(stem: str) -> str:
    """Turn a kebab-case stem into a Title Case title.

    'my-document-final' → 'My Document Final'
    """
    return " ".join(word.capitalize() for word in stem.split("-"))


def _frontmatter(title: str, original_format: str, ingested: str) -> str:
    return (
        "---\n"
        f'title: "{title}"\n'
        f"original_format: {original_format}\n"
        f"ingested: {ingested}\n"
        "---\n\n"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert_file(input_path: str | Path, output_dir: str | Path) -> Path:
    """Convert *input_path* to a markdown file inside *output_dir*.

    Parameters
    ----------
    input_path:
        Path to the source file (PDF, HTML, DOCX, EPUB, RTF, .md, or .txt).
    output_dir:
        Directory where the converted .md file will be written.
        Created automatically if it does not exist.

    Returns
    -------
    Path
        Absolute path to the written markdown file.

    Raises
    ------
    ValueError
        If the file extension is not supported.
    RuntimeError
        If pypandoc conversion fails.
    """
    input_path = Path(input_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = input_path.suffix.lower()
    kebab = _kebab_from_path(input_path)
    output_path = output_dir / f"{kebab}.md"
    title = _title_from_stem(kebab)
    today = date.today().isoformat()

    # ------------------------------------------------------------------
    # Passthrough: already markdown or plain text
    # ------------------------------------------------------------------
    if suffix in {".md", ".txt"}:
        body = input_path.read_text(encoding="utf-8", errors="replace")
        fm = _frontmatter(title, suffix.lstrip("."), today)
        output_path.write_text(fm + body, encoding="utf-8")
        return output_path

    # ------------------------------------------------------------------
    # Pandoc-based conversion
    # ------------------------------------------------------------------
    format_map = {
        ".pdf":  "pdf",
        ".html": "html",
        ".htm":  "html",
        ".docx": "docx",
        ".epub": "epub",
        ".rtf":  "rtf",
    }

    if suffix not in format_map:
        raise ValueError(
            f"Unsupported file format '{suffix}'. "
            f"Supported: {sorted(format_map)} + .md .txt"
        )

    try:
        import pypandoc  # noqa: PLC0415  (deferred import for graceful error)
    except ImportError:
        print(
            "Error: pypandoc is not installed. "
            "Install it with:  pip install pypandoc",
            file=sys.stderr,
        )
        sys.exit(1)

    pandoc_fmt = format_map[suffix]

    try:
        body = pypandoc.convert_file(
            str(input_path),
            "markdown",
            format=pandoc_fmt,
            extra_args=["--wrap=none"],
        )
    except Exception as exc:
        raise RuntimeError(
            f"pypandoc failed to convert '{input_path}': {exc}"
        ) from exc

    fm = _frontmatter(title, pandoc_fmt, today)
    output_path.write_text(fm + body, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Usage: uv run python _vault/lib/convert.py <input_path> [output_dir]
    # Default output_dir is raw/

    if len(sys.argv) < 2:
        print(
            "Usage: uv run python _vault/lib/convert.py <input_path> [output_dir]",
            file=sys.stderr,
        )
        sys.exit(1)

    _input = Path(sys.argv[1])
    _output_dir = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("raw")

    if not _input.exists():
        print(f"Error: input file not found: {_input}", file=sys.stderr)
        sys.exit(1)

    try:
        result = convert_file(_input, _output_dir)
        print(f"Converted: {result}")
    except (ValueError, RuntimeError) as _exc:
        print(f"Error: {_exc}", file=sys.stderr)
        sys.exit(1)
