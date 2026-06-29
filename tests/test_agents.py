"""Structural/contract tests for the context-bounded agent profiles and the
install.sh block that links them into .claude/agents/.

Two layers, mirroring the rest of the suite:

1. **Contract tests** (pure, no side effects): every `_vault/agents/<name>.md`
   (except SPEC.md) has valid frontmatter, the right model tier, the read-only
   invariant holds, and every skill an agent calls actually exists. Frontmatter
   is parsed with the repo's own helper (`vault_frontmatter.parse_file`, backed
   by python-frontmatter) — no new dependency, same path the engines use.

2. **install.sh behavioural test** (subprocess, black-box): the real agent-install
   block is sliced out of `_vault/install.sh` and run against a temp framework
   tree — the same isolation strategy test_bootstrap.py uses to exercise shell
   installers without their heavy side effects (uv sync, qmd, antigravity).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from _vault.lib.vault_frontmatter import parse_file

# --- Locations --------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = REPO_ROOT / "_vault" / "agents"
INSTALL_SH = REPO_ROOT / "_vault" / "install.sh"
PIPELINE_SKILL = REPO_ROOT / "_vault" / "vault-pipeline" / "SKILL.md"
GITIGNORE = REPO_ROOT / ".gitignore"

# The five agent profiles and their pinned model tier.
EXPECTED_MODELS = {
    "source-ingestor": "sonnet",
    "wiki-synthesizer": "opus",
    "clean-room-verifier": "haiku",
    "visualizer": "sonnet",
    "qa-responder": "haiku",
}
EXPECTED_AGENTS = set(EXPECTED_MODELS)
VALID_TIERS = {"sonnet", "opus", "haiku"}
# Agents that must never carry mutating tools.
READ_ONLY_AGENTS = {"clean-room-verifier", "qa-responder"}
REQUIRED_KEYS = {"name", "description", "tools", "model"}
# Agents the pipeline orchestrates via subagent_type.
PIPELINE_AGENTS = {"source-ingestor", "wiki-synthesizer", "clean-room-verifier"}

# The filter install.sh applies when deciding what is an installable agent.
SPEC_FILENAME = "SPEC.md"


def _agent_files() -> list[Path]:
    """Every installable agent profile — the SPEC.md doc is excluded, exactly as
    install.sh excludes it."""
    return sorted(p for p in AGENTS_DIR.glob("*.md") if p.name != SPEC_FILENAME)


def _tools_set(metadata: dict) -> set[str]:
    """The `tools:` frontmatter is a comma-separated scalar (e.g.
    'Read, Write, Edit'); split it into a set of tool names."""
    raw = metadata.get("tools", "")
    return {tok.strip() for tok in str(raw).split(",") if tok.strip()}


# ── Discovery / SPEC exclusion ────────────────────────────────────────────────

def test_exactly_the_five_expected_agents_present():
    """The agents dir holds exactly the five known profiles (plus the SPEC doc)."""
    stems = {p.stem for p in _agent_files()}
    assert stems == EXPECTED_AGENTS


def test_spec_doc_exists_but_is_excluded_from_agent_set():
    """SPEC.md ships in the dir but must never be treated as an agent profile."""
    assert (AGENTS_DIR / SPEC_FILENAME).is_file()
    assert SPEC_FILENAME not in {p.name for p in _agent_files()}


def test_spec_doc_is_not_a_valid_agent_profile():
    """SPEC.md has no agent frontmatter — proves the filename filter, not luck,
    is what keeps it out (parsing it would yield no name/model)."""
    meta = parse_file(AGENTS_DIR / SPEC_FILENAME)
    assert not REQUIRED_KEYS.issubset(meta.keys())


# ── Frontmatter contract ──────────────────────────────────────────────────────

@pytest.mark.parametrize("agent", sorted(EXPECTED_AGENTS))
def test_frontmatter_has_required_keys(agent):
    """Each profile parses into a dict carrying name, description, tools, model."""
    meta = parse_file(AGENTS_DIR / f"{agent}.md")
    assert isinstance(meta, dict)
    missing = REQUIRED_KEYS - meta.keys()
    assert not missing, f"{agent}.md missing frontmatter keys: {missing}"


@pytest.mark.parametrize("agent", sorted(EXPECTED_AGENTS))
def test_name_field_matches_filename_stem(agent):
    """A subagent is spawned by `name`, so name must equal the file stem or the
    profile can never be resolved by install.sh / the Agent tool."""
    meta = parse_file(AGENTS_DIR / f"{agent}.md")
    assert meta.get("name") == agent


@pytest.mark.parametrize("agent,expected_model", sorted(EXPECTED_MODELS.items()))
def test_model_is_expected_lowercase_tier(agent, expected_model):
    """model must be the pinned lowercase tier alias for that agent."""
    meta = parse_file(AGENTS_DIR / f"{agent}.md")
    model = meta.get("model")
    assert model in VALID_TIERS, f"{agent}: model {model!r} not a tier alias"
    assert model == expected_model


# ── Read-only invariant ───────────────────────────────────────────────────────

@pytest.mark.parametrize("agent", sorted(READ_ONLY_AGENTS))
def test_readonly_agents_cannot_write_or_edit(agent):
    """clean-room-verifier and qa-responder are read-only by design — granting
    Write/Edit would let them mutate the wiki they only inspect."""
    tools = _tools_set(parse_file(AGENTS_DIR / f"{agent}.md"))
    assert "Write" not in tools, f"{agent} must not have Write"
    assert "Edit" not in tools, f"{agent} must not have Edit"


@pytest.mark.parametrize("agent", sorted(EXPECTED_AGENTS - READ_ONLY_AGENTS))
def test_authoring_agents_have_write(agent):
    """The three authoring agents do produce files, so Write must be present."""
    tools = _tools_set(parse_file(AGENTS_DIR / f"{agent}.md"))
    assert "Write" in tools, f"{agent} should have Write"


# ── Skill-reference integrity ─────────────────────────────────────────────────

@pytest.mark.parametrize("agent", sorted(EXPECTED_AGENTS))
def test_referenced_vault_skills_exist(agent):
    """Every `vault-*` skill an agent body names must map to a real
    _vault/vault-*/ dir with a SKILL.md — catches a typo'd skill reference."""
    text = (AGENTS_DIR / f"{agent}.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"vault-[a-z]+", text))
    assert referenced, f"{agent} references no vault-* skill at all"
    for skill in referenced:
        skill_md = REPO_ROOT / "_vault" / skill / "SKILL.md"
        assert skill_md.is_file(), f"{agent} references missing skill {skill}"


# ── Pipeline orchestration wiring ─────────────────────────────────────────────

@pytest.mark.parametrize("agent", sorted(PIPELINE_AGENTS))
def test_pipeline_skill_spawns_agent_by_subagent_type(agent):
    """vault-pipeline must reference each pipeline agent via subagent_type, or the
    orchestration described in the spec is not actually wired up."""
    text = PIPELINE_SKILL.read_text(encoding="utf-8")
    assert f'subagent_type="{agent}"' in text or f"subagent_type: \"{agent}\"" in text


def test_gitignore_ignores_generated_agent_links():
    """The .claude/agents/ symlinks are generated artifacts, not source."""
    assert ".claude/agents/" in GITIGNORE.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# install.sh agent-install block — behavioural (subprocess) tests
# ─────────────────────────────────────────────────────────────────────────────


def _extract_agent_block() -> str:
    """Slice the real agent-install logic out of install.sh.

    The block is self-contained: it opens at `AGENTS_SRC_DIR=...` and closes at
    the first column-0 `fi` (the inner if/elif/else fis are all indented). It
    depends only on SCRIPT_DIR and VAULT_ROOT, which the harness supplies — so we
    exercise the shipped shell code, not a reimplementation of it.
    """
    lines = INSTALL_SH.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("AGENTS_SRC_DIR="))
    end = next(i for i, ln in enumerate(lines) if i > start and re.match(r"^fi\s*$", ln))
    return "\n".join(lines[start : end + 1])


def _run_agent_install(vault_root: Path) -> subprocess.CompletedProcess:
    """Run the extracted block with SCRIPT_DIR/VAULT_ROOT pointed at a temp tree."""
    script = "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -e",
            f'SCRIPT_DIR="{vault_root / "_vault"}"',
            f'VAULT_ROOT="{vault_root}"',
            _extract_agent_block(),
            "",
        ]
    )
    runner = vault_root / "_run_agent_install.sh"
    runner.write_text(script, encoding="utf-8")
    return subprocess.run(
        ["bash", str(runner)],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def agent_tree(tmp_path: Path) -> Path:
    """A temp framework tree: real _vault/agents/ (incl. SPEC.md) copied in."""
    shutil.copytree(AGENTS_DIR, tmp_path / "_vault" / "agents")
    return tmp_path


class TestInstallAgentBlock:
    def test_installs_exactly_five_symlinks_and_no_spec(self, agent_tree):
        r = _run_agent_install(agent_tree)
        assert r.returncode == 0, r.stderr

        links_dir = agent_tree / ".claude" / "agents"
        installed = {p.name for p in links_dir.iterdir()}
        assert installed == {f"{a}.md" for a in EXPECTED_AGENTS}
        assert "SPEC.md" not in installed
        assert all((links_dir / name).is_symlink() for name in installed)

    def test_symlinks_are_relative_and_resolve_to_source(self, agent_tree):
        r = _run_agent_install(agent_tree)
        assert r.returncode == 0, r.stderr

        links_dir = agent_tree / ".claude" / "agents"
        for agent in EXPECTED_AGENTS:
            link = links_dir / f"{agent}.md"
            target = os.readlink(link)
            assert target == f"../../_vault/agents/{agent}.md", target
            assert not os.path.isabs(target), "link must be relative, not absolute"
            # And it must actually resolve back to the real source file.
            expected = (agent_tree / "_vault" / "agents" / f"{agent}.md").resolve()
            assert link.resolve() == expected

    def test_idempotent_no_duplicates_no_real_files(self, agent_tree):
        first = _run_agent_install(agent_tree)
        assert first.returncode == 0, first.stderr

        second = _run_agent_install(agent_tree)
        assert second.returncode == 0, second.stderr
        # A re-run reports the links are already current and creates nothing new.
        assert "Current" in second.stdout
        assert "installed: 0" in second.stdout

        links_dir = agent_tree / ".claude" / "agents"
        entries = list(links_dir.iterdir())
        assert len(entries) == len(EXPECTED_AGENTS), "re-run must not duplicate links"
        assert all(p.is_symlink() for p in entries), "no entry may become a real file"
