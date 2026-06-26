"""
digest.py — Vault statistics generator for the Seed Vault wiki.

Fully deterministic, no LLM required.

Usage:
    uv run python _vault/lib/digest.py [--json | --markdown]

Default output is --markdown.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Vault root: this file lives at <vault>/_vault/lib/digest.py
# ---------------------------------------------------------------------------
VAULT_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = VAULT_ROOT / "wiki"
RAW_DIR = VAULT_ROOT / "raw"

# ---------------------------------------------------------------------------
# Shared helpers — single source of truth in vault_frontmatter
# ---------------------------------------------------------------------------
sys.path.append(str(VAULT_ROOT))

from _vault.lib.vault_frontmatter import (  # noqa: E402
    extract_wikilinks,
    is_meta_file,
    normalize_key,
    parse_date,
    parse_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_wiki_files() -> list[Path]:
    if not WIKI_DIR.exists():
        return []
    return [p for p in WIKI_DIR.rglob("*.md") if not is_meta_file(p)]


def _normalize_title(title_or_path) -> str:
    """Return a display title, preferring the frontmatter title field."""
    if isinstance(title_or_path, dict):
        fm = title_or_path.get("metadata", {})
        title = fm.get("title", "")
        if title:
            return str(title)
        path = Path(title_or_path.get("path", ""))
    else:
        path = Path(title_or_path)
    # Derive from filename: kebab-case → Title Case
    stem = path.stem
    return stem.replace("-", " ").replace("_", " ").title()


# ---------------------------------------------------------------------------
# Core statistics builder
# ---------------------------------------------------------------------------

def build_stats() -> dict:
    files = _collect_wiki_files()

    # --- Article metadata ---------------------------------------------------
    articles: list[dict] = []
    for p in files:
        fm = parse_file(p)
        title = fm.get("title") or p.stem.replace("-", " ").replace("_", " ").title()
        articles.append(
            {
                "path": p,
                "title": str(title),
                "type": str(fm.get("type", "unknown")).strip(),
                "status": str(fm.get("status", "unknown")).strip(),
                "tags": _coerce_list(fm.get("tags")),
                "updated": parse_date(fm.get("updated")),
                "created": parse_date(fm.get("created")),
            }
        )

    total = len(articles)

    # --- Type counts --------------------------------------------------------
    type_counts: Counter = Counter(a["type"] for a in articles)

    # --- Status counts ------------------------------------------------------
    status_counts: Counter = Counter(a["status"] for a in articles)

    # --- Recently updated (top 10) -----------------------------------------
    recently_updated = sorted(
        [a for a in articles if a["updated"]],
        key=lambda a: a["updated"],
        reverse=True,
    )[:10]

    # --- Tag frequency ------------------------------------------------------
    tag_counter: Counter = Counter()
    for a in articles:
        for tag in a["tags"]:
            tag_counter[tag.strip()] += 1

    # --- Wikilink analysis --------------------------------------------------
    # Map every identity alias (frontmatter title slug AND filename-stem slug)
    # to the article's canonical title. A link target may use either form —
    # notably the mandated aliased link [[stem|Title]] resolves on the stem —
    # so both must point at the same article or links won't register.
    alias_to_title: dict[str, str] = {}
    for a in articles:
        for alias in (normalize_key(a["title"]), normalize_key(a["path"].stem)):
            alias_to_title.setdefault(alias, a["title"])

    # Count incoming links per canonical article title; collect targets that
    # resolve to no known article for the unresolved-links report.
    incoming: Counter = Counter()
    all_link_targets: list[str] = []

    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for t in extract_wikilinks(text):
            t_clean = t.strip()
            all_link_targets.append(t_clean)
            canonical = alias_to_title.get(normalize_key(t_clean))
            if canonical is not None:
                incoming[canonical] += 1

    # Hub nodes: top-5 articles by incoming link count.
    hub_candidates = [
        (title, count) for title, count in incoming.most_common() if count > 0
    ][:5]

    # Orphans: articles with 0 incoming links.
    orphans = [a["title"] for a in articles if incoming.get(a["title"], 0) == 0]

    # Unresolved links: targets matching no known article alias. raw/ links
    # point at raw source files (not wiki articles) and are intentional.
    unresolved: set[str] = {
        t
        for t in all_link_targets
        if not t.startswith("raw/") and normalize_key(t) not in alias_to_title
    }

    # --- Knowledge gaps -----------------------------------------------------
    # Raw files without a corresponding source summary
    raw_files: list[Path] = []
    if RAW_DIR.exists():
        raw_files = list(RAW_DIR.glob("*.md")) + list(RAW_DIR.glob("*.txt"))

    source_stems = {
        p.stem.lower()
        for p in files
        if "sources" in str(p)
    }

    raw_without_summary = 0
    for rf in raw_files:
        # Heuristic: check if any source summary filename contains the raw stem
        raw_stem = rf.stem.lower()
        if not any(raw_stem in s for s in source_stems):
            raw_without_summary += 1

    singleton_tags = sum(1 for c in tag_counter.values() if c == 1)

    return {
        "generated": date.today().isoformat(),
        "total": total,
        "type_counts": dict(type_counts),
        "status_counts": dict(status_counts),
        "recently_updated": [
            {
                "title": a["title"],
                "updated": a["updated"].isoformat() if a["updated"] else None,
                "type": a["type"],
            }
            for a in recently_updated
        ],
        "hub_nodes": [{"title": t, "incoming": c} for t, c in hub_candidates],
        "orphans": orphans,
        "unresolved_links": sorted(unresolved),
        "tag_distribution": tag_counter.most_common(),
        "gaps": {
            "raw_without_summary": raw_without_summary,
            "singleton_tags": singleton_tags,
        },
    }


def _coerce_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_markdown(stats: dict) -> str:
    lines: list[str] = []
    lines.append(f"# Vault Digest — {stats['generated']}")
    lines.append("")

    # Overview
    lines.append("## Overview")
    tc = stats["type_counts"]
    sc = stats["status_counts"]
    lines.append(f"- Total articles: {stats['total']}")
    lines.append(
        f"- Concepts: {tc.get('concept', 0)} | "
        f"Sources: {tc.get('source-summary', 0)} | "
        f"Viz: {tc.get('visualization', 0)} | "
        f"Output: {tc.get('output', 0)}"
    )
    lines.append(
        f"- Status: {sc.get('draft', 0)} draft, "
        f"{sc.get('reviewed', 0)} reviewed, "
        f"{sc.get('verified', 0)} verified"
    )
    lines.append("")

    # Recently updated
    lines.append("## Recently Updated")
    if stats["recently_updated"]:
        for i, a in enumerate(stats["recently_updated"], 1):
            lines.append(f"{i}. [[{a['title']}]] — {a['updated']} ({a['type']})")
    else:
        lines.append("_No articles with updated dates found._")
    lines.append("")

    # Hub nodes
    lines.append("## Hub Nodes (most linked)")
    if stats["hub_nodes"]:
        for i, node in enumerate(stats["hub_nodes"], 1):
            lines.append(f"{i}. [[{node['title']}]] — {node['incoming']} incoming links")
    else:
        lines.append("_No hub nodes detected._")
    lines.append("")

    # Orphans
    lines.append("## Orphan Pages (no incoming links)")
    if stats["orphans"]:
        for title in sorted(stats["orphans"]):
            lines.append(f"- [[{title}]]")
    else:
        lines.append("_No orphan pages._")
    lines.append("")

    # Tag distribution
    lines.append("## Tag Distribution")
    if stats["tag_distribution"]:
        for tag, count in stats["tag_distribution"]:
            lines.append(f"- {tag}: {count} article{'s' if count != 1 else ''}")
    else:
        lines.append("_No tags found._")
    lines.append("")

    # Knowledge gaps
    lines.append("## Knowledge Gaps")
    gaps = stats["gaps"]
    lines.append(f"- {gaps['raw_without_summary']} raw files without source summaries")
    lines.append(f"- {gaps['singleton_tags']} singleton tags")
    lines.append("")

    return "\n".join(lines)


def format_json(stats: dict) -> str:
    return json.dumps(stats, indent=2, default=str)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a statistics digest of the Seed Vault wiki."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--json", action="store_true", dest="as_json", help="Output as JSON"
    )
    group.add_argument(
        "--markdown",
        action="store_true",
        dest="as_markdown",
        help="Output as Markdown (default)",
    )
    args = parser.parse_args()

    stats = build_stats()

    if args.as_json:
        print(format_json(stats))
    else:
        print(format_markdown(stats))


if __name__ == "__main__":
    main()
