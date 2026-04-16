---
name: vault-maintain
description: Use when the user wants to document something in the Studio AI knowledge vault. Triggers include "document this", "file an ADR", "record this decision", "add a component page", "digest this session", "ingest this article", "save this to the vault", "update the vault with...". Also use when vault-query found a gap and the user wants to fill it. Always reads the vault's own CLAUDE.md operating manual first and follows its guided-ingest flow with approval checkpoints.
---

# Vault — Maintain

The Studio AI vault at `/Users/cristiancirje/Desktop/Dev/obsidian-studio-ai/` is the project's institutional memory. Maintaining it is **disciplined, template-driven writing** — not freeform notes. The vault has its own authoritative operating manual (`CLAUDE.md`); follow it exactly.

## When this skill fires

- "Document this decision" / "file an ADR for X"
- "Add a component page for the Y service"
- "Digest this session" / "save a session summary"
- "Ingest this article / paper / spec" (user dropped something in `raw/`, or wants a URL summarized)
- "Update the vault with..."
- Follow-up after `vault-query` reports a gap

## Mandatory first step

**Read the vault's operating manual before writing anything:**

```bash
cat /Users/cristiancirje/Desktop/Dev/obsidian-studio-ai/CLAUDE.md
```

It defines: page templates (YAML frontmatter + required sections), guardrails, the guided-ingest flow with approval checkpoints, the log format, and the index conventions. **Do not write anything until you've read it.**

## Core discipline (summary — the vault's CLAUDE.md is authoritative)

1. **Identify the operation** — ingest / adr / feature / component / session / scaffold.
2. **Propose the page set** before writing: list each page that will be created or updated, one line per page explaining what goes there. Group as:
   - **New source summary** (if ingesting external source)
   - **New entity pages** — justify each (recurs in ≥2 sources, or central treatment)
   - **Updated pages** — one-line note on what changes
3. **Wait for approval** unless the user explicitly said "autonomous" / "just do it" / "go".
4. **Follow the templates** for frontmatter and sections exactly. Use the templates from the vault's CLAUDE.md — don't invent new shapes.
5. **Maintain bidirectional wikilinks**: if page A links to B, make sure B's "Related" section mentions A.
6. **Update `index.md`** — add new pages to the correct section, alphabetical, with a one-line summary.
7. **Append to `log.md`** — `## [YYYY-MM-DD] <op> | <title>` + 1-3 line note on what was touched.

## Writing quality bar

- **Dense and specific.** No generic filler ("This is an important component that does important things"). Cut it.
- **Don't duplicate code.** Reference repo file paths (`apps/api/services/connection_manager.py:42`) instead of embedding implementation blocks. The vault holds intent, the code holds implementation.
- **Every entity page** must have at least one inbound link from a source or another entity — otherwise it's an orphan.
- **Every ADR** must name the alternatives considered with reasons why rejected. This is the value-add over a commit message.
- **For ingests**: the source summary page owns the TL;DR. Entity pages extract and generalize — they're not just copies of the source.

## Token budget

Ingesting one source typically touches 5-15 pages. Be efficient:

- Read the source once, thoroughly.
- Propose the full page set in a single message.
- **Batch writes in parallel** — multiple Write calls in one tool-use block, not sequential.
- Update `index.md` + `log.md` at the end, once.

## Escalate to brainstorming when the user is unsure

If the user is unclear about *what* to document (e.g. "I want to record something about how we approach onboarding but I'm not sure what exactly"), stop. Don't write a vague page. Either:
- Ask a few targeted questions to clarify scope.
- Suggest the user uses `superpowers:brainstorming` first to figure out what they mean, then come back here.

## Anti-patterns

- ❌ Writing without proposing the page set first
- ❌ Copying large code blocks into wiki pages
- ❌ Creating thin stub pages "to fill out later"
- ❌ Forgetting to update `index.md` and `log.md`
- ❌ Breaking bidirectional linking ("page A links to B" but B has no back-link)
- ❌ Ignoring the template frontmatter (Dataview queries depend on it)

## Related skills

- `vault-query` — read-only Q&A
- `vault-lint` — periodic health check (run before big ingest sessions)
