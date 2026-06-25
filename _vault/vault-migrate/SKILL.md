---
name: vault-migrate
description: Migrate existing wiki articles to match the current framework version. Use when the user says "migrate", "update my wiki to the new version", "apply framework updates", "my articles are out of date", or after pulling a framework update. Detects pending migrations and runs the deterministic migration script, then handles any semantic LLM steps if required.
---

# vault-migrate — Incremental Wiki Migration

You are migrating a Seed Vault wiki from an older framework version to the current one. The heavy lifting is done by `_vault/migrate.py` — a deterministic Python script that applies structural changes (frontmatter field additions, renames, deletions) without any LLM involvement. Your role is to run the script, report results, and handle any semantic migration steps that require LLM reasoning.

**How version tracking works after a framework update:**
- `bootstrap.sh update` syncs framework paths, bumping `_vault/VERSION` to the new framework version (and then runs `migrate.py` for you)
- `.vault_version` at the vault root (gitignored, local-only) records what version the existing articles are at
- `migrate.py` reads both and applies only the migrations between those two versions
- `migrate.py` is the **single authority** on `.vault_version`. It advances the record only as far as the migrations it can FULLY apply on its own. A migration with `requires_llm: true` is **held back**: its deterministic ops run, but `.vault_version` stays at that migration's `from` until the manual step is done. This is deliberate — if the version were stamped to the target before the LLM step ran, a half-finished update would look complete and both `bootstrap.sh update` and this skill's Step 1 would silently skip the pending migration.
- After you complete the manual LLM step(s) in Step 4, you finalize the version with `uv run python _vault/migrate.py --complete`, which advances `.vault_version` to the framework version.

`bootstrap.sh update` overwrites only the paths in `_vault/manifest.txt` and never touches `wiki/`, so framework updates can't conflict with your articles. Migration is the step that brings those local articles up to the new format afterward.

> **Legacy note:** pre-3.0 vaults kept this file at `wiki/.vault_version`. `migrate.py` falls back to that location automatically if the root `.vault_version` is absent.

---

## Step 1: Version Check

Read `_vault/VERSION` (new framework version, synced by `bootstrap.sh update`) and `.vault_version` at the vault root (current vault version, reflects existing articles).

- If `.vault_version` does not exist (and neither does the legacy `wiki/.vault_version`), the vault is at `0.0.0` (new or pre-versioned)
- Compare the two versions

If they match: report "Your vault is already at framework version X.Y.Z. No migration needed." and stop.

---

## Step 2: Show the Migration Plan (Dry Run First)

Run the dry-run to show the user what will change before committing:

```bash
uv run python _vault/migrate.py --dry-run
```

Report the output to the user. If the vault is large (>50 articles), ask the user to confirm before proceeding. For small vaults you may proceed directly.

---

## Step 3: Apply Migrations

Run the migration script:

```bash
uv run python _vault/migrate.py
```

Read and report the output summary:
- Version before → after
- Articles updated / skipped / errors
- Whether a reindex is needed

If the script exits with errors, report them to the user and stop.

---

## Step 4: Handle LLM-Required Migrations (if any)

If the script output includes "⚠ N migration(s) require a semantic LLM step", read the relevant migration JSON files in `_vault/migrations/` with `"requires_llm": true`.

For each:
1. Read the `llm_instructions` field — it describes exactly what to do
2. Read the `affects` field — scope to specific article types
3. Glob only the affected directory
4. Check whether the change is already present (idempotency)
5. Apply the change as described — be surgical
6. Update `updated:` date on every file modified
7. Report: "LLM migration applied to N articles"

**Finalize the version.** Until you do this, `migrate.py` has deliberately held `.vault_version` at the pre-LLM version (so an unfinished migration can't masquerade as complete). Once every `requires_llm` step above is done, advance the record:

```bash
uv run python _vault/migrate.py --complete
```

This stamps `.vault_version` to the framework version. Skip it if any manual step is still outstanding — re-run the steps first.

### Known multi-step migrations

**2.0.0 → 3.0.0 (topic type removed):** `llm_instructions` is a list — execute each step in order.
- Delete `wiki/topics/` and any article with `type: topic`.
- Strip `[[Topic - ...]]` wikilinks from surviving article bodies.
- Drop `sources:` entries that point into `wiki/topics/`.
- Rebuild the index with `uv run python _vault/lib/index.py --rebuild-qmd`.
Log every deletion to `wiki/_log.md`.

---

## Step 5: Post-Migration

1. If `requires_reindex: true`: run `uv run python _vault/lib/index.py --rebuild-qmd`
2. Offer `vault-lint` if the user wants a health check
3. Report final summary:

```
Migration complete — YYYY-MM-DD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Vault:    X.Y.Z → A.B.C
Script:   N articles updated
LLM step: N articles updated  (or: none required)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run vault-lint to verify no issues were introduced.
```

---

## Notes

- **Dry-run mode**: If the user says "dry-run", run only Step 2 and stop
- **Scoped migration**: `uv run python _vault/migrate.py --path wiki/concepts/`
- **Rollback**: Not supported. Suggest git backup first
- **Re-running**: Idempotent — "Already current. 0 changes."
- **No content conflicts**: `bootstrap.sh update` only overwrites `_vault/manifest.txt` paths — `.vault_version` and all `wiki/` files are local-only and never overwritten by an update
- **Framework authors**: Bump `_vault/VERSION` and add a JSON file to `_vault/migrations/` — end users receive both via `bootstrap.sh update`. Migrations with `requires_llm: true` must include `llm_instructions`.
