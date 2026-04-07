---
name: vault-ingest
description: Ingest raw source documents into the wiki. Use when the user says "ingest", "add this source", "import this", "convert to markdown", "add to the wiki", "process this PDF/article/URL", or drops a file path or URL. Handles PDFs, HTML, DOCX, EPUB, RTF, plain text, URLs, and YouTube transcripts. Converts to structured markdown in raw/ and creates source summaries in wiki/sources/.
---

# vault-ingest — Raw Source Ingestion

You are ingesting a source document into the Seed Vault wiki. Your job is to:
1. Convert non-markdown files using the deterministic engine
2. Extract clean content from the source
3. Save it to `raw/` as structured markdown
4. Create a source summary in `wiki/sources/`
5. Update `wiki/_index.md`

---

## Step 0: Read Framework Version

Read `_vault/VERSION` once at the start of this session. Note the version string — you will use it for the `framework_version:` field in every source summary you write.

---

## Step 1: Identify and Convert the Source

Determine what was provided:

### File paths (PDF, HTML, DOCX, EPUB, RTF)

**Run the deterministic conversion engine first:**
```bash
uv run python _vault/lib/convert.py "{{filepath}}" raw/
```

This converts the file to markdown in `raw/` with basic frontmatter (title, original_format, ingested date). If the conversion fails or produces garbled output, fall back to manual extraction:

- **PDF**: Use the Read tool directly on the `.pdf` file — Claude can read PDFs natively. If Read returns an error, fall back to `pdftotext "path/to/file.pdf" -` via Bash.
- **HTML**: Read directly with the Read tool
- **DOCX/EPUB/RTF**: If convert.py failed, ask the user to export as PDF or paste the text

### File path to .md or .txt
Read directly — no conversion needed.

### YouTube URL (`youtube.com/watch` or `youtu.be/`)
1. Extract the video ID from the URL
2. Try fetching a transcript: `WebFetch https://youtranscript.vercel.app/api?videoId={{VIDEOID}}`
3. If unavailable, ask the user to paste the auto-generated transcript
4. Use the video title as the source title; set `original_format: youtube-transcript`

### URL
Use WebFetch to retrieve the page content. If WebFetch fails or returns empty content, automatically retry via the Wayback Machine: `WebFetch https://web.archive.org/web/2*/{{url}}` before giving up.

### Plain text / already in raw/
Read directly.

If multiple sources are provided, process them one at a time and report progress.

---

## Step 2: Extract and Clean Content

For **PDFs** (if convert.py output needs cleanup):
- Clean up hyphenation artifacts, page headers/footers, column-merge issues
- Preserve section structure as markdown headings

For **HTML/URLs**:
- Strip navigation, ads, footers — keep only article body
- Preserve the heading hierarchy as `#`, `##`, `###`
- Keep tables as markdown tables
- Keep code blocks as fenced code blocks

For **plain text**:
- Read as-is, add minimal markdown structure

---

## Step 3: Determine the File Name

Create a kebab-case file name from the title:
- "The CRISPR Revolution in Gene Editing" → `crispr-revolution-gene-editing`
- Strip articles (the, a, an) from the start
- Max 6 words

Check if `raw/{{name}}.md` already exists. If so, ask the user whether to overwrite or create `{{name}}-2.md`.

---

## Step 4: Save to raw/

Write `raw/{{name}}.md` with this structure:

```markdown
---
title: "{{Full Title}}"
original_format: pdf | html | url | text | youtube-transcript | docx | epub
source_url: "{{url if applicable}}"
author: "{{author if found}}"
publication: "{{journal/site if found}}"
date_published: "{{date if found}}"
ingested: {{today YYYY-MM-DD}}
---

{{cleaned markdown content}}
```

Never truncate or summarize the raw content — preserve everything.

---

## Step 5: Create Source Summary in wiki/sources/

Write `wiki/sources/summary-{{name}}.md`:

```markdown
---
title: "Summary: {{Full Title}}"
type: source-summary
created: {{today}}
updated: {{today}}
original_source: "[[raw/{{name}}]]"
source_url: "{{url}}"
author: "{{author}}"
tags: [{{inferred tags}}]
status: draft
llm_model: "{{your model ID, e.g. claude-sonnet-4-6 or gemini-2.5-pro}}"
framework_version: "{{read from _vault/VERSION}}"
---

# {{Full Title}}

## Key Takeaways
*(3–7 bullet points — the most important claims or findings)*

-

## Detailed Summary
*(2–4 paragraphs synthesizing the content)*

## Concepts Extracted
*(List concepts this source informs, as [[wikilinks]] — link to existing concept articles if they exist, or flag new ones needed)*

- [[Concept Name]] *(exists | needs article)*

## Raw Source
[[raw/{{name}}]]
```

To find existing concept articles for the "Concepts Extracted" section:
1. Run `qmd query "{{topic keywords}}"` if qmd is available, OR
2. Read `wiki/_index.md` to see what concepts already exist
3. Link to any that match — mark others as "needs article"

---

## Step 6: Update Index

**Rebuild the index** using the deterministic engine:
```bash
uv run python _vault/lib/index.py
```

Or if you prefer a targeted update, manually append to `wiki/_index.md` under the `## Source Summaries` section:
```
- [[Summary: {{Full Title}}]] — {{one-line description}}
```

Also update the `*Last updated*` line in `_index.md`.

---

## Step 7: Log and Report

Append to `wiki/_log.md`:
```
[{{today}} ingest] raw/{{name}}.md → wiki/sources/summary-{{name}}.md
```

Report:
- Source saved to: `raw/{{name}}.md`
- Summary created: `wiki/sources/summary-{{name}}.md`
- New concepts flagged: (list any "needs article" concepts)
- Suggest next step: "Run `vault-compile` to create articles for the flagged concepts."

---

## Error Handling

- **PDF conversion fails**: Fall back to Claude's native PDF Read, then `pdftotext "path" -` via Bash, then ask user for text
- **URL fetch fails**: Automatically retry via Wayback Machine. If that also fails, ask the user to paste the article text
- **YouTube transcript fails**: Ask user to paste from YouTube's "Show transcript" panel
- **File not found**: Ask user to confirm the path
- **Ambiguous title**: Use the filename as a fallback title, ask user to confirm
