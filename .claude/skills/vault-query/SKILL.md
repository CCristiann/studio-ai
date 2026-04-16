---
name: vault-query
description: Use when answering any question about Studio AI's architecture decisions, product vision, design rationale, component responsibilities, domain concepts, or anything asking "why did we...", "how come...", "what's the reason for..." about project choices. Also use when the user references "the vault", "obsidian docs", "our knowledge base", or mentions wanting to know the history behind a decision. READ-ONLY and token-cheap — always try this before grep-ing the codebase for design intent.
---

# Vault — Query

Studio AI has a dedicated knowledge vault at:

**`/Users/cristiancirje/Desktop/Dev/obsidian-studio-ai/`**

It captures product vision, architecture decisions (ADRs), component responsibilities, domain concepts, and source summaries — the **"why" that the code cannot express**.

## When this skill fires

- User asks about **design rationale, architecture decisions, or "why" the project looks a certain way**
- User says "the vault" / "obsidian" / "our docs" / "the wiki"
- You would otherwise start grepping the repo to find design intent — **stop, the vault probably has it**
- Question touches product strategy, component boundaries, competitor positioning, or decisions already made

## Query workflow (token-frugal)

### Step 1 — Read the index first. Always.

```bash
cat /Users/cristiancirje/Desktop/Dev/obsidian-studio-ai/index.md
```

~500 tokens. Catalogs every page with a one-line summary. Tells you exactly which 1-3 pages to read next. **Never skip this step.**

### Step 2 — Identify the right pages

Vault layout:

- `wiki/product/` — vision, phase-1-scope, roadmap (the "what" and "for whom")
- `wiki/architecture/overview.md` — topology, subsystems, data flow
- `wiki/architecture/decisions/YYYY-MM-DD-*.md` — ADRs with Context / Decision / Alternatives / Consequences
- `wiki/components/` — one page per major code unit (web-app, relay-service, vst3-plugin, fl-studio-bridge, database, midi-sysex-transport, organization-agent)
- `wiki/concepts/` — domain vocabulary (message-envelope, plugin-token-auth, webview-ipc, connection-state-machine, agentic-loops, query-key-hierarchy)
- `wiki/sources/` — summaries of external/internal sources that informed design

### Step 3 — Read only the pages you need

Usually 1-3 pages, ~1-2k tokens each. Total budget for a typical query: **3-5k tokens**.

### Step 4 — Cite paths in your answer

Always quote the vault path when referencing its content:

> "As documented in `wiki/architecture/decisions/2026-04-09-windows-ipc-midi-sysex.md`, we pivoted to MIDI SysEx because FL Studio's Python sandbox cannot create WinAPI pipes or sockets."

Makes the answer verifiable and helps the user jump there in Obsidian.

## Discipline

- **Do NOT read the whole vault.** Index + targeted drill-down. That's it.
- **Do NOT re-derive from code.** If the vault has the answer, trust it — it captures alternatives already considered.
- **Do NOT use this skill for implementation details** ("what does this function do"). Use normal code reading for that.
- **If the answer synthesizes across pages** (a comparison, a newly-noticed connection), mention: *"This could be filed back — want me to use `vault-maintain` to save it?"*
- **If the vault lacks the answer**, say so and offer: *"The vault doesn't cover this. Want me to switch to `vault-maintain` and add a page?"*

## Anti-patterns

- ❌ Reading every file in `wiki/` "for context"
- ❌ Grepping the code for design intent before checking the vault
- ❌ Paraphrasing vault content without citation
- ❌ Skipping the index and opening random pages

## Related skills

- `vault-maintain` — when the user wants to document something new
- `vault-lint` — when the user wants a health check
