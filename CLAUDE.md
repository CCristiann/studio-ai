# Studio AI

Monorepo: `apps/web` (Next.js), `apps/api` (FastAPI relay), `bridge/fl_studio` (Python IPC), `plugin` (Rust WebView).

## Dev servers

```bash
./dev.sh                    # all services (Redis + FastAPI :8000 + Next.js :3000)
```

Manual per-service commands live in `dev.sh` if you need to run one in isolation.

## apps/web — data fetching

Client-side reads/writes go through **TanStack Query v5** using a three-layer split. Do not reintroduce raw `fetch + useState + useEffect` patterns in client components.

### Three-layer pattern

```
lib/query/api/<resource>.ts       # typed fetch functions, throw ApiError on non-ok
lib/query/queries/<resource>.ts   # queryOptions() factories
hooks/mutations/use-*-mutations.ts # useMutation hooks w/ invalidation
```

- Query keys are hierarchical tuples: `['presets', 'all']`, `['preferences', 'all']`, `['auth', 'validate', token]`.
- API functions unwrap response envelopes (`{ presets: [...] }` → `Preset[]`) so components see clean types.
- All non-ok responses throw `ApiError` (`lib/query/errors.ts`) with `status` + `body`. Global 401 handling in `lib/query/client.ts` clears the token and redirects to `/plugin`.

### Plugin auth

The plugin route tree (`app/(plugin)/`) is wrapped in `PluginAuthProvider`. Always read the token via `usePluginToken()` — never pass `token` as a prop, never touch `localStorage.getItem('studio-ai-token')` directly.

- Mutations needing auth use the `useRequiredToken()` helper (see `use-preset-mutations.ts`). Never use `token!` non-null assertions.
- `clearToken()` handles: localStorage removal, state reset, `queryClient.clear()`, and IPC notification. Call it instead of replicating any of those steps.

### Explicitly not migrated to TanStack Query

- `useChat` (Vercel AI SDK) — streaming chat, not a good fit
- IPC 5s connection-status polling in `plugin-dashboard.tsx` — it's `window.sendToPlugin`, not HTTP
- Server actions in `login/page.tsx` and `link/page.tsx`
- Dashboard server components in `app/(dashboard)/dashboard/` — still server-fetches from Supabase

Do not migrate these without explicit discussion.

### Docs

- Design: `docs/superpowers/specs/2026-04-14-tanstack-query-design.md`
- Plan: `docs/superpowers/plans/2026-04-14-tanstack-query.md`

## Future work

When the dashboard (`app/(dashboard)/dashboard/`) gains interactive features that need client-side queries, apply the same three-layer pattern.

_All deferred follow-ups from the 2026-04-14 migration audit (I3, I4, I5, M1, M5) are shipped — see commits on `main` and the 2026-04-15 security-audit session note in the vault._

## Conventions

- Client components: keep them as thin as possible; push data fetching into query hooks, not inline `fetch`.
- Commit messages follow `type(scope): subject`. Types in use: `feat`, `fix`, `refactor`, `chore`, `docs`.
- Run `cd apps/web && bunx tsc --noEmit` before committing — this repo uses **bun** for the TypeScript toolchain, not npm/npx.

## Knowledge vault

The project's institutional memory — product vision, architecture decisions (ADRs), component rationale, domain concepts, and source summaries — lives in a separate Obsidian vault at:

**`/Users/cristiancirje/Desktop/Dev/obsidian-studio-ai/`**

Three project-level skills in `.claude/skills/` mediate access:

- **`vault-query`** — read-only Q&A ("why did we X?", "what's the rationale for Y?"). Reads `index.md` first (~500 tokens), drills into 1-3 specific pages. Use this **before** grep-ing the repo for design intent.
- **`vault-maintain`** — file ADRs, document components, digest sessions, ingest sources. Reads the vault's own `CLAUDE.md` operating manual and follows its guided-ingest flow.
- **`vault-lint`** — periodic health check (orphan pages, broken wikilinks, stale content). Report-only; delegates fixes to `vault-maintain`.

**Prefer the vault over grep for design rationale.** Code shows *how*; the vault shows *why*.
