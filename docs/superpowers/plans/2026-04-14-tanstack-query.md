# TanStack React Query Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all raw `fetch()` + `useState` + `useEffect` data fetching patterns in the plugin area with TanStack React Query v5, and set up the infrastructure for future adoption in the dashboard.

**Architecture:** Provider at root layout (`QueryClientProvider` + `ThemeProvider`). Plugin auth context in plugin layout. Pure API functions in `lib/query/api/`, `queryOptions` factories in `lib/query/queries/`, mutation hooks in `hooks/mutations/`. Global 401 handler auto-clears token and redirects.

**Tech Stack:** `@tanstack/react-query` v5, `@tanstack/react-query-devtools` v5, Next.js App Router, TypeScript

**Spec:** `docs/superpowers/specs/2026-04-14-tanstack-query-design.md`

---

## File Map

### New files (create)

| File | Responsibility |
|------|---------------|
| `src/lib/query/errors.ts` | `ApiError` class |
| `src/lib/query/client.ts` | `getQueryClient()` singleton with global 401 handler |
| `src/lib/query/api/presets.ts` | Plain fetch functions for presets CRUD |
| `src/lib/query/api/preferences.ts` | Plain fetch functions for preferences |
| `src/lib/query/api/auth.ts` | Plain fetch functions for token validation, device flow |
| `src/lib/query/queries/presets.ts` | `presetQueries` factory |
| `src/lib/query/queries/preferences.ts` | `preferencesQueries` factory |
| `src/lib/query/queries/auth.ts` | `authQueries` factory |
| `src/hooks/use-plugin-auth.ts` | `PluginAuthProvider` + `usePluginToken()` |
| `src/hooks/mutations/use-preset-mutations.ts` | `useCreatePreset()` |
| `src/hooks/mutations/use-preferences-mutations.ts` | `useUpdatePreferences()` |
| `src/hooks/mutations/use-device-auth-mutations.ts` | `useInitiateDeviceFlow()` |

### Modified files

| File | What changes |
|------|-------------|
| `src/components/theme-provider.tsx` | Add `QueryClientProvider` wrapping, rename to `providers.tsx` |
| `src/app/layout.tsx` | Import `Providers` instead of `ThemeProvider` |
| `src/app/(plugin)/layout.tsx` | Wrap children with `PluginAuthProvider` |
| `src/app/(plugin)/plugin/page.tsx` | Replace all token/validation logic with `usePluginToken()` + `useQuery(authQueries.validate)` |
| `src/app/(plugin)/plugin/plugin-login.tsx` | Replace manual polling with `useInitiateDeviceFlow()` + `useQuery(authQueries.deviceToken)` |
| `src/app/(plugin)/plugin/plugin-dashboard.tsx` | Replace preferences `useEffect` fetch with `useQuery(preferencesQueries.all)` |
| `src/app/(plugin)/plugin/components/panels/presets-panel.tsx` | Replace all fetch/state with `useQuery` + mutation hooks |
| `src/app/(plugin)/plugin/components/onboarding-wizard.tsx` | Replace inline `fetch(PATCH)` with `useUpdatePreferences()` |

---

### Task 1: Install dependencies

**Files:**
- Modify: `apps/web/package.json`

- [ ] **Step 1: Install TanStack Query packages**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai
pnpm add @tanstack/react-query @tanstack/react-query-devtools --filter web
```

Expected: packages added to `apps/web/package.json` under `dependencies` and `devDependencies`.

- [ ] **Step 2: Verify installation**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
node -e "require('@tanstack/react-query'); console.log('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add apps/web/package.json pnpm-lock.yaml
git commit -m "chore: add @tanstack/react-query and devtools"
```

---

### Task 2: Create ApiError class

**Files:**
- Create: `src/lib/query/errors.ts`

- [ ] **Step 1: Create the error class**

Create `apps/web/src/lib/query/errors.ts`:

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

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
npx tsc --noEmit 2>&1 | grep "query/errors"
```

Expected: no output (no errors).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/query/errors.ts
git commit -m "feat(query): add ApiError class for typed API errors"
```

---

### Task 3: Create QueryClient singleton

**Files:**
- Create: `src/lib/query/client.ts`

- [ ] **Step 1: Create the client file**

Create `apps/web/src/lib/query/client.ts`:

```ts
import {
  QueryClient,
  QueryCache,
  MutationCache,
  isServer,
} from '@tanstack/react-query'
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
        staleTime: 60 * 1000,
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

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
npx tsc --noEmit 2>&1 | grep "query/client"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/query/client.ts
git commit -m "feat(query): add QueryClient singleton with global 401 handler"
```

---

### Task 4: Create Providers component and wire into root layout

**Files:**
- Modify: `src/components/theme-provider.tsx` (rename to `providers.tsx`)
- Modify: `src/app/layout.tsx`

- [ ] **Step 1: Create providers.tsx**

Create `apps/web/src/components/providers.tsx`:

```tsx
'use client'

import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { ThemeProvider as NextThemesProvider } from 'next-themes'
import { getQueryClient } from '@/lib/query/client'

export function Providers({ children }: { children: React.ReactNode }) {
  const queryClient = getQueryClient()

  return (
    <QueryClientProvider client={queryClient}>
      <NextThemesProvider
        attribute="class"
        defaultTheme="system"
        enableSystem
        disableTransitionOnChange
      >
        {children}
      </NextThemesProvider>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
```

- [ ] **Step 2: Update root layout to use Providers**

Modify `apps/web/src/app/layout.tsx`. Replace the import and usage:

Change:
```tsx
import { ThemeProvider } from "@/components/theme-provider";
```
To:
```tsx
import { Providers } from "@/components/providers";
```

Change:
```tsx
<ThemeProvider>{children}</ThemeProvider>
```
To:
```tsx
<Providers>{children}</Providers>
```

- [ ] **Step 3: Update all imports of ThemeProvider**

Search codebase for any other imports of `@/components/theme-provider`. If none exist besides `layout.tsx`, delete the old `theme-provider.tsx` file.

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
grep -r "theme-provider" src/ --include="*.tsx" --include="*.ts"
```

If only `layout.tsx` imported it (now updated), delete:

```bash
rm apps/web/src/components/theme-provider.tsx
```

- [ ] **Step 4: Verify the app loads**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors referencing `theme-provider` or `providers`.

Also confirm the dev server still runs (check `http://localhost:3000` in browser — theme should still work, React Query devtools icon should appear bottom-right).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/providers.tsx apps/web/src/app/layout.tsx
git rm apps/web/src/components/theme-provider.tsx 2>/dev/null; true
git commit -m "feat(query): add Providers with QueryClientProvider, replace ThemeProvider"
```

---

### Task 5: Create PluginAuthProvider and usePluginToken hook

**Files:**
- Create: `src/hooks/use-plugin-auth.ts`
- Modify: `src/app/(plugin)/layout.tsx`

- [ ] **Step 1: Create the auth provider**

Create `apps/web/src/hooks/use-plugin-auth.ts`:

```tsx
'use client'

import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'

interface PluginAuthContextValue {
  token: string | null
  ready: boolean
  setToken: (token: string) => void
  clearToken: () => void
}

const PluginAuthCtx = createContext<PluginAuthContextValue | null>(null)

export function PluginAuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const queryClient = useQueryClient()

  // Read token from localStorage on mount, check client-side expiry
  useEffect(() => {
    const stored = localStorage.getItem('studio-ai-token')
    if (!stored) {
      setReady(true)
      return
    }

    // Quick client-side JWT expiry check
    try {
      const base64 = stored.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
      const payload = JSON.parse(atob(base64))
      if (!payload.exp || payload.exp * 1000 <= Date.now()) {
        localStorage.removeItem('studio-ai-token')
        setReady(true)
        return
      }
    } catch {
      localStorage.removeItem('studio-ai-token')
      setReady(true)
      return
    }

    setTokenState(stored)
    // Push token to native plugin via IPC
    window.sendToPlugin?.({ type: 'sendToken', payload: { token: stored } })
    setReady(true)
  }, [])

  const setToken = useCallback((t: string) => {
    localStorage.setItem('studio-ai-token', t)
    setTokenState(t)
    window.sendToPlugin?.({ type: 'sendToken', payload: { token: t } })
  }, [])

  const clearToken = useCallback(() => {
    localStorage.removeItem('studio-ai-token')
    setTokenState(null)
    queryClient.clear()
  }, [queryClient])

  return (
    <PluginAuthCtx.Provider value={{ token, ready, setToken, clearToken }}>
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

- [ ] **Step 2: Wrap plugin layout with PluginAuthProvider**

Modify `apps/web/src/app/(plugin)/layout.tsx`:

```tsx
import { PluginAuthProvider } from '@/hooks/use-plugin-auth'

export default function PluginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="dark flex h-screen w-screen overflow-hidden bg-[#0a0a0a]">
      <PluginAuthProvider>
        {children}
      </PluginAuthProvider>
    </div>
  );
}
```

Note: This layout is a Server Component that renders a Client Component (`PluginAuthProvider`). This is valid in Next.js App Router — client components can be imported and rendered inside server components.

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
npx tsc --noEmit 2>&1 | grep -E "use-plugin-auth|plugin.*layout"
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/hooks/use-plugin-auth.ts apps/web/src/app/\(plugin\)/layout.tsx
git commit -m "feat(query): add PluginAuthProvider with token lifecycle and IPC bridge"
```

---

### Task 6: Create API functions

**Files:**
- Create: `src/lib/query/api/presets.ts`
- Create: `src/lib/query/api/preferences.ts`
- Create: `src/lib/query/api/auth.ts`

- [ ] **Step 1: Create shared auth fetch helper pattern and presets API**

Create `apps/web/src/lib/query/api/presets.ts`:

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
  return data.presets
}

export async function createPreset(
  token: string,
  input: CreatePresetInput,
): Promise<Preset> {
  const data = await authFetch(BASE, token, {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return data.preset
}

export async function updatePreset(
  token: string,
  id: string,
  input: Partial<CreatePresetInput>,
): Promise<Preset> {
  const data = await authFetch(`${BASE}/${id}`, token, {
    method: 'PUT',
    body: JSON.stringify(input),
  })
  return data.preset
}

export async function deletePreset(
  token: string,
  id: string,
): Promise<{ success: boolean }> {
  return authFetch(`${BASE}/${id}`, token, { method: 'DELETE' })
}
```

- [ ] **Step 2: Create preferences API**

Create `apps/web/src/lib/query/api/preferences.ts`:

```ts
import { ApiError } from '../errors'

export interface Preferences {
  onboarding_completed: boolean
}

export interface UpdatePreferencesInput {
  onboarding_completed?: boolean
}

const BASE = '/api/plugin/preferences'

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

export async function fetchPreferences(token: string): Promise<Preferences> {
  const data = await authFetch(BASE, token)
  return data.preferences
}

export async function updatePreferences(
  token: string,
  input: UpdatePreferencesInput,
): Promise<Preferences> {
  const data = await authFetch(BASE, token, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
  return data.preferences
}
```

- [ ] **Step 3: Create auth API**

Create `apps/web/src/lib/query/api/auth.ts`:

```ts
import { ApiError } from '../errors'

export interface DeviceFlowSession {
  session_id: string
  device_code: string
  user_code: string
  expires_in: number
}

export interface DeviceTokenResponse {
  status: 'pending' | 'complete' | 'expired'
  token?: string
}

export async function validateToken(token: string): Promise<{ valid: boolean }> {
  const res = await fetch('/api/auth/plugin/validate', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, body)
  }
  return res.json()
}

export async function initiateDeviceFlow(): Promise<DeviceFlowSession> {
  const res = await fetch('/api/auth/device', { method: 'POST' })
  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, body)
  }
  return res.json()
}

export async function pollDeviceToken(
  sessionId: string,
  deviceCode: string,
): Promise<DeviceTokenResponse> {
  const res = await fetch('/api/auth/device/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, device_code: deviceCode }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, body)
  }
  return res.json()
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
npx tsc --noEmit 2>&1 | grep "query/api"
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/query/api/
git commit -m "feat(query): add API functions for presets, preferences, and auth"
```

---

### Task 7: Create query factories

**Files:**
- Create: `src/lib/query/queries/presets.ts`
- Create: `src/lib/query/queries/preferences.ts`
- Create: `src/lib/query/queries/auth.ts`

- [ ] **Step 1: Create presets query factory**

Create `apps/web/src/lib/query/queries/presets.ts`:

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

- [ ] **Step 2: Create preferences query factory**

Create `apps/web/src/lib/query/queries/preferences.ts`:

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

- [ ] **Step 3: Create auth query factory**

Create `apps/web/src/lib/query/queries/auth.ts`:

```ts
import { queryOptions } from '@tanstack/react-query'
import { validateToken, pollDeviceToken } from '../api/auth'

export const authQueries = {
  validate: (token: string) =>
    queryOptions({
      queryKey: ['auth', 'validate'] as const,
      queryFn: () => validateToken(token),
      enabled: !!token,
      refetchInterval: 30_000,
    }),

  deviceToken: (sessionId: string, deviceCode: string, expiresAt: number) =>
    queryOptions({
      queryKey: ['auth', 'device-token', deviceCode] as const,
      queryFn: () => pollDeviceToken(sessionId, deviceCode),
      enabled: !!deviceCode && Date.now() < expiresAt,
      refetchInterval: (query) => {
        if (Date.now() >= expiresAt) return false
        if (query.state.data?.status === 'complete') return false
        return 2_000
      },
      retry: false,
    }),
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
npx tsc --noEmit 2>&1 | grep "query/queries"
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/query/queries/
git commit -m "feat(query): add queryOptions factories for presets, preferences, auth"
```

---

### Task 8: Create mutation hooks

**Files:**
- Create: `src/hooks/mutations/use-preset-mutations.ts`
- Create: `src/hooks/mutations/use-preferences-mutations.ts`
- Create: `src/hooks/mutations/use-device-auth-mutations.ts`

- [ ] **Step 1: Create preset mutations**

Create `apps/web/src/hooks/mutations/use-preset-mutations.ts`:

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createPreset,
  updatePreset,
  deletePreset,
  CreatePresetInput,
} from '@/lib/query/api/presets'
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

- [ ] **Step 2: Create preferences mutations**

Create `apps/web/src/hooks/mutations/use-preferences-mutations.ts`:

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  updatePreferences,
  UpdatePreferencesInput,
} from '@/lib/query/api/preferences'
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

- [ ] **Step 3: Create device auth mutations**

Create `apps/web/src/hooks/mutations/use-device-auth-mutations.ts`:

```ts
import { useMutation } from '@tanstack/react-query'
import { initiateDeviceFlow } from '@/lib/query/api/auth'

export function useInitiateDeviceFlow() {
  return useMutation({
    mutationFn: () => initiateDeviceFlow(),
  })
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
npx tsc --noEmit 2>&1 | grep "mutations"
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/hooks/mutations/
git commit -m "feat(query): add mutation hooks for presets, preferences, device auth"
```

---

### Task 9: Migrate plugin/page.tsx to use PluginAuthProvider

**Files:**
- Modify: `src/app/(plugin)/plugin/page.tsx`

This is the biggest behavioral change. The current `page.tsx` manages token state, validation, and IPC. All of that now lives in `PluginAuthProvider` + `authQueries.validate`. This file becomes a thin router.

- [ ] **Step 1: Rewrite page.tsx**

Replace the entire content of `apps/web/src/app/(plugin)/plugin/page.tsx`:

```tsx
'use client'

import { useQuery } from '@tanstack/react-query'
import { usePluginToken } from '@/hooks/use-plugin-auth'
import { authQueries } from '@/lib/query/queries/auth'
import { PluginDashboard } from './plugin-dashboard'
import { PluginLogin } from './plugin-login'

export default function PluginPage() {
  const { token, ready, setToken, clearToken } = usePluginToken()

  // Periodic server-side validation (checks revocation)
  const { isError } = useQuery({
    ...authQueries.validate(token ?? ''),
    enabled: !!token,
  })

  // If validation fails, clear the token
  if (isError && token) {
    clearToken()
  }

  if (!ready) return null

  if (!token) {
    return <PluginLogin onToken={setToken} />
  }

  return <PluginDashboard token={token} onAuthError={clearToken} />
}
```

- [ ] **Step 2: Verify the plugin page loads**

Open `http://localhost:3000/plugin` in the browser.

Expected behavior:
- If no token stored: shows login screen
- If token stored: validates and shows dashboard
- Token validation polls every 30 seconds (check React Query devtools)

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/page.tsx
git commit -m "refactor(plugin): replace manual token management with usePluginToken + useQuery"
```

---

### Task 10: Migrate plugin-login.tsx to use query + mutation

**Files:**
- Modify: `src/app/(plugin)/plugin/plugin-login.tsx`

- [ ] **Step 1: Rewrite plugin-login.tsx**

Replace the entire content of `apps/web/src/app/(plugin)/plugin/plugin-login.tsx`:

```tsx
'use client'

import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useInitiateDeviceFlow } from '@/hooks/mutations/use-device-auth-mutations'
import { authQueries } from '@/lib/query/queries/auth'

export function PluginLogin({ onToken }: { onToken: (token: string) => void }) {
  const [sessionId, setSessionId] = useState('')
  const [deviceCode, setDeviceCode] = useState('')
  const [userCode, setUserCode] = useState('')
  const [expiresAt, setExpiresAt] = useState(0)
  const [error, setError] = useState('')

  const initiate = useInitiateDeviceFlow()

  // Poll for token once device flow is initiated
  const { data: pollData } = useQuery({
    ...authQueries.deviceToken(sessionId, deviceCode, expiresAt),
  })

  // When polling returns a complete token, pass it up
  useEffect(() => {
    if (pollData?.status === 'complete' && pollData.token) {
      onToken(pollData.token)
    } else if (pollData?.status === 'expired') {
      setError('Session expired. Please try again.')
      setSessionId('')
      setDeviceCode('')
      setUserCode('')
    }
  }, [pollData, onToken])

  // Handle expiry based on deadline
  useEffect(() => {
    if (!expiresAt) return
    const timeout = setTimeout(() => {
      if (Date.now() >= expiresAt && deviceCode) {
        setError('Authorization expired. Please try again.')
        setSessionId('')
        setDeviceCode('')
        setUserCode('')
      }
    }, expiresAt - Date.now())
    return () => clearTimeout(timeout)
  }, [expiresAt, deviceCode])

  const startAuth = async () => {
    setError('')
    setUserCode('')

    initiate.mutate(undefined, {
      onSuccess: (data) => {
        setSessionId(data.session_id)
        setDeviceCode(data.device_code)
        setUserCode(data.user_code)
        setExpiresAt(Date.now() + data.expires_in * 1000)

        // Open system browser to /link
        const linkUrl = `${window.location.origin}/link`
        if (typeof window.sendToPlugin === 'function') {
          window.sendToPlugin({ type: 'open_browser', url: linkUrl })
        } else {
          window.open(linkUrl, '_blank')
        }
      },
      onError: () => {
        setError('Failed to start authentication.')
      },
    })
  }

  return (
    <div className="flex h-full w-full items-center justify-center bg-background">
      <Card className="w-full max-w-sm p-6 space-y-4">
        <div className="text-center space-y-1">
          <h1 className="text-xl font-semibold">Studio AI</h1>
          <p className="text-sm text-muted-foreground">
            Sign in to connect your DAW
          </p>
        </div>

        {!userCode ? (
          <Button
            onClick={startAuth}
            className="w-full"
            disabled={initiate.isPending}
          >
            {initiate.isPending ? 'Starting...' : 'Sign in with Browser'}
          </Button>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground text-center">
              Enter this code in your browser:
            </p>
            <div className="text-3xl font-mono font-bold text-center tracking-widest py-3">
              {userCode}
            </div>
            <p className="text-xs text-muted-foreground text-center">
              Waiting for authorization...
            </p>
          </div>
        )}

        {error && (
          <p className="text-sm text-destructive text-center">{error}</p>
        )}
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Test the device auth flow**

Open `http://localhost:3000/plugin` (while logged out).

Expected:
1. Click "Sign in with Browser" — initiates device flow
2. Shows user code
3. React Query devtools shows `['auth', 'device-token', ...]` query polling every 2s
4. After authorizing in browser, token is received and dashboard loads
5. If expired, shows error and resets

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/plugin-login.tsx
git commit -m "refactor(plugin): replace manual device auth polling with useQuery + useMutation"
```

---

### Task 11: Migrate plugin-dashboard.tsx preferences fetch

**Files:**
- Modify: `src/app/(plugin)/plugin/plugin-dashboard.tsx`

Only the preferences `useEffect` fetch (lines 94-105) is replaced. Everything else (`useChat`, IPC, connection status) stays as-is.

- [ ] **Step 1: Replace the preferences fetch**

In `apps/web/src/app/(plugin)/plugin/plugin-dashboard.tsx`:

Add import at the top:
```tsx
import { useQuery } from '@tanstack/react-query'
import { preferencesQueries } from '@/lib/query/queries/preferences'
```

Remove the entire `useEffect` block at lines 94-105:
```tsx
  // Check onboarding status
  useEffect(() => {
    fetch("/api/plugin/preferences", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data.preferences?.onboarding_completed) {
          setShowOnboarding(true);
        }
      })
      .catch(() => {});
  }, [token]);
```

Replace it with:
```tsx
  // Check onboarding status
  const { data: preferences } = useQuery(preferencesQueries.all(token))

  useEffect(() => {
    if (preferences && !preferences.onboarding_completed) {
      setShowOnboarding(true)
    }
  }, [preferences])
```

- [ ] **Step 2: Verify the dashboard loads and onboarding works**

Open `http://localhost:3000/plugin` (while logged in).

Expected:
- Dashboard loads normally
- If onboarding not completed, wizard appears
- React Query devtools shows `['preferences', 'all']` query

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/plugin-dashboard.tsx
git commit -m "refactor(plugin): replace preferences useEffect fetch with useQuery"
```

---

### Task 12: Migrate presets-panel.tsx

**Files:**
- Modify: `src/app/(plugin)/plugin/components/panels/presets-panel.tsx`

This is the most thorough migration — replaces all state, effects, and fetch calls.

- [ ] **Step 1: Rewrite presets-panel.tsx**

Replace the entire content of `apps/web/src/app/(plugin)/plugin/components/panels/presets-panel.tsx`:

```tsx
'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Skeleton } from '@/components/ui/skeleton'
import { Plus } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { usePluginToken } from '@/hooks/use-plugin-auth'
import { presetQueries } from '@/lib/query/queries/presets'
import { useCreatePreset } from '@/hooks/mutations/use-preset-mutations'

export function PresetsPanel({
  onSendPrompt,
}: {
  onSendPrompt: (prompt: string) => void
}) {
  const { token } = usePluginToken()
  const { data: presets, isLoading } = useQuery(presetQueries.all(token ?? ''))
  const createPreset = useCreatePreset()

  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [newPrompt, setNewPrompt] = useState('')

  const handleCreate = () => {
    if (!newName.trim() || !newPrompt.trim()) return
    createPreset.mutate(
      { name: newName, description: newDescription || null, prompt: newPrompt },
      {
        onSuccess: () => {
          setShowCreate(false)
          setNewName('')
          setNewDescription('')
          setNewPrompt('')
        },
      },
    )
  }

  if (isLoading) {
    return (
      <div className="space-y-2 p-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-14 w-full rounded-xl" />
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1.5 p-2.5">
      {presets?.map((preset) => (
        <button
          key={preset.id}
          onClick={() => onSendPrompt(preset.prompt)}
          className="rounded-xl bg-white/[0.02] px-3.5 py-3 text-left transition-colors hover:bg-white/[0.04]"
        >
          <div className="text-[12.5px] font-medium text-[#c8c8c8]">
            {preset.name}
          </div>
          {preset.description && (
            <div className="mt-0.5 text-[10.5px] text-[#444] line-clamp-1">
              {preset.description}
            </div>
          )}
        </button>
      ))}

      <button
        onClick={() => setShowCreate(true)}
        className="rounded-xl border border-dashed border-white/5 py-3 text-center text-[12px] text-[#333] transition-colors hover:border-white/10 hover:text-[#555]"
      >
        <Plus className="mr-1 inline h-3.5 w-3.5" />
        Create Custom
      </button>

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Preset</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 pt-2">
            <div>
              <Label htmlFor="preset-name">Name</Label>
              <Input
                id="preset-name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Lo-fi Beat Setup"
              />
            </div>
            <div>
              <Label htmlFor="preset-desc">Description (optional)</Label>
              <Input
                id="preset-desc"
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="Set BPM, add drums, bass, keys"
              />
            </div>
            <div>
              <Label htmlFor="preset-prompt">Prompt</Label>
              <Input
                id="preset-prompt"
                value={newPrompt}
                onChange={(e) => setNewPrompt(e.target.value)}
                placeholder="Set BPM to 85 and add drums, bass, and keys tracks"
              />
            </div>
            <Button
              onClick={handleCreate}
              disabled={createPreset.isPending || !newName.trim() || !newPrompt.trim()}
              className="w-full"
            >
              {createPreset.isPending ? 'Creating...' : 'Create Preset'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
```

- [ ] **Step 2: Update PresetsPanel usage in plugin-dashboard.tsx**

In `apps/web/src/app/(plugin)/plugin/plugin-dashboard.tsx`, the `PresetsPanel` is rendered at line 156:

```tsx
presets: <PresetsPanel token={token} onSendPrompt={handleSendPrompt} />,
```

Change to (remove the `token` prop — it now comes from `usePluginToken`):

```tsx
presets: <PresetsPanel onSendPrompt={handleSendPrompt} />,
```

- [ ] **Step 3: Test presets CRUD**

Open `http://localhost:3000/plugin` (logged in), expand the presets panel.

Expected:
- Presets load (check React Query devtools for `['presets', 'all']`)
- Click a preset — sends prompt to chat
- Click "Create Custom" — form appears
- Submit form — preset created, list auto-refreshes (invalidation)
- No `token` prop passed to `PresetsPanel`

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/components/panels/presets-panel.tsx apps/web/src/app/\(plugin\)/plugin/plugin-dashboard.tsx
git commit -m "refactor(plugin): replace presets fetch/state with useQuery + useCreatePreset"
```

---

### Task 13: Migrate onboarding-wizard.tsx

**Files:**
- Modify: `src/app/(plugin)/plugin/components/onboarding-wizard.tsx`

Only the `fetch(PATCH)` call inside `handleNext` changes.

- [ ] **Step 1: Replace the inline fetch with mutation**

In `apps/web/src/app/(plugin)/plugin/components/onboarding-wizard.tsx`:

Add imports at the top:
```tsx
import { useUpdatePreferences } from '@/hooks/mutations/use-preferences-mutations'
```

Inside the component function, add the mutation hook:
```tsx
const updatePreferences = useUpdatePreferences()
```

Replace the `handleNext` function (approximately lines 51-65). Change:
```tsx
  const handleNext = async () => {
    if (step < steps.length - 1) {
      setStep(step + 1);
    } else {
      await fetch("/api/plugin/preferences", {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ onboarding_completed: true }),
      });
      onComplete();
    }
  };
```

To:
```tsx
  const handleNext = () => {
    if (step < steps.length - 1) {
      setStep(step + 1)
    } else {
      updatePreferences.mutate(
        { onboarding_completed: true },
        { onSuccess: () => onComplete() },
      )
    }
  }
```

If the component currently receives a `token` prop only for this fetch, check if `token` is used elsewhere in the component. If it's only used for the fetch call, remove the `token` prop from the component signature and from where it's rendered in `plugin-dashboard.tsx`.

- [ ] **Step 2: Update OnboardingWizard usage if token prop was removed**

In `apps/web/src/app/(plugin)/plugin/plugin-dashboard.tsx`, line 206:

```tsx
<OnboardingWizard
  open={showOnboarding}
  onComplete={() => setShowOnboarding(false)}
  token={token}
/>
```

If `token` was removed from the component, change to:

```tsx
<OnboardingWizard
  open={showOnboarding}
  onComplete={() => setShowOnboarding(false)}
/>
```

- [ ] **Step 3: Test onboarding flow**

Open `http://localhost:3000/plugin` (with a fresh user or reset onboarding in DB).

Expected:
- Wizard appears
- Navigate through steps
- On final step, preferences mutation fires
- React Query devtools shows `['preferences']` invalidation
- Wizard closes

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/components/onboarding-wizard.tsx apps/web/src/app/\(plugin\)/plugin/plugin-dashboard.tsx
git commit -m "refactor(plugin): replace onboarding fetch with useUpdatePreferences mutation"
```

---

### Task 14: Final cleanup and verification

**Files:**
- Possibly modify: various files for unused imports

- [ ] **Step 1: Check for TypeScript errors**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
npx tsc --noEmit
```

Fix any errors that appear.

- [ ] **Step 2: Check for unused imports**

```bash
cd /Users/cristiancirje/Desktop/Dev/studio-ai/apps/web
npx tsc --noEmit 2>&1 | grep "declared but"
```

Remove any flagged unused imports.

- [ ] **Step 3: Full app smoke test**

Test each flow in the browser:

1. **Marketing pages** (`/`) — theme still works, no console errors
2. **Login page** (`/login`) — Google sign-in still works
3. **Plugin login** (`/plugin` while logged out) — device flow works with TanStack Query polling
4. **Plugin dashboard** (`/plugin` while logged in):
   - Chat works (useChat unaffected)
   - Presets panel loads and creates
   - Onboarding wizard completes
   - Connection status polling works (IPC, unaffected)
5. **React Query devtools** — visible in bottom-right, shows all active queries

- [ ] **Step 4: Commit any cleanup**

```bash
git add -u apps/web/src/
git commit -m "chore: cleanup unused imports after TanStack Query migration"
```
