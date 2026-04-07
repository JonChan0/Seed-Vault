---
name: vault-migrate
description: Migrate existing wiki articles to match the current framework version. Use when the user says "migrate", "update my wiki to the new version", "apply framework updates", "my articles are out of date", or after pulling a framework update. Detects pending migrations and runs the deterministic migration script, then handles any semantic LLM steps if required.
---

# vault-migrate — Incremental Wiki Migration

You are migrating a Seed Vault wiki from an older framework version to the current one. The heavy lifting is done by `_vault/migrate.py` — a deterministic Python script that applies structural changes (frontmatter field additions, renames, deletions) without any LLM involvement. Your role is to run the script, report results, and handle any semantic migration steps that require LLM reasoning.

---

## Step 1: Version Check

Read `_vault/VERSION` and `wiki/_index.md` frontmatter.

- If `wiki/_index.md` has no `framework_version:` field, the vault is at `0.0.0`
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
- **Framework authors**: Bump `_vault/VERSION`, add JSON to `_vault/migrations/`. Migrations with `requires_llm: true` must include `llm_instructions`.
