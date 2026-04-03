# Plugin Auth Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 6-character code-based plugin authentication with direct Google OAuth in the WebView, using the same NextAuth session as the dashboard.

**Architecture:** Remove the custom JWT/code exchange system. The plugin WebView loads `/plugin?context=plugin`, NextAuth middleware handles auth (redirect to Google Sign-In if needed), and the session cookie authenticates all API calls. The Rust plugin still receives the JWT via IPC for WebSocket auth to FastAPI.

**Tech Stack:** NextAuth v5, Next.js middleware, React server components

---

### Task 1: Simplify middleware — remove plugin token/code special cases

**Files:**
- Modify: `apps/web/src/middleware.ts`

- [ ] **Step 1: Rewrite middleware to unify plugin and dashboard auth**

Replace the entire middleware with this simplified version that treats plugin routes the same as dashboard routes:

```typescript
import { auth } from "@/lib/auth";
import { NextResponse } from "next/server";

export default auth((req) => {
  const { pathname, searchParams } = req.nextUrl;
  const isAuthenticated = !!req.auth;

  // Public routes that don't require auth
  const publicPaths = ["/", "/login", "/api/auth", "/api/stripe/webhook"];
  const isPublic = publicPaths.some((path) => pathname.startsWith(path));

  if (isPublic) return NextResponse.next();

  // All protected routes (dashboard + plugin): require NextAuth session
  if (!isAuthenticated) {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    // Preserve context param so after login we redirect back correctly
    const callbackUrl = req.nextUrl.href;
    loginUrl.searchParams.set("callbackUrl", callbackUrl);
    return NextResponse.redirect(loginUrl);
  }

  // Plugin context rewrite: / with ?context=plugin → /plugin
  const isPluginContext = searchParams.get("context") === "plugin";
  if (isPluginContext && pathname === "/") {
    const pluginUrl = new URL("/plugin", req.nextUrl.origin);
    pluginUrl.search = searchParams.toString();
    return NextResponse.rewrite(pluginUrl);
  }

  return NextResponse.next();
});

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
  ],
};
```

- [ ] **Step 2: Verify middleware works**

Run: `pnpm --filter web build`
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/middleware.ts
git commit -m "refactor: simplify middleware to use unified NextAuth session for plugin and dashboard"
```

---

### Task 2: Convert plugin page from client to server component

**Files:**
- Modify: `apps/web/src/app/(plugin)/plugin/page.tsx`

- [ ] **Step 1: Rewrite plugin page as server component**

Replace the entire file. The page reads the session server-side and renders PluginChat directly. No more token detection, sessionStorage, or URL params:

```typescript
import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { PluginChat } from "./plugin-chat";

export default async function PluginPage() {
  const session = await auth();

  if (!session?.userId) {
    redirect("/login");
  }

  return <PluginChat />;
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds. (PluginChat will need updating in next task.)

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/page.tsx
git commit -m "refactor: convert plugin page to server component with NextAuth session"
```

---

### Task 3: Update PluginChat to use session cookie instead of Bearer token

**Files:**
- Modify: `apps/web/src/app/(plugin)/plugin/plugin-chat.tsx`

- [ ] **Step 1: Remove token prop and Bearer header from PluginChat**

The component no longer receives a token. API calls use the session cookie automatically. Replace the full file:

```typescript
"use client";

import { useChat } from "@ai-sdk/react";
import { isToolUIPart, getToolName } from "ai";
import { useRef, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";

export function PluginChat() {
  const { messages, sendMessage, status, error } = useChat({
    api: "/api/ai/execute",
  });
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isLoading = status === "streaming" || status === "submitted";

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    sendMessage({ text: input });
    setInput("");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center text-muted-foreground">
              <h2 className="text-lg font-semibold">Studio AI</h2>
              <p className="mt-1 text-sm">
                Tell me what to do in your DAW. Try &quot;Set the BPM to
                128&quot; or &quot;Show me the project state&quot;.
              </p>
            </div>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${
              message.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <Card
              className={`max-w-[80%] px-4 py-3 ${
                message.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted"
              }`}
            >
              {message.parts.map((part, i) => {
                if (part.type === "text") {
                  return (
                    <div key={i} className="text-sm whitespace-pre-wrap">
                      {part.text}
                    </div>
                  );
                }

                if (isToolUIPart(part)) {
                  const toolName = getToolName(part);
                  const toolPart = part as {
                    type: string;
                    toolName?: string;
                    state: string;
                    input?: unknown;
                    output?: unknown;
                  };
                  return (
                    <div
                      key={i}
                      className="mt-2 rounded border bg-background/50 p-2 text-xs"
                    >
                      <div className="font-mono text-muted-foreground">
                        {toolName}(
                        {toolPart.input !== undefined
                          ? JSON.stringify(toolPart.input)
                          : ""}
                        )
                      </div>
                      {toolPart.state === "output-available" &&
                        toolPart.output !== undefined && (
                          <div className="mt-1 font-mono">
                            {JSON.stringify(toolPart.output)}
                          </div>
                        )}
                    </div>
                  );
                }

                return null;
              })}
            </Card>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <Card className="bg-muted px-4 py-3">
              <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                <div className="h-2 w-2 animate-pulse rounded-full bg-current" />
                <span>Thinking...</span>
              </div>
            </Card>
          </div>
        )}

        {error && (
          <div className="flex justify-center">
            <Card className="border-destructive bg-destructive/10 px-4 py-3">
              <p className="text-sm text-destructive">
                Error: {error.message}
              </p>
            </Card>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="border-t p-4">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Tell your DAW what to do..."
            disabled={isLoading}
            className="flex-1"
            autoFocus
          />
          <Button type="submit" disabled={isLoading || !input.trim()}>
            Send
          </Button>
        </form>
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
git add apps/web/src/app/\(plugin\)/plugin/plugin-chat.tsx
git commit -m "refactor: remove Bearer token from PluginChat, use session cookie"
```

---

### Task 4: Simplify API execute route — remove Bearer token path

**Files:**
- Modify: `apps/web/src/app/api/ai/execute/route.ts`

- [ ] **Step 1: Replace getUserId with session-only auth**

Remove the `verifyPluginToken` import and the Bearer token branch. Replace the `getUserId` function at the top of the file:

Old code to replace:
```typescript
import { verifyPluginToken } from "@/lib/plugin-auth";

async function getUserId(req: Request): Promise<string | null> {
  // 1. Try Bearer token (plugin WebView)
  const authHeader = req.headers.get("authorization");
  if (authHeader?.startsWith("Bearer ")) {
    const result = await verifyPluginToken(authHeader.slice(7));
    if (result) return result.userId;
  }
  // 2. Fall back to session cookie (browser)
  const session = await auth();
  return session?.userId ?? null;
}
```

New code:
```typescript
async function getUserId(): Promise<string | null> {
  const session = await auth();
  return session?.userId ?? null;
}
```

Also update the call site in the `POST` function — change `getUserId(req)` to `getUserId()`.

- [ ] **Step 2: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/api/ai/execute/route.ts
git commit -m "refactor: simplify API auth to use only NextAuth session"
```

---

### Task 5: Remove sidebar link to deleted plugin connection page

**Files:**
- Modify: `apps/web/src/components/layout/dashboard-sidebar.tsx`

- [ ] **Step 1: Remove Plugin nav item**

In `dashboard-sidebar.tsx`, remove the Plugin entry from the `navItems` array:

```typescript
const navItems = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Projects", href: "/dashboard/projects" },
  { label: "Billing", href: "/dashboard/billing" },
  { label: "Settings", href: "/dashboard/settings" },
];
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/components/layout/dashboard-sidebar.tsx
git commit -m "refactor: remove Plugin link from dashboard sidebar"
```

---

### Task 6: Delete obsolete auth files

**Files:**
- Delete: `apps/web/src/lib/plugin-codes.ts`
- Delete: `apps/web/src/lib/plugin-auth.ts`
- Delete: `apps/web/src/app/(plugin)/plugin/plugin-login.tsx`
- Delete: `apps/web/src/app/api/auth/plugin-token/route.ts`
- Delete: `apps/web/src/app/dashboard/plugin/page.tsx`

- [ ] **Step 1: Delete all obsolete files**

```bash
rm apps/web/src/lib/plugin-codes.ts
rm apps/web/src/lib/plugin-auth.ts
rm apps/web/src/app/\(plugin\)/plugin/plugin-login.tsx
rm apps/web/src/app/api/auth/plugin-token/route.ts
rm -rf apps/web/src/app/dashboard/plugin
```

- [ ] **Step 2: Check for remaining imports of deleted modules**

```bash
grep -r "plugin-codes\|plugin-auth\|plugin-login\|plugin-token" apps/web/src/ --include="*.ts" --include="*.tsx"
```

Expected: No matches. If any remain, remove those imports.

- [ ] **Step 3: Verify build**

Run: `pnpm --filter web build`
Expected: Build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
git add -A apps/web/src/lib/plugin-codes.ts apps/web/src/lib/plugin-auth.ts apps/web/src/app/\(plugin\)/plugin/plugin-login.tsx apps/web/src/app/api/auth/plugin-token apps/web/src/app/dashboard/plugin
git commit -m "chore: delete obsolete plugin code auth files"
```

---

### Task 7: Verify full build and manual smoke test

- [ ] **Step 1: Full build**

Run: `pnpm build`
Expected: All packages build successfully.

- [ ] **Step 2: Manual smoke test**

Start the dev server: `pnpm --filter web dev`

Test these scenarios:
1. Open `http://localhost:3000/plugin?context=plugin` in a private window → should redirect to Google Sign-In
2. Complete Google Sign-In → should redirect back to `/plugin` with chat UI
3. Open `http://localhost:3000/dashboard` → should work normally with session
4. Send a chat message in plugin UI → should work (session cookie auth)

- [ ] **Step 3: Commit (if any fixes were needed)**

```bash
git commit -m "fix: address issues found during smoke test"
```
