"""Integrity tests for _vault/migrations/*.json."""
from __future__ import annotations

import json
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = VAULT_ROOT / "_vault" / "migrations"
VERSION_FILE = VAULT_ROOT / "_vault" / "VERSION"


def _load_all() -> list[dict]:
    migs = []
    for p in sorted(MIGRATIONS_DIR.glob("*.json")):
        migs.append(json.loads(p.read_text(encoding="utf-8")))
    return migs


def _semver(v: str) -> tuple[int, int, int]:
    return tuple(int(x) for x in v.split("."))  # type: ignore[return-value]


def test_every_migration_has_required_fields():
    required = {"from", "to", "description", "operations", "requires_llm", "requires_reindex"}
    for mig in _load_all():
        missing = required - set(mig)
        assert not missing, f"{mig.get('to','?')} missing fields: {missing}"


def test_migration_chain_continuous_from_0_to_current():
    current = VERSION_FILE.read_text(encoding="utf-8").strip()
    migs = sorted(_load_all(), key=lambda m: _semver(m["to"]))
    assert migs, "no migration specs found"
    assert migs[0]["from"] == "0.0.0", "chain must start from 0.0.0"

    for prev, nxt in zip(migs, migs[1:]):
        assert prev["to"] == nxt["from"], (
            f"gap in migration chain: {prev['to']} !=> {nxt['from']}"
        )

    assert migs[-1]["to"] == current, (
        f"latest migration ({migs[-1]['to']}) does not match _vault/VERSION ({current})"
    )


def test_llm_migrations_include_llm_instructions():
    for mig in _load_all():
        if mig.get("requires_llm"):
            assert "llm_instructions" in mig, f"{mig['from']}->{mig['to']} missing llm_instructions"
            value = mig["llm_instructions"]
            assert isinstance(value, (str, list)) and value, (
                f"{mig['from']}->{mig['to']} llm_instructions must be non-empty str or list"
            )


def test_3_0_0_migration_covers_topic_removal():
    """Spec check — the 3.0.0 migration must reference topic artifacts."""
    target = next((m for m in _load_all() if m.get("to") == "3.0.0"), None)
    assert target is not None, "2.0.0-to-3.0.0 migration missing"
    assert target["requires_llm"] is True
    assert target["requires_reindex"] is True
    joined = " ".join(target["llm_instructions"]) if isinstance(target["llm_instructions"], list) else target["llm_instructions"]
    # The migration spec must mention these artifacts so the LLM knows what to clean up.
    for keyword in ("wiki/topics", "type", "Topic"):
        assert keyword in joined, f"migration spec missing keyword {keyword!r}"


def test_operations_use_known_ops():
    known = {"add_field", "set_field", "rename_field_value", "delete_field"}
    for mig in _load_all():
        for op in mig.get("operations", []):
            assert op["op"] in known, f"unknown op {op['op']!r} in {mig['from']}->{mig['to']}"
