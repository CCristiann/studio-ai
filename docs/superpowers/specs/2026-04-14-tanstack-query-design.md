# TanStack React Query Integration

**Date:** 2026-04-14
**Status:** Approved
**Scope:** Client-side query infrastructure + plugin migration. Dashboard stays server-rendered but infrastructure is ready for future adoption.

---

## 1. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `@tanstack/react-query` | ^5 | Core query/mutation library |
| `@tanstack/react-query-devtools` | ^5 | Dev-only inspector (tree-shaken in prod) |

No other dependencies. The existing `@ai-sdk/react` (`useChat`) is unaffected and remains as-is.

---

## 2. Folder Structure

```
src/
├── lib/
│   └── query/
│       ├── client.ts              # makeQueryClient, getQueryClient, global error config
│       ├── errors.ts             # ApiError class
│       ├── api/                   # Plain fetch functions (no React)
│       │   ├── presets.ts         # fetchPresets, createPreset, updatePreset, deletePreset
│       │   ├── preferences.ts    # fetchPreferences, updatePreferences
│       │   └── auth.ts           # validateToken, initiateDeviceFlow, pollDeviceToken
│       └── queries/              # queryOptions factories (keys + queryFn together)
│           ├── presets.ts        # presetQueries.all
│           ├── preferences.ts   # preferencesQueries.all
│           └── auth.ts          # authQueries.validate, authQueries.deviceToken
├── hooks/
│   ├── use-plugin-auth.ts        # PluginAuthProvider context + usePluginToken hook
│   └── mutations/                # useMutation wrappers with cache invalidation
│       ├── use-preset-mutations.ts
│       ├── use-preferences-mutations.ts
│       └── use-device-auth-mutations.ts  # useInitiateDeviceFlow
├── components/
│   └── providers.tsx             # QueryClientProvider + ReactQueryDevtools (updated)
```

### Rationale

- **`api/`** — Pure functions. No React imports. Accept token as parameter. Return typed data. Fully unit-testable without React.
- **`queries/`** — `queryOptions()` factories that bind keys to fetch functions. Single source of truth for "what key fetches what data." Components never construct keys manually.
- **`hooks/mutations/`** — Thin wrappers around `useMutation` that handle cache invalidation. Keeps mutation side-effects (invalidation, optimistic updates) co-located and reusable.
- **`use-plugin-auth.ts`** — Manages the plugin JWT token lifecycle. Queries receive the token explicitly via factory parameters, making the dependency visible and testable.

---

## 3. QueryClient Configuration

**File:** `src/lib/query/client.ts`

```ts
import { QueryClient, QueryCache, MutationCache, isServer } from '@tanstack/react-query'
import { ApiError } from './errors'

function handle401() {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('studio-ai-token')
    window.location.href = '/plugin'
  }
}

function makeQueryClient() {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
        if (error instanceof ApiError && error.status === 401) handle401()
      },
    }),
    mutationCache: new MutationCache({
      onError: (error) => {
        if (error instanceof ApiError && error.status === 401) handle401()
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000,       // 60s — avoid refetch after SSR hydration
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status === 401) return false
          return failureCount < 3
        },
      },
    },
  })
}

let browserQueryClient: QueryClient | undefined

export function getQueryClient() {
  if (isServer) {
    return makeQueryClient()
  }
  if (!browserQueryClient) {
    browserQueryClient = makeQueryClient()
  }
  return browserQueryClient
}
```

### Key decisions

- **No `useState` for client** — follows TanStack v5 recommendation for Suspense safety.
- **Server always gets a new client** — prevents cross-request data leaking.
- **Global 401 handling** — any query or mutation that gets a 401 triggers logout. No duplicate logout logic across components. Uses `ApiError` class (see section 6) instead of `instanceof Response` for reliability across module boundaries.
- **No retry on 401** — retrying an expired token is pointless.
- **60s staleTime** — prevents client-side refetch immediately after server render. Can be overridden per-query.

---

## 4. Provider Setup

**File:** `src/components/providers.tsx`

```tsx
'use client'

import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { ThemeProvider } from './theme-provider'
import { getQueryClient } from '@/lib/query/client'

export function Providers({ children }: { children: React.ReactNode }) {
  const queryClient = getQueryClient()

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem
        disableTransitionOnChange
      >
        {children}
      </ThemeProvider>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
```

**Root layout** (`app/layout.tsx`) wraps children with `<Providers>`.

The existing `ThemeProvider` moves inside `Providers` — single provider tree, no nesting in layout.

---

## 5. PluginAuthProvider

**File:** `src/hooks/use-plugin-auth.ts`

```tsx
'use client'

import { createContext, useContext, useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'

interface PluginAuthContext {
  token: string | null
  setToken: (token: string) => void
  clearToken: () => void
}

const PluginAuthCtx = createContext<PluginAuthContext | null>(null)

export function PluginAuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() =>
    typeof window !== 'undefined' ? localStorage.getItem('studio-ai-token') : null
  )
  const queryClient = useQueryClient()

  const setToken = useCallback((t: string) => {
    localStorage.setItem('studio-ai-token', t)
    setTokenState(t)
    // Push token to native plugin over WebView IPC for cloud WebSocket auth
    window.sendToPlugin?.({ type: 'sendToken', payload: { token: t } })
  }, [])

  const clearToken = useCallback(() => {
    localStorage.removeItem('studio-ai-token')
    setTokenState(null)
    queryClient.clear()
  }, [queryClient])

  return (
    <PluginAuthCtx.Provider value={{ token, setToken, clearToken }}>
      {children}
    </PluginAuthCtx.Provider>
  )
}

export function usePluginToken() {
  const ctx = useContext(PluginAuthCtx)
  if (!ctx) throw new Error('usePluginToken must be used within PluginAuthProvider')
  return ctx
}
```

### Placement

`PluginAuthProvider` wraps only the `(plugin)` layout — the dashboard and marketing sections don't need it.

```tsx
// app/(plugin)/layout.tsx — only PluginAuthProvider here, NOT Providers
// Providers (QueryClientProvider + ThemeProvider) is in the root layout
<PluginAuthProvider>
  {children}
</PluginAuthProvider>
```

### Key decisions

- **`queryClient.clear()` on logout** — wipes all cached data when token is revoked. No stale user data visible after logout.
- **Lazy localStorage read** — `useState(() => ...)` reads once on mount, avoids SSR mismatch.
- **Explicit token parameter in query factories** — queries don't silently read from context; the dependency is visible in the call site.
- **IPC bridge in `setToken`** — calls `window.sendToPlugin()` to push the JWT to the native Rust plugin so it can open a cloud WebSocket. Without this, the DAW plugin never receives the token after login.
- **No double `<Providers>` nesting** — `PluginAuthProvider` lives inside the plugin layout, but `QueryClientProvider` is in the root layout only. Nesting two `QueryClientProvider`s would create separate caches.

---

## 6. Error Class

**File:** `src/lib/query/errors.ts`

```ts
export class ApiError extends Error {
  status: number
  body: string

  constructor(status: number, body: string) {
    super(`API error ${status}: ${body}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}
```

All API functions throw `ApiError` instead of raw `Response`. This is reliable across module boundaries (unlike `instanceof Response`) and preserves both status code and response body for local error handlers.

---

## 7. API Functions

**File:** `src/lib/query/api/presets.ts` (example)

```ts
import { ApiError } from '../errors'

export interface Preset {
  id: string
  name: string
  description: string | null
  prompt: string
  created_at: string
  updated_at: string
}

export interface CreatePresetInput {
  name: string
  description?: string | null
  prompt: string
}

const BASE = '/api/plugin/presets'

async function authFetch(url: string, token: string, init?: RequestInit) {
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, body)
  }
  return res.json()
}

export async function fetchPresets(token: string): Promise<Preset[]> {
  const data = await authFetch(BASE, token)
  return data.presets  // API returns { presets: [...] } envelope
}

export async function createPreset(token: string, data: CreatePresetInput): Promise<Preset> {
  const res = await authFetch(BASE, token, { method: 'POST', body: JSON.stringify(data) })
  return res.preset
}

export async function updatePreset(token: string, id: string, data: Partial<CreatePresetInput>): Promise<Preset> {
  const res = await authFetch(`${BASE}/${id}`, token, { method: 'PUT', body: JSON.stringify(data) })
  return res.preset
}

export async function deletePreset(token: string, id: string): Promise<{ success: boolean }> {
  return authFetch(`${BASE}/${id}`, token, { method: 'DELETE' })
}
```

### Pattern

- **`throw new ApiError()`** on non-ok — the global 401 handler in QueryCache checks `error instanceof ApiError && error.status === 401`. The body is preserved for local handlers that need to display error messages.
- **Response envelope unwrapping** — API routes return `{ presets: [...] }`, `{ preset: {...} }`, etc. The API functions unwrap these so consumers always receive clean typed data.
- **Token as first parameter** — explicit, no hidden dependencies.
- **Shared `authFetch` helper** — DRY within each API file, but NOT exported as a global utility. Each domain file can have its own if the auth pattern diverges.

Same pattern applies to `preferences.ts` and `auth.ts`.

---

## 8. Query Factories

**File:** `src/lib/query/queries/presets.ts`

```ts
import { queryOptions } from '@tanstack/react-query'
import { fetchPresets } from '../api/presets'

export const presetQueries = {
  all: (token: string) =>
    queryOptions({
      queryKey: ['presets', 'all'] as const,
      queryFn: () => fetchPresets(token),
      enabled: !!token,
    }),
}
```

**File:** `src/lib/query/queries/preferences.ts`

```ts
import { queryOptions } from '@tanstack/react-query'
import { fetchPreferences } from '../api/preferences'

export const preferencesQueries = {
  all: (token: string) =>
    queryOptions({
      queryKey: ['preferences', 'all'] as const,
      queryFn: () => fetchPreferences(token),
      enabled: !!token,
    }),
}
```

**File:** `src/lib/query/queries/auth.ts`

```ts
import { queryOptions } from '@tanstack/react-query'
import { validateToken, pollDeviceToken } from '../api/auth'

export const authQueries = {
  validate: (token: string) =>
    queryOptions({
      queryKey: ['auth', 'validate'] as const,
      queryFn: () => validateToken(token),
      enabled: !!token,
      refetchInterval: 30_000,  // validate every 30s (matches current behavior)
    }),

  deviceToken: (sessionId: string, deviceCode: string, expiresAt: number) =>
    queryOptions({
      queryKey: ['auth', 'device-token', deviceCode] as const,
      queryFn: () => pollDeviceToken(sessionId, deviceCode),
      enabled: !!deviceCode && Date.now() < expiresAt,
      refetchInterval: (query) => {
        // Stop polling if expired or if we got a successful token
        if (Date.now() >= expiresAt) return false
        if (query.state.data?.status === 'complete') return false
        return 2_000
      },
      retry: false,
    }),
}
```

### Key decisions

- **`enabled: !!token`** — queries don't fire until the user is authenticated. Prevents wasted requests and errors during login flow.
- **`refetchInterval`** — replaces manual `setInterval` in device polling and token validation. TanStack Query handles cleanup automatically.
- **`as const` on queryKey** — enables type-safe key matching in `invalidateQueries`.
- **Namespaced keys** — `['presets', 'all']` instead of `['presets']`. Prevents key collisions if sub-queries are added later (e.g., `['presets', id]`). Consistent with the `['auth', 'validate']` pattern.
- **Device token polling** — takes `sessionId`, `deviceCode`, and `expiresAt`. The `refetchInterval` callback returns `false` to stop polling when the token arrives or the deadline passes. The `enabled` flag also prevents initial fetch if already expired.

---

## 9. Mutation Hooks

All mutation hooks guard against null tokens with an explicit check instead of `token!` non-null assertions. This prevents confusing `Bearer null` headers if a mutation is triggered during a race condition.

**File:** `src/hooks/mutations/use-preset-mutations.ts`

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createPreset, updatePreset, deletePreset, CreatePresetInput } from '@/lib/query/api/presets'
import { usePluginToken } from '@/hooks/use-plugin-auth'

function useRequiredToken() {
  const { token } = usePluginToken()
  return () => {
    if (!token) throw new Error('Not authenticated')
    return token
  }
}

export function useCreatePreset() {
  const queryClient = useQueryClient()
  const getToken = useRequiredToken()

  return useMutation({
    mutationFn: (data: CreatePresetInput) => createPreset(getToken(), data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['presets'] })
    },
  })
}

export function useUpdatePreset() {
  const queryClient = useQueryClient()
  const getToken = useRequiredToken()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CreatePresetInput> }) =>
      updatePreset(getToken(), id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['presets'] })
    },
  })
}

export function useDeletePreset() {
  const queryClient = useQueryClient()
  const getToken = useRequiredToken()

  return useMutation({
    mutationFn: (id: string) => deletePreset(getToken(), id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['presets'] })
    },
  })
}
```

**File:** `src/hooks/mutations/use-preferences-mutations.ts`

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { updatePreferences, UpdatePreferencesInput } from '@/lib/query/api/preferences'
import { usePluginToken } from '@/hooks/use-plugin-auth'

export function useUpdatePreferences() {
  const queryClient = useQueryClient()
  const { token } = usePluginToken()

  return useMutation({
    mutationFn: (data: UpdatePreferencesInput) => {
      if (!token) throw new Error('Not authenticated')
      return updatePreferences(token, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['preferences'] })
    },
  })
}
```

**File:** `src/hooks/mutations/use-device-auth-mutations.ts`

```ts
import { useMutation } from '@tanstack/react-query'
import { initiateDeviceFlow, DeviceFlowSession } from '@/lib/query/api/auth'

export function useInitiateDeviceFlow() {
  return useMutation({
    mutationFn: () => initiateDeviceFlow(),
  })
}
```

The device auth flow is two phases:
1. **Initiate** — `useInitiateDeviceFlow()` mutation POSTs to `/api/auth/device`, returns `{ session_id, device_code, user_code, expires_in }`.
2. **Poll** — component passes `sessionId`, `deviceCode`, and computed `expiresAt` to `authQueries.deviceToken(...)` which polls via `refetchInterval`.

### No optimistic updates

Current API calls go to Supabase via local API routes — fast enough that optimistic updates add complexity without meaningful UX gain. Can be added per-mutation later if latency increases.

---

## 10. Migration Map

| File | Current Pattern | After | Notes |
|------|----------------|-------|-------|
| `presets-panel.tsx` | `useState` + `useEffect` + `fetch` | `useQuery(presetQueries.all(token))` + `useCreatePreset()`, `useUpdatePreset()`, `useDeletePreset()` | Remove all manual state/effect/fetch code |
| `plugin-dashboard.tsx` | `fetch('/api/plugin/preferences')` in `useEffect` | `useQuery(preferencesQueries.all(token))` | Remove `useState` for preferences, `useEffect` for fetch |
| `onboarding-wizard.tsx` | Inline `fetch(PATCH)` | `useUpdatePreferences()` | Single mutation call replaces inline fetch |
| `plugin-login.tsx` | `setInterval` polling for device token | `useInitiateDeviceFlow()` mutation + `useQuery(authQueries.deviceToken(sessionId, deviceCode, expiresAt))` | Two-phase: mutation initiates, query polls with auto-stop on expiry |
| `plugin-dashboard.tsx` | Manual 30s token validation interval | `useQuery(authQueries.validate(token))` | `refetchInterval: 30000` replaces `setInterval` |
| `plugin/page.tsx` | `localStorage` + `useState` for token | `usePluginToken()` from `PluginAuthProvider` | Centralized token management |

### Not migrated (stays as-is)

| File | Reason |
|------|--------|
| `useChat()` in `plugin-dashboard.tsx` | Vercel AI SDK streaming — TanStack Query doesn't replace this |
| IPC polling in `plugin-dashboard.tsx` | 5s `setInterval` for `window.sendToPlugin({ type: "getConnectionStatus" })` — pure WebView IPC, not HTTP |
| Server actions (`auth-actions.ts`, `link/actions.ts`) | Server-side, no client query needed |
| Dashboard server components | Already server-rendered, no benefit from client queries |
| API route handlers (`app/api/**`) | Backend, not affected |

---

## 11. Error Handling Strategy

### Global (QueryCache / MutationCache)

- **401 Unauthorized** — clear token from localStorage, wipe query cache, redirect to `/plugin` (login). Applied to all queries and mutations automatically.
- **No retry on 401** — custom `retry` function skips 401 responses.

### Local (per component)

- Components handle domain-specific errors via the `error` / `isError` state from `useQuery` / `useMutation`.
- Example: preset save failure shows an inline error message in the presets panel.
- No global toast system for now — can be added to `MutationCache.onError` later if needed.

### Error type

API functions throw `ApiError` (see section 6) on non-ok status. This provides:
- `error.status` for the global 401 handler and local status checks
- `error.body` for displaying error messages in the UI
- Reliable `instanceof ApiError` across module boundaries (unlike `instanceof Response`)

---

## 12. What This Does NOT Cover

- **Server-side prefetching / dehydration** — not needed now since plugin is fully client-rendered. Infrastructure is ready (the `getQueryClient()` function works on server) for when dashboard needs it.
- **Optimistic updates** — deferred. Can be added per-mutation.
- **Infinite queries / pagination** — no current use case.
- **WebSocket / real-time invalidation** — no current use case.
