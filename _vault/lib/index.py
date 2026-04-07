"""
index.py — Index generator for the Seed Vault wiki.

Scans wiki/**/*.md, groups articles by type, and writes wiki/_index.md.
Optionally rebuilds the qmd collection index.

Usage:
    uv run python _vault/lib/index.py [--rebuild-qmd]
    python -m _vault.lib.index [--rebuild-qmd]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Vault root detection
# ---------------------------------------------------------------------------

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = VAULT_ROOT / "wiki"
INDEX_FILE = WIKI_DIR / "_index.md"
VERSION_FILE = VAULT_ROOT / "_vault" / "VERSION"

# Files to exclude from scanning
EXCLUDED_NAMES = {"_index.md", "_log.md", "_migration-log.md", "_catalog.md"}
EXCLUDED_SUFFIXES = {".base"}

# ---------------------------------------------------------------------------
# Frontmatter helpers — prefer shared module, fall back to regex
# ---------------------------------------------------------------------------

try:
    from _vault.lib.frontmatter import parse_file as _fm_parse_file, scan_directory as _fm_scan_directory

    def parse_file(path: Path) -> dict:
        return _fm_parse_file(path)

    def scan_directory(dirpath: Path, fields=None) -> list[dict]:
        return _fm_scan_directory(dirpath, fields)

except ImportError:
    import yaml  # type: ignore

    _FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def _parse_frontmatter_regex(text: str) -> dict:
        m = _FM_RE.match(text)
        if not m:
            return {}
        try:
            return yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            return {}

    def parse_file(path: Path) -> dict:
        try:
            return _parse_frontmatter_regex(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            return {}

    def scan_directory(dirpath: Path, fields=None) -> list[dict]:
        results = []
        for md_file in sorted(Path(dirpath).rglob("*.md")):
            metadata = parse_file(md_file)
            if fields is not None:
                metadata = {k: metadata[k] for k in fields if k in metadata}
            results.append({"path": str(md_file), "metadata": metadata})
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_version() -> str:
    """Read the framework version from _vault/VERSION."""
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "2.0.0"


def is_excluded(path: Path) -> bool:
    """Return True if this file should be skipped."""
    return path.name in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES


def tags_str(tags) -> str:
    """Render a tags value (list or str) as a comma-separated string."""
    if not tags:
        return ""
    if isinstance(tags, list):
        return ", ".join(str(t) for t in tags)
    return str(tags)


def count_previous_entries(index_path: Path) -> int:
    """Count the number of article list lines in an existing _index.md."""
    if not index_path.exists():
        return 0
    text = index_path.read_text(encoding="utf-8")
    # Each article entry is a bullet line starting with "- [["
    return len(re.findall(r"^\s*- \[\[", text, re.MULTILINE))


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

# Display order and labels for each article type
TYPE_ORDER = [
    ("concept",        "Concepts"),
    ("source-summary", "Source Summaries"),
    ("topic",          "Topics"),
    ("visualization",  "Visualizations"),
    ("output",         "Outputs"),
]

PLACEHOLDER = {
    "concept":        "*(No concepts yet — ingest sources and ask Claude to compile)*",
    "source-summary": "*(No sources yet — drop files into `raw/` and use seed-ingest)*",
    "topic":          "*(No topics yet — topics are created automatically during compilation)*",
    "visualization":  "*(No visualizations yet — ask Claude to visualize data from the wiki)*",
    "output":         "*(No outputs yet)*",
}


def collect_articles(wiki_dir: Path) -> dict[str, list[dict]]:
    """Scan wiki_dir and return articles grouped by type, sorted by title."""
    if not wiki_dir.exists():
        return defaultdict(list)

    raw = scan_directory(wiki_dir, fields=["title", "type", "tags", "status"])

    groups: dict[str, list[dict]] = defaultdict(list)

    for entry in raw:
        path = Path(entry["path"])
        if is_excluded(path):
            continue

        meta = entry["metadata"]
        article_type = str(meta.get("type", "")).strip()

        # Skip index/catalog/unknown types that aren't article types
        if article_type in ("index", ""):
            continue

        title = str(meta.get("title", path.stem)).strip()
        tags = meta.get("tags", [])
        status = str(meta.get("status", "")).strip()

        groups[article_type].append({
            "title": title,
            "tags": tags,
            "status": status,
        })

    # Sort alphabetically by title within each group
    for key in groups:
        groups[key].sort(key=lambda a: a["title"].lower())

    return groups


def build_index_text(groups: dict[str, list[dict]], today: str, version: str) -> str:
    """Render the full _index.md content."""
    total = sum(len(v) for v in groups.values())

    lines: list[str] = []

    # Frontmatter
    lines += [
        "---",
        'title: "Wiki Index"',
        "type: index",
        f"updated: {today}",
        f'framework_version: "{version}"',
        "---",
        "",
    ]

    # Heading
    lines += ["# Wiki Index", ""]

    # Sections
    for type_key, label in TYPE_ORDER:
        lines.append(f"## {label}")
        articles = groups.get(type_key, [])
        if articles:
            for art in articles:
                tag_part = f" — tags: {tags_str(art['tags'])}" if art["tags"] else ""
                lines.append(f"- [[{art['title']}]]{tag_part}")
        else:
            lines.append(PLACEHOLDER.get(type_key, "*(none)*"))
        lines.append("")

    # Footer
    lines += [
        "---",
        f"*Last updated: {today} | Total articles: {total}*",
    ]

    return "\n".join(lines) + "\n"


def run_qmd_rebuild(wiki_dir: Path) -> None:
    """Run qmd collection add and qmd embed."""
    print("Rebuilding qmd collection index…")
    try:
        subprocess.run(
            ["qmd", "collection", "add", str(wiki_dir), "--name", "vault"],
            check=True,
        )
        subprocess.run(["qmd", "embed"], check=True)
        print("qmd rebuild complete.")
    except FileNotFoundError:
        print("WARNING: qmd not found — skipping qmd rebuild.", file=sys.stderr)
    except subprocess.CalledProcessError as exc:
        print(f"WARNING: qmd command failed (exit {exc.returncode}) — continuing.", file=sys.stderr)


def print_stats(groups: dict[str, list[dict]], previous_count: int) -> None:
    """Print counts by type and delta vs previous index."""
    total = sum(len(v) for v in groups.values())
    delta = total - previous_count

    print("\n--- Index Stats ---")
    for type_key, label in TYPE_ORDER:
        count = len(groups.get(type_key, []))
        if count:
            print(f"  {label}: {count}")
    print(f"  Total: {total}")

    if delta > 0:
        print(f"  Delta: +{delta} vs previous index")
    elif delta < 0:
        print(f"  Delta: {delta} vs previous index")
    else:
        print("  Delta: no change vs previous index")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate wiki/_index.md for the Seed Vault."
    )
    parser.add_argument(
        "--rebuild-qmd",
        action="store_true",
        help="Also run 'qmd collection add wiki/ --name vault && qmd embed' after writing the index.",
    )
    args = parser.parse_args()

    today = date.today().isoformat()
    version = read_version()

    # Count entries in the existing index before overwriting
    previous_count = count_previous_entries(INDEX_FILE)

    # Collect and group articles
    if not WIKI_DIR.exists():
        print(f"WARNING: wiki directory not found at {WIKI_DIR} — writing empty index.", file=sys.stderr)
        groups: dict[str, list[dict]] = {}
    else:
        groups = collect_articles(WIKI_DIR)

    # Generate index text
    index_text = build_index_text(groups, today, version)

    # Write _index.md
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(index_text, encoding="utf-8")
    print(f"Written: {INDEX_FILE}")

    # Stats
    print_stats(groups, previous_count)

    # Optional qmd rebuild
    if args.rebuild_qmd:
        run_qmd_rebuild(WIKI_DIR)


if __name__ == "__main__":
    main()
