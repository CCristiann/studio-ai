---
name: vault-lint
description: Use when the user asks to lint, audit, or health-check the Studio AI knowledge vault. Triggers include "lint the vault", "audit our knowledge base", "check the vault health", "is the vault consistent", "find orphan pages", "any broken links in the vault". Produces a written report only — NEVER auto-edits without approval. Delegates fixes to vault-maintain after user confirms.
---

# Vault — Lint

Health check pass for the Studio AI vault at `/Users/cristiancirje/Desktop/Dev/obsidian-studio-ai/`. **Produces a written report only.** Does not edit.

## When this skill fires

- "Lint the vault" / "audit the vault"
- "Is the vault still consistent"
- "Check for orphan pages" / "find broken wikilinks"
- Periodic review (e.g. monthly)
- Before a big ingest session (clean the slate first)

## Checks to run

1. **Broken wikilinks** — `[[Page]]` pointing to non-existent files. Critical.
2. **Orphan pages** — entity pages in `wiki/` with no inbound wikilinks. Warning.
3. **Missing back-links** — page A links to B but B's "Related" section doesn't mention A. Warning.
4. **Stub pages** — pages with fewer than ~3 non-empty sections. Warning.
5. **Components without feature links** (and vice versa, once features exist). Suggestion.
6. **ADRs missing `status`** or without linked components. Warning.
7. **Sources not linked from any entity page.** Warning.
8. **Stale `status: current` product pages** older than 3 months → suggestion to revisit.
9. **Competitor pages** with `last_reviewed` frontmatter older than 3 months.
10. **Filesystem vs index.md drift** — files that exist but aren't in `index.md`, or index entries pointing to missing files. Critical.

## Tools to use

```bash
# All markdown files in the vault
find /Users/cristiancirje/Desktop/Dev/obsidian-studio-ai/wiki -name "*.md"

# All wikilinks across the vault (dedup'd)
grep -roh "\[\[[^]]*\]\]" /Users/cristiancirje/Desktop/Dev/obsidian-studio-ai/wiki | sort -u

# Recent log activity
grep "^## \[" /Users/cristiancirje/Desktop/Dev/obsidian-studio-ai/log.md | tail -10

# Files referenced in index.md
grep -oh "\[\[[^]]*\]\]" /Users/cristiancirje/Desktop/Dev/obsidian-studio-ai/index.md
```

## Report format

Group by severity:

### Critical (fix first)
- Broken wikilinks (target file missing)
- Files in `wiki/` not indexed in `index.md`
- Index entries pointing to deleted files

### Warning (address soon)
- Orphan pages
- Stub content (< 3 sections filled)
- Missing back-links
- ADRs without linked components
- Sources not linked from any entity

### Suggestion (nice-to-have)
- Stale `last_reviewed` dates
- Thin concept pages
- Features pages missing for completed work

**For each finding give:** what's wrong · which file(s) · a one-line suggested fix.

## After the report

**Do not auto-edit.** Ask the user:

> "Want me to apply these fixes? I'll switch to `vault-maintain` to do it properly."

Then only if they approve, delegate the fix flow.

## Token budget

Lint is I/O-heavy. Aim for **under 20k tokens total**:

- Use `grep` / `find` first to scope problems — don't read every file.
- Only read the content of pages that are candidates for a finding.
- Produce a structured report, not a page-by-page dump.
- Use the Agent tool (Explore subagent) for the initial sweep if the vault has grown large (>50 pages).

## Anti-patterns

- ❌ Reading every page end-to-end just to check for stubs
- ❌ Auto-fixing broken links without asking
- ❌ Generating a report so long it's unreadable — prioritize and summarize
- ❌ Running lint during small, focused writing sessions (waste of tokens)

## Related skills

- `vault-query` — read-only Q&A
- `vault-maintain` — apply fixes after approval
