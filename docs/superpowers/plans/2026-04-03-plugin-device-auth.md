# Plugin Device Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken direct-OAuth-in-WebView with a secure device authorization flow that opens the system browser for Google sign-in and exchanges a token back to the plugin automatically.

**Architecture:** The WebView initiates a device session via API, opens the system browser for Google OAuth + approval, then polls for the resulting JWT. Device sessions are stored in Supabase for scalability. After exchange, the JWT is stored in localStorage and used as Bearer token for all API calls.

**Tech Stack:** NextAuth v5, Supabase (PostgreSQL), jose (JWT), Next.js App Router, crypto (Node.js)

**Spec:** `docs/superpowers/specs/2026-04-03-plugin-auth-simplification-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `apps/web/src/lib/device-session.ts` | **Create** — Device session CRUD with Supabase (create, findBySessionId, approve, deleteSession, cleanExpired) |
| `apps/web/src/lib/plugin-auth.ts` | **Create** — JWT sign + verify for plugin tokens |
| `apps/web/src/app/api/auth/device/route.ts` | **Create** — POST endpoint: create device session |
| `apps/web/src/app/api/auth/device/token/route.ts` | **Create** — POST endpoint: poll & exchange for JWT |
| `apps/web/src/app/auth/device/authorize/page.tsx` | **Create** — Browser page: "Authorize plugin?" + approve action |
| `apps/web/src/app/(plugin)/plugin/plugin-login.tsx` | **Create** — WebView UI: "Sign in" button + polling |
| `apps/web/src/middleware.ts` | **Modify** — Add device auth to public paths |
| `apps/web/src/app/(plugin)/plugin/page.tsx` | **Modify** — Client component with localStorage token check |
| `apps/web/src/app/(plugin)/plugin/plugin-chat.tsx` | **Modify** — Accept token prop, send as Bearer header |
| `apps/web/src/app/api/ai/execute/route.ts` | **Modify** — Restore Bearer token auth path |

---

### Task 1: Database migration — create device_sessions table

**Files:**
- Create: SQL migration via Supabase dashboard or CLI

- [ ] **Step 1: Run migration on Supabase**

Execute this SQL in the Supabase SQL editor (or via `supabase db push`):

```sql
CREATE TABLE device_sessions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       UUID UNIQUE NOT NULL,
  device_code_hash TEXT NOT NULL,
  user_id          UUID REFERENCES next_auth.users(id),
  status           TEXT NOT NULL DEFAULT 'pending',
  expires_at       TIMESTAMPTZ NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_device_sessions_session_id ON device_sessions(session_id);
CREATE INDEX idx_device_sessions_expires ON device_sessions(expires_at);
```

- [ ] **Step 2: Verify table exists**

Run in Supabase SQL editor:
```sql
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'device_sessions' ORDER BY ordinal_position;
```

Expected: 7 columns (id, session_id, device_code_hash, user_id, status, expires_at, created_at).

- [ ] **Step 3: Commit migration file**

```bash
mkdir -p packages/db/migrations
cat > packages/db/migrations/002_device_sessions.sql << 'EOSQL'
CREATE TABLE device_sessions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       UUID UNIQUE NOT NULL,
  device_code_hash TEXT NOT NULL,
  user_id          UUID REFERENCES next_auth.users(id),
  status           TEXT NOT NULL DEFAULT 'pending',
  expires_at       TIMESTAMPTZ NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_device_sessions_session_id ON device_sessions(session_id);
CREATE INDEX idx_device_sessions_expires ON device_sessions(expires_at);
EOSQL
git add packages/db/migrations/002_device_sessions.sql
git commit -m "feat: add device_sessions table migration"
```

---

### Task 2: Create device-session.ts — Supabase CRUD for device sessions

**Files:**
- Create: `apps/web/src/lib/device-session.ts`

- [ ] **Step 1: Create device-session.ts**

```typescript
import { createSupabaseServerClient } from "./supabase";
import { randomUUID, randomBytes, createHash } from "crypto";

const DEVICE_SESSION_TTL = 5 * 60 * 1000; // 5 minutes

export function generateDeviceCode(): string {
  return randomBytes(32).toString("base64url");
}

export function hashDeviceCode(code: string): string {
  return createHash("sha256").update(code).digest("hex");
}

export async function createDeviceSession() {
  const supabase = createSupabaseServerClient();
  const sessionId = randomUUID();
  const deviceCode = generateDeviceCode();
  const deviceCodeHash = hashDeviceCode(deviceCode);
  const expiresAt = new Date(Date.now() + DEVICE_SESSION_TTL).toISOString();

  const { error } = await supabase.from("device_sessions").insert({
    session_id: sessionId,
    device_code_hash: deviceCodeHash,
    status: "pending",
    expires_at: expiresAt,
  });

  if (error) throw new Error(`Failed to create device session: ${error.message}`);

  return { sessionId, deviceCode, expiresIn: 300, interval: 2 };
}

export async function findDeviceSession(sessionId: string) {
  const supabase = createSupabaseServerClient();

  const { data, error } = await supabase
    .from("device_sessions")
    .select("*")
    .eq("session_id", sessionId)
    .gt("expires_at", new Date().toISOString())
    .single();

  if (error || !data) return null;
  return data;
}

export async function approveDeviceSession(sessionId: string, userId: string) {
  const supabase = createSupabaseServerClient();

  const { error } = await supabase
    .from("device_sessions")
    .update({ user_id: userId, status: "approved" })
    .eq("session_id", sessionId)
    .eq("status", "pending")
    .gt("expires_at", new Date().toISOString());

  if (error) throw new Error(`Failed to approve device session: ${error.message}`);
}

export async function deleteDeviceSession(sessionId: string) {
  const supabase = createSupabaseServerClient();

  await supabase
    .from("device_sessions")
    .delete()
    .eq("session_id", sessionId);
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/device-session.ts
git commit -m "feat: add device session CRUD for Supabase"
```

---

### Task 3: Create plugin-auth.ts — JWT sign and verify

**Files:**
- Create: `apps/web/src/lib/plugin-auth.ts`

- [ ] **Step 1: Create plugin-auth.ts**

```typescript
import { SignJWT, jwtVerify } from "jose";

function getSecret() {
  const secret = process.env.NEXTAUTH_SECRET || process.env.AUTH_SECRET;
  if (!secret) throw new Error("Missing NEXTAUTH_SECRET");
  return new TextEncoder().encode(secret);
}

export async function signPluginToken(userId: string): Promise<string> {
  return new SignJWT({ userId })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("7d")
    .sign(getSecret());
}

export async function verifyPluginToken(
  token: string
): Promise<{ userId: string } | null> {
  try {
    const { payload } = await jwtVerify(token, getSecret());
    if (typeof payload.userId === "string") {
      return { userId: payload.userId };
    }
    return null;
  } catch {
    return null;
  }
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/plugin-auth.ts
git commit -m "feat: add plugin JWT sign and verify utilities"
```

---

### Task 4: Create POST /api/auth/device — initiate device session

**Files:**
- Create: `apps/web/src/app/api/auth/device/route.ts`

- [ ] **Step 1: Create the route**

```typescript
import { createDeviceSession } from "@/lib/device-session";
import { NextResponse } from "next/server";

export async function POST() {
  try {
    const session = await createDeviceSession();

    return NextResponse.json({
      session_id: session.sessionId,
      device_code: session.deviceCode,
      expires_in: session.expiresIn,
      interval: session.interval,
    });
  } catch (error) {
    console.error("Device session creation failed:", error);
    return NextResponse.json(
      { error: "Failed to create device session" },
      { status: 500 }
    );
  }
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/api/auth/device/route.ts
git commit -m "feat: add POST /api/auth/device endpoint"
```

---

### Task 5: Create POST /api/auth/device/token — poll and exchange

**Files:**
- Create: `apps/web/src/app/api/auth/device/token/route.ts`

- [ ] **Step 1: Create the route**

```typescript
import { findDeviceSession, deleteDeviceSession, hashDeviceCode } from "@/lib/device-session";
import { signPluginToken } from "@/lib/plugin-auth";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  let body: { session_id?: string; device_code?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { session_id, device_code } = body;

  if (!session_id || !device_code) {
    return NextResponse.json(
      { error: "Missing session_id or device_code" },
      { status: 400 }
    );
  }

  const session = await findDeviceSession(session_id);

  if (!session) {
    return NextResponse.json({ status: "expired" });
  }

  // Verify device_code matches stored hash
  const codeHash = hashDeviceCode(device_code);
  if (codeHash !== session.device_code_hash) {
    return NextResponse.json({ error: "Invalid device code" }, { status: 401 });
  }

  if (session.status === "pending") {
    return NextResponse.json({ status: "pending" });
  }

  if (session.status === "approved" && session.user_id) {
    // Generate JWT and delete the session (one-time use)
    const token = await signPluginToken(session.user_id);
    await deleteDeviceSession(session.session_id);

    return NextResponse.json({ status: "complete", token });
  }

  return NextResponse.json({ status: "expired" });
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/api/auth/device/token/route.ts
git commit -m "feat: add POST /api/auth/device/token polling endpoint"
```

---

### Task 6: Create browser authorize page

**Files:**
- Create: `apps/web/src/app/auth/device/authorize/page.tsx`

- [ ] **Step 1: Create the authorize page**

This is a server component that reads the NextAuth session. If not authenticated, it redirects to login with a callback back to this page. If authenticated, it shows an "Approve" button that calls a server action.

```typescript
import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { approveDeviceSession, findDeviceSession } from "@/lib/device-session";

export default async function AuthorizeDevicePage({
  searchParams,
}: {
  searchParams: Promise<{ session_id?: string }>;
}) {
  const { session_id } = await searchParams;

  if (!session_id) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-destructive">Missing session ID.</p>
      </div>
    );
  }

  const userSession = await auth();

  if (!userSession?.userId) {
    const callbackUrl = `/auth/device/authorize?session_id=${session_id}`;
    redirect(`/login?callbackUrl=${encodeURIComponent(callbackUrl)}`);
  }

  const deviceSession = await findDeviceSession(session_id);

  if (!deviceSession) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center space-y-2">
          <h1 className="text-xl font-semibold">Session Expired</h1>
          <p className="text-muted-foreground">
            This authorization request has expired. Go back to the plugin and try again.
          </p>
        </div>
      </div>
    );
  }

  if (deviceSession.status === "approved") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center space-y-2">
          <h1 className="text-xl font-semibold text-green-600">Plugin Authorized</h1>
          <p className="text-muted-foreground">You can close this tab.</p>
        </div>
      </div>
    );
  }

  async function approve() {
    "use server";

    const userSession = await auth();
    if (!userSession?.userId || !session_id) return;

    await approveDeviceSession(session_id, userSession.userId);
    redirect(`/auth/device/authorize?session_id=${session_id}`);
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-sm space-y-6 text-center">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold">Studio AI</h1>
          <p className="text-muted-foreground">
            Your FL Studio plugin is requesting access to your account.
          </p>
        </div>
        <div className="rounded-lg border p-4 text-sm text-left space-y-1">
          <p><strong>Account:</strong> {userSession.user?.email}</p>
          <p><strong>Access:</strong> Control your DAW via Studio AI</p>
        </div>
        <form action={approve}>
          <button
            type="submit"
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Authorize Plugin
          </button>
        </form>
        <p className="text-xs text-muted-foreground">
          This will allow the Studio AI plugin to act on your behalf.
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/auth/device/authorize/page.tsx
git commit -m "feat: add browser authorize page for device auth flow"
```

---

### Task 7: Update middleware — add device auth to public paths

**Files:**
- Modify: `apps/web/src/middleware.ts`

- [ ] **Step 1: Add device auth paths to public paths**

In `apps/web/src/middleware.ts`, change the `publicPaths` array:

Old:
```typescript
  const publicPaths = ["/login", "/api/auth", "/api/stripe/webhook"];
```

New:
```typescript
  const publicPaths = ["/login", "/api/auth", "/auth/device", "/api/stripe/webhook"];
```

The `/api/auth` prefix already covers `/api/auth/device` and `/api/auth/device/token`. We add `/auth/device` to make the browser authorize page accessible before login (it handles its own auth redirect internally).

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/middleware.ts
git commit -m "feat: add device auth paths to middleware public routes"
```

---

### Task 8: Create plugin-login.tsx — WebView sign-in UI with polling

**Files:**
- Create: `apps/web/src/app/(plugin)/plugin/plugin-login.tsx`

- [ ] **Step 1: Create plugin-login.tsx**

```typescript
"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type AuthState = "idle" | "waiting" | "complete" | "expired" | "error";

export function PluginLogin({
  onToken,
}: {
  onToken: (token: string) => void;
}) {
  const [state, setState] = useState<AuthState>("idle");
  const [error, setError] = useState("");

  const startAuth = useCallback(async () => {
    setState("waiting");
    setError("");

    try {
      const res = await fetch("/api/auth/device", { method: "POST" });
      if (!res.ok) {
        setState("error");
        setError("Failed to start authentication.");
        return;
      }

      const { session_id, device_code, interval } = await res.json();

      // Open system browser for authorization
      window.open(
        `${window.location.origin}/auth/device/authorize?session_id=${session_id}`,
        "_blank"
      );

      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          const pollRes = await fetch("/api/auth/device/token", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id, device_code }),
          });

          if (!pollRes.ok) {
            clearInterval(pollInterval);
            setState("error");
            setError("Authentication failed. Please try again.");
            return;
          }

          const data = await pollRes.json();

          if (data.status === "complete") {
            clearInterval(pollInterval);
            localStorage.setItem("studio-ai-token", data.token);
            setState("complete");
            onToken(data.token);
          } else if (data.status === "expired") {
            clearInterval(pollInterval);
            setState("expired");
          }
        } catch {
          // Network error — continue polling
        }
      }, (interval || 2) * 1000);

      // Stop polling after 5 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        setState((current) => (current === "waiting" ? "expired" : current));
      }, 5 * 60 * 1000);
    } catch {
      setState("error");
      setError("Connection error. Is the server running?");
    }
  }, [onToken]);

  return (
    <div className="flex h-full items-center justify-center bg-background">
      <Card className="w-full max-w-sm p-6 space-y-4">
        <div className="text-center space-y-1">
          <h1 className="text-xl font-semibold">Studio AI</h1>
          <p className="text-sm text-muted-foreground">
            Sign in to connect your DAW
          </p>
        </div>

        {state === "idle" && (
          <Button onClick={startAuth} className="w-full">
            Sign in with Google
          </Button>
        )}

        {state === "waiting" && (
          <div className="space-y-3 text-center">
            <div className="flex items-center justify-center space-x-2">
              <div className="h-2 w-2 animate-pulse rounded-full bg-primary" />
              <span className="text-sm text-muted-foreground">
                Waiting for authorization...
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Complete sign-in in the browser window that just opened.
            </p>
          </div>
        )}

        {state === "expired" && (
          <div className="space-y-3">
            <p className="text-sm text-center text-muted-foreground">
              Authorization expired. Please try again.
            </p>
            <Button onClick={startAuth} className="w-full" variant="outline">
              Try again
            </Button>
          </div>
        )}

        {state === "error" && (
          <div className="space-y-3">
            <p className="text-sm text-destructive text-center">{error}</p>
            <Button onClick={startAuth} className="w-full" variant="outline">
              Try again
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/plugin-login.tsx
git commit -m "feat: add plugin login UI with device auth polling"
```

---

### Task 9: Update plugin page — client component with localStorage token check

**Files:**
- Modify: `apps/web/src/app/(plugin)/plugin/page.tsx`

- [ ] **Step 1: Rewrite plugin page as client component**

Replace the entire file. The page checks localStorage for an existing token, validates it, and shows either the login or chat:

```typescript
"use client";

import { useEffect, useState, useCallback } from "react";
import { PluginChat } from "./plugin-chat";
import { PluginLogin } from "./plugin-login";

export default function PluginPage() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("studio-ai-token");
    if (stored) {
      // Quick client-side expiry check (JWT payload is base64url)
      try {
        const payload = JSON.parse(atob(stored.split(".")[1]));
        if (payload.exp && payload.exp * 1000 > Date.now()) {
          setToken(stored);
        } else {
          localStorage.removeItem("studio-ai-token");
        }
      } catch {
        localStorage.removeItem("studio-ai-token");
      }
    }
    setReady(true);
  }, []);

  const handleToken = useCallback((newToken: string) => {
    setToken(newToken);
  }, []);

  if (!ready) return null;

  if (!token) {
    return <PluginLogin onToken={handleToken} />;
  }

  return <PluginChat token={token} />;
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds (PluginChat token prop will be added in next task).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/page.tsx
git commit -m "feat: plugin page with localStorage token check and device auth"
```

---

### Task 10: Update PluginChat — accept token prop, use Bearer header

**Files:**
- Modify: `apps/web/src/app/(plugin)/plugin/plugin-chat.tsx`

- [ ] **Step 1: Add token prop and Bearer header**

Make these changes to `plugin-chat.tsx`:

1. Add `useMemo` to React imports:
```typescript
import { useRef, useEffect, useState, useMemo } from "react";
```

2. Replace the module-level transport and component signature:

Old:
```typescript
const transport = new DefaultChatTransport({ api: "/api/ai/execute" });

export function PluginChat() {
  const { messages, sendMessage, status, error } = useChat({ transport });
```

New:
```typescript
export function PluginChat({ token }: { token: string }) {
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: "/api/ai/execute",
        headers: { Authorization: `Bearer ${token}` },
      }),
    [token]
  );
  const { messages, sendMessage, status, error } = useChat({ transport });
```

Everything else in the component stays identical.

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/plugin-chat.tsx
git commit -m "feat: PluginChat accepts token prop with Bearer auth"
```

---

### Task 11: Update API execute route — restore Bearer token path

**Files:**
- Modify: `apps/web/src/app/api/ai/execute/route.ts`

- [ ] **Step 1: Restore Bearer token auth**

Add the import at the top of the file:
```typescript
import { verifyPluginToken } from "@/lib/plugin-auth";
```

Replace the `getUserId` function:

Old:
```typescript
async function getUserId(): Promise<string | null> {
  const session = await auth();
  return session?.userId ?? null;
}
```

New:
```typescript
async function getUserId(req: Request): Promise<string | null> {
  // 1. Try Bearer token (plugin WebView)
  const authHeader = req.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const result = await verifyPluginToken(authHeader.slice(7));
    if (result) return result.userId;
  }
  // 2. Fall back to session cookie (browser dashboard)
  const session = await auth();
  return session?.userId ?? null;
}
```

Also update the call site in the `POST` function — change `getUserId()` to `getUserId(req)`.

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/api/ai/execute/route.ts
git commit -m "feat: restore Bearer token auth path in API execute route"
```

---

### Task 12: Update middleware — allow unauthenticated access to /plugin

**Files:**
- Modify: `apps/web/src/middleware.ts`

- [ ] **Step 1: Add /plugin to public paths**

The plugin page is now a client component that handles its own auth via localStorage token. It must be accessible without a NextAuth session.

In `apps/web/src/middleware.ts`, change the `publicPaths` array:

Old:
```typescript
  const publicPaths = ["/login", "/api/auth", "/auth/device", "/api/stripe/webhook"];
```

New:
```typescript
  const publicPaths = ["/login", "/api/auth", "/auth/device", "/api/stripe/webhook", "/plugin"];
```

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/middleware.ts
git commit -m "feat: allow unauthenticated access to /plugin for device auth flow"
```

---

### Task 13: Full build verification and manual smoke test

- [ ] **Step 1: Full build**

Run: `pnpm build`
Expected: All packages build successfully.

- [ ] **Step 2: Manual smoke test**

Start the dev server: `pnpm --filter web dev`

Test these scenarios:
1. Open `http://localhost:3000/plugin?context=plugin` — should show "Sign in with Google" button
2. Click button — system browser opens to authorize page
3. If not logged in to dashboard — redirects to Google Sign-In, then back to authorize page
4. Click "Authorize Plugin" — shows "Plugin authorized! You can close this tab."
5. Back in WebView — polling detects approval, receives token, shows chat
6. Refresh the plugin page — localStorage has token, chat loads directly (no sign-in)
7. Open `http://localhost:3000/dashboard` — dashboard still works with NextAuth session
8. Send a chat message — API call works with Bearer token

- [ ] **Step 3: Commit if any fixes needed**

```bash
git commit -m "fix: address issues found during smoke test"
```
