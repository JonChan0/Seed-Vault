"""
pipeline.py — Orchestration engine for the Seed Vault wiki pipeline.

Scans raw/ for source files, compares them against existing wiki/sources/
summaries, and outputs a manifest describing what needs to be ingested or
re-ingested. This script is detection-only — it never modifies vault content.

Usage:
    uv run python _vault/lib/pipeline.py [--dry-run] [--json]

Options:
    --dry-run   No-op flag (detection is always read-only; included for
                pipeline symmetry so callers can pass it unconditionally).
    --json      Output raw JSON manifest instead of human-readable summary.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Vault root and directory constants
# ---------------------------------------------------------------------------

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = VAULT_ROOT / "raw"
SOURCES_DIR = VAULT_ROOT / "wiki" / "sources"
LOG_FILE = VAULT_ROOT / "wiki" / "_log.md"

# File extensions that are not already markdown and require conversion
_MARKDOWN_EXTENSIONS = {".md", ".txt"}


# ---------------------------------------------------------------------------
# Filename convention helpers
# ---------------------------------------------------------------------------

def raw_stem(raw_path: Path) -> str:
    """Return the stem used for summary matching: strip the extension.

    raw/foo.pdf  → 'foo'
    raw/bar.md   → 'bar'
    """
    return raw_path.stem


def expected_summary_path(raw_path: Path) -> Path:
    """Return the expected wiki/sources/ path for a given raw file.

    raw/foo.pdf  → wiki/sources/summary-foo.md
    raw/bar.md   → wiki/sources/summary-bar.md
    """
    return SOURCES_DIR / f"summary-{raw_stem(raw_path)}.md"


def needs_conversion(raw_path: Path) -> bool:
    """Return True if the file must be converted before ingestion."""
    return raw_path.suffix.lower() not in _MARKDOWN_EXTENSIONS


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------

def scan_raw(raw_dir: Path) -> list[Path]:
    """Return all files found directly under raw_dir (non-recursive).

    Silently returns an empty list if the directory does not exist.
    """
    if not raw_dir.exists():
        return []
    return sorted(p for p in raw_dir.iterdir() if p.is_file())


def classify_files(raw_files: list[Path]) -> dict[str, list[dict]]:
    """Classify each raw file as new, updated, or unchanged.

    Returns a dict with keys 'new', 'updated', 'unchanged', each mapping
    to a list of entry dicts suitable for JSON serialisation.
    """
    result: dict[str, list[dict]] = {"new": [], "updated": [], "unchanged": []}

    for raw_path in raw_files:
        summary_path = expected_summary_path(raw_path)
        rel_raw = str(raw_path.relative_to(VAULT_ROOT))

        if not summary_path.exists():
            # No summary yet — brand new file
            entry: dict = {"raw": rel_raw}
            if needs_conversion(raw_path):
                entry["needs_conversion"] = True
            result["new"].append(entry)
        else:
            rel_summary = str(summary_path.relative_to(VAULT_ROOT))
            raw_mtime = raw_path.stat().st_mtime
            summary_mtime = summary_path.stat().st_mtime

            if raw_mtime > summary_mtime:
                result["updated"].append({
                    "raw": rel_raw,
                    "summary": rel_summary,
                })
            else:
                result["unchanged"].append({
                    "raw": rel_raw,
                    "summary": rel_summary,
                })

    return result


def build_manifest(classified: dict[str, list[dict]]) -> dict:
    """Wrap classified entries in a full manifest structure."""
    total_raw = (
        len(classified["new"])
        + len(classified["updated"])
        + len(classified["unchanged"])
    )
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "new": classified["new"],
        "updated": classified["updated"],
        "unchanged": classified["unchanged"],
        "stats": {
            "total_raw": total_raw,
            "new": len(classified["new"]),
            "updated": len(classified["updated"]),
            "unchanged": len(classified["unchanged"]),
        },
    }


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_human(manifest: dict) -> str:
    """Render a human-readable pipeline assessment string."""
    ts = manifest["timestamp"]
    date_part = ts[:10]
    stats = manifest["stats"]

    lines: list[str] = [
        f"Pipeline Assessment — {date_part}",
        "",
        f"Raw files scanned:      {stats['total_raw']}",
        f"Already-summarized:     {stats['total_raw'] - stats['new']}",
        "",
    ]

    # New
    if manifest["new"]:
        lines.append("New (need ingest):")
        for entry in manifest["new"]:
            suffix = " (needs conversion)" if entry.get("needs_conversion") else ""
            lines.append(f"  + {entry['raw']}{suffix}")
    else:
        lines.append("New (need ingest): none")
    lines.append("")

    # Updated
    if manifest["updated"]:
        lines.append("Updated (need re-ingest):")
        for entry in manifest["updated"]:
            lines.append(f"  ~ {entry['raw']} \u2192 {entry['summary']}")
    else:
        lines.append("Updated (need re-ingest): none")
    lines.append("")

    # Unchanged
    lines.append(
        f"Unchanged: {stats['unchanged']} file{'s' if stats['unchanged'] != 1 else ''}"
    )
    lines.append("")
    lines.append(
        f"Summary: {stats['new']} new, "
        f"{stats['updated']} updated, "
        f"{stats['unchanged']} unchanged"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Log helper
# ---------------------------------------------------------------------------

_LOG_FRONTMATTER = (
    "---\n"
    'title: "Pipeline Log"\n'
    "type: output\n"
    "created: {created}\n"
    "updated: {updated}\n"
    "sources: []\n"
    "tags: [pipeline/log]\n"
    "status: draft\n"
    'framework_version: "3.0.0"\n'
    "---\n"
    "\n"
    "# Pipeline Log\n"
    "\n"
    "Timestamped record of pipeline operations.\n"
    "\n"
)


def append_log(vault_root: Path, message: str) -> None:
    """Append a timestamped line to wiki/_log.md.

    Creates the file with proper frontmatter if it does not exist.

    Format of each log line:
        [YYYY-MM-DD HH:MM operation] message text here
    """
    log_path = vault_root / "wiki" / "_log.md"
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")

    # Create with frontmatter if missing
    if not log_path.exists():
        today = now.strftime("%Y-%m-%d")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            _LOG_FRONTMATTER.format(created=today, updated=today),
            encoding="utf-8",
        )

    line = f"[{timestamp} pipeline] {message}\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Scan raw/ and wiki/sources/ to produce a pipeline manifest. "
            "This script is detection-only — it never modifies vault content."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No-op compatibility flag (detection is always read-only).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output raw JSON manifest instead of human-readable summary.",
    )
    args = parser.parse_args()

    raw_files = scan_raw(RAW_DIR)
    classified = classify_files(raw_files)
    manifest = build_manifest(classified)

    if args.json_output:
        print(json.dumps(manifest, indent=2))
    else:
        print(format_human(manifest))


if __name__ == "__main__":
    main()
