---
name: seed-ingest
description: Ingest raw source documents into a Seed Vault wiki. Use this skill whenever the user says "ingest", "add this source", "import this", "convert to markdown", "add to the wiki", "process this PDF", "process this article", "process this URL", "clip this page", or drops a file path or URL and wants it added to the vault. Handles PDFs, HTML files, plain text, and web URLs. Converts them to structured markdown in raw/ and creates corresponding source summaries in wiki/sources/.
---

# seed-ingest — Raw Source Ingestion

You are ingesting a source document into the Seed Vault wiki. Your job is to:
1. Extract clean content from the source
2. Save it to `raw/` as structured markdown
3. Create a source summary in `wiki/sources/`
4. Update `wiki/_index.md` and `wiki/_catalog.md`

---

## Step 0: Read Framework Version

Read `_seeds/VERSION` once at the start of this session. Note the version string — you will use it for the `framework_version:` field in every source summary you write.

---

## Step 1: Identify the Source

Determine what was provided:
- **File path to PDF**: Use the Read tool directly on the `.pdf` file first — Claude can read PDFs natively. If Read returns an error or garbled output, fall back to `pdftotext "path/to/file.pdf" -` via Bash. If pdftotext is also unavailable, ask the user to paste the text.
- **File path to .html or .md**: Read directly with the Read tool
- **YouTube URL** (`youtube.com/watch` or `youtu.be/`): See YouTube handling below
- **URL**: Use WebFetch to retrieve the page content. If WebFetch fails or returns empty content, automatically retry via the Wayback Machine: `WebFetch https://web.archive.org/web/2*/{{url}}` before giving up.
- **Plain text / already in raw/**: Read directly

If multiple sources are provided, process them one at a time and report progress.

### YouTube URLs

If the URL is a YouTube video:
1. Extract the video ID from the URL (e.g., `youtube.com/watch?v=VIDEOID` or `youtu.be/VIDEOID`)
2. Try fetching a transcript: `WebFetch https://youtranscript.vercel.app/api?videoId={{VIDEOID}}`
3. If the transcript service is unavailable, ask the user to paste the auto-generated transcript (YouTube → "..." → "Show transcript")
4. Use the video title as the source title; set `original_format: youtube-transcript` in the raw file

---

## Step 2: Extract and Clean Content

For **PDFs**:
- Run: `pdftotext "{{filepath}}" -`
- Clean up hyphenation artifacts, page headers/footers, column-merge issues
- Preserve section structure as markdown headings

For **HTML/URLs**:
- Use WebFetch on the URL
- Strip navigation, ads, footers — keep only article body
- Preserve the heading hierarchy as `#`, `##`, `###`
- Keep tables as markdown tables
- Keep code blocks as fenced code blocks
- Convert image alt-text to `![alt](url)` references

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
original_format: pdf | html | url | text | youtube-transcript
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
framework_version: "{{read from _seeds/VERSION}}"
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
- [[Another Concept]] *(exists | needs article)*

## Raw Source
[[raw/{{name}}]]
```

To find existing concept articles for the "Concepts Extracted" section:
1. Read `wiki/_catalog.md` to see what concepts already exist
2. Link to any that match — mark others as "needs article"

---

## Step 6: Update Index and Catalog

**Append to `wiki/_index.md`** under the `## Source Summaries` section:
```
- [[Summary: {{Full Title}}]] — {{one-line description}}
```

**Append to `wiki/_catalog.md`**:
```markdown
### [[Summary: {{Full Title}}]]
Type: source-summary
Tags: {{tags}}
Summary: {{2–3 sentences covering the source's main claims, methods, and relevance.}}
```

Also update the `*Last updated*` line in `_index.md`.

---

## Step 7: Report

After ingestion, report:
- Source saved to: `raw/{{name}}.md`
- Summary created: `wiki/sources/summary-{{name}}.md`
- New concepts flagged: (list any "needs article" concepts)
- Suggest next step: "Run `seed-compile` to create articles for the flagged concepts."

---

## Error Handling

- **PDF Read fails**: Fall back to `pdftotext "path" -` via Bash. If that also fails, ask the user to install poppler-utils (`sudo apt install poppler-utils`) or provide the text manually.
- **URL fetch fails**: Automatically retry via Wayback Machine (`WebFetch https://web.archive.org/web/2*/{{url}}`). If that also fails, ask the user to paste the article text directly.
- **YouTube transcript fetch fails**: Ask user to paste the transcript from YouTube's "Show transcript" panel (video page → "..." menu → "Show transcript").
- **File not found**: Ask user to confirm the path
- **Ambiguous title**: Use the filename as a fallback title, ask user to confirm
