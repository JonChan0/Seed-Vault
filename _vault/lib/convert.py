"""
convert.py — File conversion engine for vault-ingest.

Converts non-markdown files to markdown using opendataloader-pdf (for PDFs)
or pypandoc (for all other binary formats), then prepends minimal YAML
frontmatter. The LLM layer handles semantic extraction.

PDF conversion priority:
  1. opendataloader-pdf  — high-fidelity, structure-aware PDF parser
     (install: pip install opendataloader-pdf)
  2. pypandoc fallback   — used when opendataloader-pdf is unavailable

Supported input formats: PDF, HTML, DOCX, EPUB, RTF, and passthrough for
.md / .txt files.

Depends on:
  - opendataloader-pdf (primary PDF backend, optional with graceful fallback)
  - pypandoc (fallback PDF + all other binary formats; requires Pandoc on PATH)
"""

import re
import shutil
import sys
import tempfile
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


def _try_opendataloader_pdf(input_path: Path) -> str | None:
    """Convert a PDF via opendataloader-pdf.

    Returns the markdown string on success, or None if the library is not
    installed or the conversion fails (caller falls back to pypandoc).
    """
    try:
        import opendataloader_pdf  # noqa: PLC0415
    except ImportError:
        return None

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            opendataloader_pdf.convert(
                input_path=[str(input_path)],
                output_dir=tmpdir,
                format="markdown",
            )
            # opendataloader-pdf writes <original-stem>.md into output_dir
            expected = Path(tmpdir) / f"{input_path.stem}.md"
            if expected.exists():
                return expected.read_text(encoding="utf-8", errors="replace")
            # Fallback: pick any .md file produced in the temp dir
            md_files = list(Path(tmpdir).glob("*.md"))
            if md_files:
                return md_files[0].read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert_file(input_path: str | Path, output_dir: str | Path) -> Path:
    """Convert *input_path* to a markdown file inside *output_dir*.

    For PDF files, opendataloader-pdf is tried first (structure-aware,
    high-fidelity). If unavailable or unsuccessful, pypandoc is used as
    a fallback. All other binary formats use pypandoc directly.

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
        If all conversion backends fail.
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
    # PDF: opendataloader-pdf first, then pypandoc fallback
    # ------------------------------------------------------------------
    if suffix == ".pdf":
        body = _try_opendataloader_pdf(input_path)
        if body is not None:
            fm = _frontmatter(title, "pdf", today)
            output_path.write_text(fm + body, encoding="utf-8")
            return output_path

        # Fall back to pypandoc
        _body = _convert_via_pandoc(input_path, "pdf")
        fm = _frontmatter(title, "pdf", today)
        output_path.write_text(fm + _body, encoding="utf-8")
        return output_path

    # ------------------------------------------------------------------
    # Other binary formats: pypandoc
    # ------------------------------------------------------------------
    format_map = {
        ".html": "html",
        ".htm":  "html",
        ".docx": "docx",
        ".epub": "epub",
        ".rtf":  "rtf",
    }

    if suffix not in format_map:
        raise ValueError(
            f"Unsupported file format '{suffix}'. "
            f"Supported: {sorted({'.pdf'} | set(format_map))} + .md .txt"
        )

    pandoc_fmt = format_map[suffix]
    body = _convert_via_pandoc(input_path, pandoc_fmt)
    fm = _frontmatter(title, pandoc_fmt, today)
    output_path.write_text(fm + body, encoding="utf-8")
    return output_path


def _convert_via_pandoc(input_path: Path, pandoc_fmt: str) -> str:
    """Run pypandoc conversion and return the markdown string.

    Raises
    ------
    RuntimeError
        If pypandoc is not installed or the conversion fails.
    """
    try:
        import pypandoc  # noqa: PLC0415
    except ImportError:
        print(
            "Error: pypandoc is not installed. "
            "Install it with:  pip install pypandoc",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        return pypandoc.convert_file(
            str(input_path),
            "markdown",
            format=pandoc_fmt,
            extra_args=["--wrap=none"],
        )
    except Exception as exc:
        raise RuntimeError(
            f"pypandoc failed to convert '{input_path}': {exc}"
        ) from exc


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
