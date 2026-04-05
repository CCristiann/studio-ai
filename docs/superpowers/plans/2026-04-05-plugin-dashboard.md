# Plugin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plugin's chat-only view with a professional dashboard shell — icon-rail sidebar, expandable panels (connection, presets, settings, help), Claude-style chat input, and an onboarding wizard.

**Architecture:** Incremental refactor of `(plugin)/plugin/`. The existing `page.tsx` auth orchestrator stays; `PluginChat` is replaced by `PluginDashboard` which wraps chat in a shadcn `Sidebar` (`collapsible="icon"`). Panels are state-driven, not route-based. New API routes under `/api/plugin/` for presets CRUD and user preferences.

**Tech Stack:** Next.js 15 App Router, shadcn/ui (sidebar, tooltip, popover, scroll-area, skeleton, collapsible), Tailwind CSS 4, Supabase, Lucide icons, TypeScript.

**Spec:** `docs/superpowers/specs/2026-04-05-plugin-dashboard-design.md`

---

## File Map

### New Files
| File | Purpose |
|------|---------|
| `apps/web/src/app/(plugin)/plugin/plugin-dashboard.tsx` | Dashboard shell — SidebarProvider, useChat, state management |
| `apps/web/src/app/(plugin)/plugin/components/plugin-sidebar.tsx` | Sidebar with icon rail, menu items, user avatar |
| `apps/web/src/app/(plugin)/plugin/components/plugin-topbar.tsx` | Top bar — chat title, project info, new chat button |
| `apps/web/src/app/(plugin)/plugin/components/chat-input.tsx` | Claude-style rounded pill input |
| `apps/web/src/app/(plugin)/plugin/components/chat-messages.tsx` | Message list with ScrollArea |
| `apps/web/src/app/(plugin)/plugin/components/panels/connection-panel.tsx` | Cloud relay + DAW bridge status |
| `apps/web/src/app/(plugin)/plugin/components/panels/presets-panel.tsx` | Preset list, create, send to chat |
| `apps/web/src/app/(plugin)/plugin/components/panels/settings-panel.tsx` | Sign out, token info |
| `apps/web/src/app/(plugin)/plugin/components/panels/help-panel.tsx` | Capabilities, example prompts, docs link |
| `apps/web/src/app/(plugin)/plugin/components/onboarding-wizard.tsx` | Dialog-based step wizard |
| `apps/web/src/app/api/plugin/presets/route.ts` | GET/POST presets |
| `apps/web/src/app/api/plugin/presets/[id]/route.ts` | PUT/DELETE preset by ID |
| `apps/web/src/app/api/plugin/preferences/route.ts` | GET/PATCH user preferences |
| `packages/db/migrations/007_presets.sql` | Presets table |
| `packages/db/migrations/008_user_preferences.sql` | User preferences table |

### Modified Files
| File | Change |
|------|--------|
| `apps/web/src/app/(plugin)/layout.tsx` | Add `dark` class, update flex for SidebarProvider |
| `apps/web/src/app/(plugin)/plugin/page.tsx` | Swap `PluginChat` for `PluginDashboard` |
| `apps/web/src/types/webview.d.ts` | Add `getConnectionStatus` / `connectionStatus` IPC types |

### Unchanged Files (referenced)
| File | Why |
|------|-----|
| `apps/web/src/lib/plugin-auth.ts` | Used by API routes for `verifyPluginToken` |
| `apps/web/src/lib/supabase.ts` | Used by API routes for DB access |
| `apps/web/src/middleware.ts` | No changes needed |

---

## Task 1: Install shadcn components and create database migrations

**Files:**
- Modify: `apps/web/package.json` (via shadcn CLI)
- Create: `packages/db/migrations/007_presets.sql`
- Create: `packages/db/migrations/008_user_preferences.sql`

- [ ] **Step 1: Install shadcn components**

Run from `apps/web/`:

```bash
cd apps/web && pnpm dlx shadcn@latest add sidebar tooltip popover scroll-area skeleton collapsible
```

This installs the components to `src/components/ui/` and adds any Radix dependencies to `package.json`.

- [ ] **Step 2: Verify sidebar component was installed**

```bash
ls apps/web/src/components/ui/sidebar.tsx apps/web/src/components/ui/tooltip.tsx apps/web/src/components/ui/scroll-area.tsx
```

Expected: all three files exist.

- [ ] **Step 3: Create presets migration**

Create `packages/db/migrations/007_presets.sql`:

```sql
-- Presets: saved AI prompt templates per user
CREATE TABLE public.presets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  prompt TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_presets_user_id ON public.presets(user_id);

COMMENT ON COLUMN public.presets.user_id IS 'References next_auth.users.id — no FK because NextAuth manages user lifecycle externally';
```

- [ ] **Step 4: Create user_preferences migration**

Create `packages/db/migrations/008_user_preferences.sql`:

```sql
-- User preferences: onboarding state and future settings
CREATE TABLE public.user_preferences (
  user_id TEXT PRIMARY KEY,
  onboarding_completed BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON COLUMN public.user_preferences.user_id IS 'References next_auth.users.id — no FK because NextAuth manages user lifecycle externally';
```

- [ ] **Step 5: Apply migrations to Supabase**

Use the Supabase MCP tool `apply_migration` to run both migrations against the project database.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/ui/ apps/web/package.json apps/web/pnpm-lock.yaml packages/db/migrations/007_presets.sql packages/db/migrations/008_user_preferences.sql
git commit -m "feat: install shadcn sidebar components and add presets/preferences migrations"
```

---

## Task 2: Create API routes for presets and preferences

**Files:**
- Create: `apps/web/src/app/api/plugin/presets/route.ts`
- Create: `apps/web/src/app/api/plugin/presets/[id]/route.ts`
- Create: `apps/web/src/app/api/plugin/preferences/route.ts`

- [ ] **Step 1: Create presets list/create route**

Create `apps/web/src/app/api/plugin/presets/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { verifyPluginToken } from "@/lib/plugin-auth";
import { createSupabaseServerClient } from "@/lib/supabase";

async function getPluginUserId(req: Request): Promise<string | null> {
  const authHeader = req.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) return null;
  const result = await verifyPluginToken(authHeader.slice(7));
  return result?.userId ?? null;
}

export async function GET(req: Request) {
  const userId = await getPluginUserId(req);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const supabase = createSupabaseServerClient();
  const { data, error } = await supabase
    .from("presets")
    .select("id, name, description, prompt, created_at, updated_at")
    .eq("user_id", userId)
    .order("created_at", { ascending: true });

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ presets: data });
}

export async function POST(req: Request) {
  const userId = await getPluginUserId(req);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const { name, description, prompt } = body;

  if (!name || !prompt) {
    return NextResponse.json({ error: "name and prompt are required" }, { status: 400 });
  }

  const supabase = createSupabaseServerClient();
  const { data, error } = await supabase
    .from("presets")
    .insert({ user_id: userId, name, description: description ?? null, prompt })
    .select("id, name, description, prompt, created_at, updated_at")
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ preset: data }, { status: 201 });
}
```

- [ ] **Step 2: Create preset update/delete route**

Create `apps/web/src/app/api/plugin/presets/[id]/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { verifyPluginToken } from "@/lib/plugin-auth";
import { createSupabaseServerClient } from "@/lib/supabase";

async function getPluginUserId(req: Request): Promise<string | null> {
  const authHeader = req.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) return null;
  const result = await verifyPluginToken(authHeader.slice(7));
  return result?.userId ?? null;
}

export async function PUT(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const userId = await getPluginUserId(req);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const body = await req.json();
  const updates: Record<string, unknown> = { updated_at: new Date().toISOString() };
  if (body.name !== undefined) updates.name = body.name;
  if (body.description !== undefined) updates.description = body.description;
  if (body.prompt !== undefined) updates.prompt = body.prompt;

  const supabase = createSupabaseServerClient();
  const { data, error } = await supabase
    .from("presets")
    .update(updates)
    .eq("id", id)
    .eq("user_id", userId)
    .select("id, name, description, prompt, created_at, updated_at")
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!data) return NextResponse.json({ error: "Not found" }, { status: 404 });

  return NextResponse.json({ preset: data });
}

export async function DELETE(
  req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const userId = await getPluginUserId(req);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { id } = await params;
  const supabase = createSupabaseServerClient();
  const { error } = await supabase
    .from("presets")
    .delete()
    .eq("id", id)
    .eq("user_id", userId);

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ success: true });
}
```

- [ ] **Step 3: Create preferences route**

Create `apps/web/src/app/api/plugin/preferences/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { verifyPluginToken } from "@/lib/plugin-auth";
import { createSupabaseServerClient } from "@/lib/supabase";

async function getPluginUserId(req: Request): Promise<string | null> {
  const authHeader = req.headers.get("authorization");
  if (!authHeader?.startsWith("Bearer ")) return null;
  const result = await verifyPluginToken(authHeader.slice(7));
  return result?.userId ?? null;
}

export async function GET(req: Request) {
  const userId = await getPluginUserId(req);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const supabase = createSupabaseServerClient();
  const { data } = await supabase
    .from("user_preferences")
    .select("onboarding_completed")
    .eq("user_id", userId)
    .single();

  // Return defaults if no row exists yet
  return NextResponse.json({
    preferences: data ?? { onboarding_completed: false },
  });
}

export async function PATCH(req: Request) {
  const userId = await getPluginUserId(req);
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const supabase = createSupabaseServerClient();

  const { data, error } = await supabase
    .from("user_preferences")
    .upsert(
      {
        user_id: userId,
        onboarding_completed: body.onboarding_completed ?? false,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "user_id" }
    )
    .select("onboarding_completed")
    .single();

  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  return NextResponse.json({ preferences: data });
}
```

- [ ] **Step 4: Update middleware to allow /api/plugin routes**

Check that `/api/plugin` routes pass through. The existing middleware allows `/api/auth` and `/api/ai` as public. Since plugin API routes use Bearer token auth (not NextAuth sessions), they need to be accessible without a session.

In `apps/web/src/middleware.ts`, the `publicPaths` array already includes `/api/auth` and `/api/ai`. Add `/api/plugin`:

```typescript
const publicPaths = ["/", "/login", "/api/auth", "/api/ai", "/api/plugin", "/api/stripe/webhook"];
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/api/plugin/ apps/web/src/middleware.ts
git commit -m "feat: add presets CRUD and preferences API routes for plugin"
```

---

## Task 3: Update WebView types and plugin layout

**Files:**
- Modify: `apps/web/src/types/webview.d.ts`
- Modify: `apps/web/src/app/(plugin)/layout.tsx`

- [ ] **Step 1: Extend WebView IPC types**

Replace `apps/web/src/types/webview.d.ts`:

```typescript
interface PluginConnectionStatus {
  cloud: { connected: boolean; latency_ms?: number };
  bridge: { connected: boolean; daw?: string; project?: string };
}

interface PluginMessage {
  type: string;
  payload?: Record<string, unknown>;
}

interface Window {
  ipc?: {
    postMessage(message: string): void;
  };
  sendToPlugin?: (msg: PluginMessage) => void;
  onPluginMessage?: (msg: PluginMessage) => void;
}
```

- [ ] **Step 2: Update plugin layout for dark mode and SidebarProvider**

Replace `apps/web/src/app/(plugin)/layout.tsx`:

```typescript
export default function PluginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="dark flex h-screen w-screen overflow-hidden bg-[#0a0a0a]">
      {children}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/types/webview.d.ts apps/web/src/app/\(plugin\)/layout.tsx
git commit -m "feat: extend WebView IPC types and update plugin layout for dark mode"
```

---

## Task 4: Build chat-input and chat-messages components

**Files:**
- Create: `apps/web/src/app/(plugin)/plugin/components/chat-input.tsx`
- Create: `apps/web/src/app/(plugin)/plugin/components/chat-messages.tsx`

- [ ] **Step 1: Create Claude-style chat input**

Create `apps/web/src/app/(plugin)/plugin/components/chat-input.tsx`:

```typescript
"use client";

import { useRef, useEffect } from "react";
import { ArrowRight } from "lucide-react";

export function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}) {
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !disabled) onSubmit();
    }
  };

  return (
    <div className="px-5 pb-5 pt-3">
      <div className="flex items-end gap-2.5 rounded-3xl border border-white/5 bg-white/[0.03] px-5 py-1.5 transition-colors hover:border-white/10 focus-within:border-white/10">
        <textarea
          ref={inputRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask Studio AI anything..."
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none bg-transparent py-2.5 text-[13px] leading-relaxed text-foreground placeholder:text-[#444] focus:outline-none disabled:opacity-50"
        />
        <button
          onClick={onSubmit}
          disabled={disabled || !value.trim()}
          className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-black shadow-sm transition-transform hover:scale-105 disabled:opacity-30 disabled:hover:scale-100"
        >
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create chat messages component**

Create `apps/web/src/app/(plugin)/plugin/components/chat-messages.tsx`:

```typescript
"use client";

import { useRef, useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { isToolUIPart, getToolName } from "ai";
import type { UIMessage } from "ai";

export function ChatMessages({
  messages,
  isLoading,
  error,
}: {
  messages: UIMessage[];
  isLoading: boolean;
  error: Error | undefined;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-b from-neutral-200 to-neutral-400 text-sm font-bold text-black">
            AI
          </div>
          <p className="text-sm text-[#555]">
            Tell me what to do in your DAW.
          </p>
        </div>
      </div>
    );
  }

  return (
    <ScrollArea className="flex-1">
      <div className="space-y-5 px-6 py-5">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex gap-3 ${
              message.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            {message.role === "assistant" && (
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] bg-gradient-to-b from-neutral-200 to-neutral-400 text-[10px] font-bold text-black">
                AI
              </div>
            )}
            <div className="max-w-[85%]">
              {message.parts.map((part, i) => {
                if (part.type === "text") {
                  return (
                    <div
                      key={i}
                      className={`rounded-2xl px-4 py-3 text-[13px] leading-relaxed ${
                        message.role === "user"
                          ? "bg-white/[0.08] text-[#f0f0f0]"
                          : "bg-white/[0.04] text-[#c8c8c8]"
                      }`}
                    >
                      {part.text}
                    </div>
                  );
                }

                if (isToolUIPart(part)) {
                  const toolName = getToolName(part);
                  const toolPart = part as {
                    type: string;
                    state: string;
                    input?: unknown;
                    output?: unknown;
                  };
                  return (
                    <div
                      key={i}
                      className="mt-2 rounded-xl border border-green-500/10 bg-green-500/[0.04] px-3.5 py-2.5 font-mono text-[11.5px] leading-relaxed"
                    >
                      <div className="text-[#666]">
                        {toolName}(
                        {toolPart.input !== undefined
                          ? JSON.stringify(toolPart.input)
                          : ""}
                        )
                      </div>
                      {toolPart.state === "output-available" &&
                        toolPart.output !== undefined && (
                          <div className="mt-1 text-green-400">
                            &#10003; {JSON.stringify(toolPart.output)}
                          </div>
                        )}
                    </div>
                  );
                }

                return null;
              })}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-3">
            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[9px] bg-gradient-to-b from-neutral-200 to-neutral-400 text-[10px] font-bold text-black">
              AI
            </div>
            <div className="rounded-2xl bg-white/[0.04] px-4 py-3">
              <div className="flex items-center gap-2 text-[13px] text-[#555]">
                <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                Thinking...
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="mx-auto max-w-sm rounded-xl border border-red-500/10 bg-red-500/[0.04] px-4 py-3 text-center text-[13px] text-red-400">
            {error.message}
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/components/chat-input.tsx apps/web/src/app/\(plugin\)/plugin/components/chat-messages.tsx
git commit -m "feat: add Claude-style chat input and message list components"
```

---

## Task 5: Build the plugin sidebar

**Files:**
- Create: `apps/web/src/app/(plugin)/plugin/components/plugin-sidebar.tsx`
- Create: `apps/web/src/app/(plugin)/plugin/components/plugin-topbar.tsx`

- [ ] **Step 1: Create plugin sidebar component**

Create `apps/web/src/app/(plugin)/plugin/components/plugin-sidebar.tsx`:

```typescript
"use client";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  MessageSquare,
  Globe,
  Zap,
  HelpCircle,
  Settings,
  LogOut,
} from "lucide-react";

export type PanelId = "chat" | "connection" | "presets" | "settings" | "help";

const topItems: { id: PanelId; label: string; icon: typeof MessageSquare }[] = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "connection", label: "Connection", icon: Globe },
  { id: "presets", label: "Quick Actions", icon: Zap },
];

const bottomItems: { id: PanelId; label: string; icon: typeof HelpCircle }[] = [
  { id: "help", label: "Help", icon: HelpCircle },
  { id: "settings", label: "Settings", icon: Settings },
];

export function PluginSidebar({
  activePanel,
  onPanelChange,
  onSignOut,
  connectionStatus,
}: {
  activePanel: PanelId;
  onPanelChange: (panel: PanelId) => void;
  onSignOut: () => void;
  connectionStatus: "connected" | "partial" | "disconnected";
}) {
  const { toggleSidebar, state } = useSidebar();

  const handleClick = (panelId: PanelId) => {
    if (state === "collapsed") {
      onPanelChange(panelId);
      toggleSidebar();
    } else if (activePanel === panelId) {
      toggleSidebar();
    } else {
      onPanelChange(panelId);
    }
  };

  const statusColor =
    connectionStatus === "connected"
      ? "bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]"
      : connectionStatus === "partial"
        ? "bg-yellow-500 shadow-[0_0_8px_rgba(234,179,8,0.4)]"
        : "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.4)]";

  const renderItem = (item: { id: PanelId; label: string; icon: typeof MessageSquare }) => (
    <SidebarMenuItem key={item.id}>
      <Tooltip>
        <TooltipTrigger asChild>
          <SidebarMenuButton
            isActive={activePanel === item.id}
            onClick={() => handleClick(item.id)}
            className="relative"
          >
            <item.icon className="h-5 w-5" />
            <span className="group-data-[collapsible=icon]:hidden">
              {item.label}
            </span>
          </SidebarMenuButton>
        </TooltipTrigger>
        <TooltipContent side="right" className="group-data-[state=expanded]:hidden">
          {item.label}
        </TooltipContent>
      </Tooltip>
    </SidebarMenuItem>
  );

  return (
    <Sidebar
      collapsible="icon"
      variant="sidebar"
      className="border-r-0 bg-[#080808] [--sidebar-width:320px] [--sidebar-width-icon:60px]"
    >
      <SidebarHeader className="flex items-center justify-center py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-gradient-to-b from-neutral-200 to-neutral-400 text-[15px] font-extrabold text-black shadow-md">
          S
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {topItems.map(renderItem)}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          {bottomItems.map(renderItem)}
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton className="h-auto py-2">
                  <div className="relative">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-b from-indigo-400 to-violet-500 text-xs font-bold text-white shadow-md">
                      U
                    </div>
                    <div
                      className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[#080808] ${statusColor}`}
                    />
                  </div>
                  <span className="group-data-[collapsible=icon]:hidden text-sm">
                    Account
                  </span>
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent side="right" align="end">
                <DropdownMenuItem onClick={onSignOut}>
                  <LogOut className="mr-2 h-4 w-4" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
```

- [ ] **Step 2: Create plugin topbar component**

Create `apps/web/src/app/(plugin)/plugin/components/plugin-topbar.tsx`:

```typescript
"use client";

import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function PluginTopbar({
  projectName,
  dawName,
  isConnected,
}: {
  projectName?: string;
  dawName?: string;
  isConnected: boolean;
}) {
  return (
    <div className="flex h-12 items-center gap-3 px-5">
      <span className="text-[13px] font-medium text-foreground tracking-tight">
        New Chat
      </span>
      <div className="flex-1" />
      {dawName && (
        <div className="flex items-center gap-1.5 text-[11px] text-[#3a3a3a]">
          {isConnected && (
            <div className="h-1.5 w-1.5 rounded-full bg-green-500" />
          )}
          <span>
            {dawName}
            {projectName ? ` — ${projectName}` : ""}
          </span>
        </div>
      )}
      <button className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/[0.03] transition-colors hover:bg-white/[0.06]">
        <Plus className="h-3.5 w-3.5 text-[#555]" />
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/components/plugin-sidebar.tsx apps/web/src/app/\(plugin\)/plugin/components/plugin-topbar.tsx
git commit -m "feat: add plugin sidebar with icon rail and topbar components"
```

---

## Task 6: Build panel components

**Files:**
- Create: `apps/web/src/app/(plugin)/plugin/components/panels/connection-panel.tsx`
- Create: `apps/web/src/app/(plugin)/plugin/components/panels/presets-panel.tsx`
- Create: `apps/web/src/app/(plugin)/plugin/components/panels/settings-panel.tsx`
- Create: `apps/web/src/app/(plugin)/plugin/components/panels/help-panel.tsx`

- [ ] **Step 1: Create connection panel**

Create `apps/web/src/app/(plugin)/plugin/components/panels/connection-panel.tsx`:

```typescript
"use client";

import { useEffect, useState, useCallback } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Globe, Cable, RefreshCw } from "lucide-react";
import type { PluginConnectionStatus } from "@/types/webview";

export function ConnectionPanel() {
  const [status, setStatus] = useState<PluginConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const requestStatus = useCallback(() => {
    if (typeof window.sendToPlugin === "function") {
      window.sendToPlugin({ type: "getConnectionStatus" });
    } else {
      // Dev fallback: mock data
      setStatus({
        cloud: { connected: true, latency_ms: 42 },
        bridge: { connected: false },
      });
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const handler = (msg: { type: string; payload?: Record<string, unknown> }) => {
      if (msg.type === "connectionStatus" && msg.payload) {
        setStatus(msg.payload as unknown as PluginConnectionStatus);
        setLoading(false);
      }
    };
    window.onPluginMessage = handler;
    requestStatus();

    const interval = setInterval(requestStatus, 5000);
    return () => clearInterval(interval);
  }, [requestStatus]);

  if (loading) {
    return (
      <div className="space-y-3 p-4">
        <Skeleton className="h-16 w-full rounded-xl" />
        <Skeleton className="h-16 w-full rounded-xl" />
      </div>
    );
  }

  const items = [
    {
      label: "Cloud Relay",
      icon: Globe,
      connected: status?.cloud.connected ?? false,
      detail: status?.cloud.latency_ms ? `${status.cloud.latency_ms}ms` : undefined,
    },
    {
      label: "DAW Bridge",
      icon: Cable,
      connected: status?.bridge.connected ?? false,
      detail: status?.bridge.daw
        ? `${status.bridge.daw}${status.bridge.project ? ` — ${status.bridge.project}` : ""}`
        : undefined,
    },
  ];

  return (
    <div className="space-y-2 p-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="flex items-center gap-3 rounded-xl bg-white/[0.02] px-3.5 py-3"
        >
          <item.icon className="h-4 w-4 text-[#555]" />
          <div className="flex-1">
            <div className="text-[12.5px] font-medium text-[#c8c8c8]">
              {item.label}
            </div>
            {item.detail && (
              <div className="text-[10.5px] text-[#444]">{item.detail}</div>
            )}
          </div>
          <div
            className={`h-2 w-2 rounded-full ${
              item.connected
                ? "bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.4)]"
                : "bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]"
            }`}
          />
        </div>
      ))}
      <button
        onClick={requestStatus}
        className="flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-[12px] text-[#444] transition-colors hover:text-[#666]"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        Refresh
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Create presets panel**

Create `apps/web/src/app/(plugin)/plugin/components/panels/presets-panel.tsx`:

```typescript
"use client";

import { useEffect, useState, useCallback } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

interface Preset {
  id: string;
  name: string;
  description: string | null;
  prompt: string;
}

export function PresetsPanel({
  token,
  onSendPrompt,
}: {
  token: string;
  onSendPrompt: (prompt: string) => void;
}) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newPrompt, setNewPrompt] = useState("");
  const [saving, setSaving] = useState(false);

  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const fetchPresets = useCallback(async () => {
    const res = await fetch("/api/plugin/presets", { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) {
      const data = await res.json();
      setPresets(data.presets);
    }
    setLoading(false);
  }, [token]);

  useEffect(() => {
    fetchPresets();
  }, [fetchPresets]);

  const handleCreate = async () => {
    if (!newName.trim() || !newPrompt.trim()) return;
    setSaving(true);
    const res = await fetch("/api/plugin/presets", {
      method: "POST",
      headers,
      body: JSON.stringify({ name: newName, description: newDescription || null, prompt: newPrompt }),
    });
    if (res.ok) {
      const data = await res.json();
      setPresets((prev) => [...prev, data.preset]);
      setShowCreate(false);
      setNewName("");
      setNewDescription("");
      setNewPrompt("");
    }
    setSaving(false);
  };

  if (loading) {
    return (
      <div className="space-y-2 p-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-14 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 p-2.5">
      {presets.map((preset) => (
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
            <Button onClick={handleCreate} disabled={saving || !newName.trim() || !newPrompt.trim()} className="w-full">
              {saving ? "Creating..." : "Create Preset"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
```

- [ ] **Step 3: Create settings panel**

Create `apps/web/src/app/(plugin)/plugin/components/panels/settings-panel.tsx`:

```typescript
"use client";

import { Button } from "@/components/ui/button";
import { LogOut, Key } from "lucide-react";

export function SettingsPanel({
  tokenExpiry,
  onSignOut,
  onRefreshToken,
}: {
  tokenExpiry: Date | null;
  onSignOut: () => void;
  onRefreshToken: () => void;
}) {
  return (
    <div className="flex flex-col gap-2 p-3">
      <div className="rounded-xl bg-white/[0.02] px-3.5 py-3">
        <div className="flex items-center gap-2">
          <Key className="h-4 w-4 text-[#555]" />
          <div className="flex-1">
            <div className="text-[12.5px] font-medium text-[#c8c8c8]">
              Session Token
            </div>
            <div className="text-[10.5px] text-[#444]">
              {tokenExpiry
                ? `Expires ${tokenExpiry.toLocaleDateString()} at ${tokenExpiry.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                : "Active"}
            </div>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefreshToken}
          className="mt-2 w-full text-[11px] text-[#555] hover:text-[#888]"
        >
          Refresh Token
        </Button>
      </div>

      <Button
        variant="ghost"
        onClick={onSignOut}
        className="w-full justify-start gap-2 rounded-xl px-3.5 py-3 text-[12.5px] text-red-400 hover:bg-red-500/5 hover:text-red-300"
      >
        <LogOut className="h-4 w-4" />
        Sign Out
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Create help panel**

Create `apps/web/src/app/(plugin)/plugin/components/panels/help-panel.tsx`:

```typescript
"use client";

import { ExternalLink, RotateCcw } from "lucide-react";

const capabilities = [
  "Set BPM and tempo",
  "Add and rename tracks",
  "Control playback (play, stop, record)",
  "Adjust mixer (volume, pan, mute, solo)",
  "Analyze your mix",
];

const examplePrompts = [
  "Set the BPM to 128",
  "Add a new track called 'Bass'",
  "Show me the project state",
  "Set track 1 volume to 80%",
  "Stop playback",
];

export function HelpPanel({
  onSendPrompt,
  onReplayOnboarding,
}: {
  onSendPrompt: (prompt: string) => void;
  onReplayOnboarding: () => void;
}) {
  const openDocs = () => {
    if (typeof window.sendToPlugin === "function") {
      window.sendToPlugin({ type: "open_browser", url: "https://studioai.dev/docs" });
    } else {
      window.open("https://studioai.dev/docs", "_blank");
    }
  };

  return (
    <div className="flex flex-col gap-4 p-3">
      <div>
        <div className="px-1 text-[11px] font-medium uppercase tracking-wide text-[#444]">
          Capabilities
        </div>
        <div className="mt-2 space-y-1">
          {capabilities.map((cap) => (
            <div
              key={cap}
              className="rounded-lg px-3 py-1.5 text-[12px] text-[#888]"
            >
              {cap}
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="px-1 text-[11px] font-medium uppercase tracking-wide text-[#444]">
          Try These
        </div>
        <div className="mt-2 space-y-1">
          {examplePrompts.map((prompt) => (
            <button
              key={prompt}
              onClick={() => onSendPrompt(prompt)}
              className="w-full rounded-lg px-3 py-1.5 text-left text-[12px] text-[#c8c8c8] transition-colors hover:bg-white/[0.04]"
            >
              &ldquo;{prompt}&rdquo;
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1">
        <button
          onClick={onReplayOnboarding}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-[12px] text-[#555] transition-colors hover:text-[#888]"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Replay Onboarding
        </button>
        <button
          onClick={openDocs}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-[12px] text-[#555] transition-colors hover:text-[#888]"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Documentation
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/components/panels/
git commit -m "feat: add connection, presets, settings, and help panel components"
```

---

## Task 7: Build the onboarding wizard

**Files:**
- Create: `apps/web/src/app/(plugin)/plugin/components/onboarding-wizard.tsx`

- [ ] **Step 1: Create onboarding wizard component**

Create `apps/web/src/app/(plugin)/plugin/components/onboarding-wizard.tsx`:

```typescript
"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { MessageSquare, Zap, Sparkles } from "lucide-react";

const steps = [
  {
    icon: Sparkles,
    title: "Welcome to Studio AI",
    description:
      "Your AI-powered assistant for music production. Control your DAW with natural language — no menus, no shortcuts to memorize.",
  },
  {
    icon: MessageSquare,
    title: "Talk to Your DAW",
    description:
      'Just type what you want. "Set BPM to 128", "Add a bass track", "Analyze my mix". Studio AI translates your words into DAW actions instantly.',
  },
  {
    icon: Zap,
    title: "Save Quick Actions",
    description:
      "Create presets for commands you use often. One click to set up your favorite beat template, apply sidechain compression, or any workflow you repeat.",
  },
];

export function OnboardingWizard({
  open,
  onComplete,
  token,
}: {
  open: boolean;
  onComplete: () => void;
  token: string;
}) {
  const [step, setStep] = useState(0);

  const handleNext = async () => {
    if (step < steps.length - 1) {
      setStep(step + 1);
    } else {
      // Mark onboarding complete
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

  const current = steps[step];

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogContent className="max-w-sm border-white/5 bg-[#0a0a0a] sm:rounded-2xl [&>button]:hidden">
        <DialogHeader className="items-center text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-2xl bg-white/[0.05]">
            <current.icon className="h-6 w-6 text-white" />
          </div>
          <DialogTitle className="text-base">{current.title}</DialogTitle>
          <DialogDescription className="text-[13px] leading-relaxed text-[#888]">
            {current.description}
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between pt-4">
          <div className="flex gap-1.5">
            {steps.map((_, i) => (
              <div
                key={i}
                className={`h-1.5 w-1.5 rounded-full transition-colors ${
                  i === step ? "bg-white" : "bg-white/10"
                }`}
              />
            ))}
          </div>
          <Button
            onClick={handleNext}
            size="sm"
            className="rounded-full px-5"
          >
            {step < steps.length - 1 ? "Next" : "Get Started"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/components/onboarding-wizard.tsx
git commit -m "feat: add onboarding wizard dialog component"
```

---

## Task 8: Build the dashboard shell and wire everything together

**Files:**
- Create: `apps/web/src/app/(plugin)/plugin/plugin-dashboard.tsx`
- Modify: `apps/web/src/app/(plugin)/plugin/page.tsx`

- [ ] **Step 1: Create plugin dashboard shell**

Create `apps/web/src/app/(plugin)/plugin/plugin-dashboard.tsx`:

```typescript
"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { PluginSidebar, type PanelId } from "./components/plugin-sidebar";
import { PluginTopbar } from "./components/plugin-topbar";
import { ChatMessages } from "./components/chat-messages";
import { ChatInput } from "./components/chat-input";
import { ConnectionPanel } from "./components/panels/connection-panel";
import { PresetsPanel } from "./components/panels/presets-panel";
import { SettingsPanel } from "./components/panels/settings-panel";
import { HelpPanel } from "./components/panels/help-panel";
import { OnboardingWizard } from "./components/onboarding-wizard";
import type { PluginConnectionStatus } from "@/types/webview";

export function PluginDashboard({
  token,
  onAuthError,
}: {
  token: string;
  onAuthError: () => void;
}) {
  const [activePanel, setActivePanel] = useState<PanelId>("chat");
  const [input, setInput] = useState("");
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<
    "connected" | "partial" | "disconnected"
  >("disconnected");
  const [bridgeInfo, setBridgeInfo] = useState<{
    daw?: string;
    project?: string;
    connected: boolean;
  }>({ connected: false });

  // Token expiry for settings panel
  const tokenExpiry = useMemo(() => {
    try {
      const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      const payload = JSON.parse(atob(base64));
      return payload.exp ? new Date(payload.exp * 1000) : null;
    } catch {
      return null;
    }
  }, [token]);

  // Chat setup
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: "/api/ai/execute",
        headers: { Authorization: `Bearer ${token}` },
      }),
    [token]
  );

  const { messages, sendMessage, status, error } = useChat({
    transport,
    async onError() {
      try {
        const res = await fetch("/api/auth/plugin/validate", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) onAuthError();
      } catch {
        // Network error — don't force logout
      }
    },
  });

  const isLoading = status === "streaming" || status === "submitted";

  const handleSubmit = useCallback(() => {
    if (!input.trim()) return;
    sendMessage({ text: input });
    setInput("");
  }, [input, sendMessage]);

  const handleSendPrompt = useCallback(
    (prompt: string) => {
      sendMessage({ text: prompt });
      setActivePanel("chat");
    },
    [sendMessage]
  );

  const handleSignOut = useCallback(() => {
    localStorage.removeItem("studio-ai-token");
    onAuthError();
  }, [onAuthError]);

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

  // Listen for connection status from plugin
  useEffect(() => {
    const handler = (msg: { type: string; payload?: Record<string, unknown> }) => {
      if (msg.type === "connectionStatus" && msg.payload) {
        const s = msg.payload as unknown as PluginConnectionStatus;
        setBridgeInfo({
          connected: s.bridge.connected,
          daw: s.bridge.daw,
          project: s.bridge.project,
        });
        if (s.cloud.connected && s.bridge.connected) {
          setConnectionStatus("connected");
        } else if (s.cloud.connected || s.bridge.connected) {
          setConnectionStatus("partial");
        } else {
          setConnectionStatus("disconnected");
        }
      }
    };
    window.onPluginMessage = handler;
  }, []);

  // Render expanded panel content
  const panelContent: Record<PanelId, React.ReactNode> = {
    chat: (
      <div className="p-3">
        <div className="text-[11px] font-medium uppercase tracking-wide text-[#444] px-1">
          Chat History
        </div>
        <div className="mt-2 text-[12px] text-[#333] px-1">
          Coming soon — multiple conversations per workspace.
        </div>
      </div>
    ),
    connection: <ConnectionPanel />,
    presets: <PresetsPanel token={token} onSendPrompt={handleSendPrompt} />,
    settings: (
      <SettingsPanel
        tokenExpiry={tokenExpiry}
        onSignOut={handleSignOut}
        onRefreshToken={() => {
          // Re-authenticate: clear token and show login
          handleSignOut();
        }}
      />
    ),
    help: (
      <HelpPanel
        onSendPrompt={handleSendPrompt}
        onReplayOnboarding={() => setShowOnboarding(true)}
      />
    ),
  };

  return (
    <TooltipProvider delayDuration={0}>
      <SidebarProvider defaultOpen={false}>
        <PluginSidebar
          activePanel={activePanel}
          onPanelChange={setActivePanel}
          onSignOut={handleSignOut}
          connectionStatus={connectionStatus}
        />

        {/* Panel content — shown inside the sidebar when expanded */}
        <div className="group-data-[collapsible=icon]:hidden w-[260px] min-w-[260px] bg-[#080808] overflow-y-auto">
          <div className="border-b border-white/[0.04] px-4 py-3.5">
            <div className="text-[13px] font-semibold text-[#e5e5e5] tracking-tight">
              {activePanel === "chat" && "Chats"}
              {activePanel === "connection" && "Connection"}
              {activePanel === "presets" && "Quick Actions"}
              {activePanel === "settings" && "Settings"}
              {activePanel === "help" && "Help"}
            </div>
          </div>
          {panelContent[activePanel]}
        </div>

        <SidebarInset className="bg-[#111] flex flex-col min-w-0">
          <PluginTopbar
            projectName={bridgeInfo.project}
            dawName={bridgeInfo.daw}
            isConnected={bridgeInfo.connected}
          />
          <ChatMessages
            messages={messages}
            isLoading={isLoading}
            error={error}
          />
          <ChatInput
            value={input}
            onChange={setInput}
            onSubmit={handleSubmit}
            disabled={isLoading}
          />
        </SidebarInset>
      </SidebarProvider>

      <OnboardingWizard
        open={showOnboarding}
        onComplete={() => setShowOnboarding(false)}
        token={token}
      />
    </TooltipProvider>
  );
}
```

- [ ] **Step 2: Update page.tsx to use PluginDashboard**

In `apps/web/src/app/(plugin)/plugin/page.tsx`, change the import and render:

Replace:
```typescript
import { PluginChat } from "./plugin-chat";
```
with:
```typescript
import { PluginDashboard } from "./plugin-dashboard";
```

Replace:
```typescript
  return <PluginChat token={token} onAuthError={clearToken} />;
```
with:
```typescript
  return <PluginDashboard token={token} onAuthError={clearToken} />;
```

- [ ] **Step 3: Verify the app compiles**

```bash
cd apps/web && pnpm build
```

Expected: build succeeds with no type errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/plugin-dashboard.tsx apps/web/src/app/\(plugin\)/plugin/page.tsx
git commit -m "feat: wire up plugin dashboard shell with sidebar, panels, and chat"
```

---

## Task 9: Visual polish and custom sidebar styling

**Files:**
- Modify: `apps/web/src/app/(plugin)/plugin/plugin-dashboard.tsx`
- Modify: `apps/web/src/app/(plugin)/plugin/components/plugin-sidebar.tsx`

After the initial wiring, this task focuses on getting the visual design right per the spec: rounded sidebar edge, no borders, color contrast separation, proper spacing.

- [ ] **Step 1: Add custom sidebar CSS**

The sidebar needs custom styling for the rounded right edge and background colors. In `plugin-sidebar.tsx`, update the `Sidebar` className:

```typescript
<Sidebar
  collapsible="icon"
  variant="sidebar"
  className="border-r-0 bg-[#080808] [--sidebar-width:320px] [--sidebar-width-icon:60px] rounded-r-2xl"
>
```

- [ ] **Step 2: Verify the plugin panel content positioning**

The panel content div in `plugin-dashboard.tsx` should only be visible when the sidebar is expanded. This relies on the sidebar's `group-data-[collapsible=icon]:hidden` pattern. If the panel content is rendering outside the `Sidebar` component, it won't receive the data attribute. In that case, move the panel content inside the `Sidebar` component as a `SidebarContent` section and use the `group-data-[collapsible=icon]:hidden` class.

Test by running `pnpm dev` and navigating to `http://localhost:3000/plugin?context=plugin`. Click sidebar icons and verify:
- Collapsed: only 60px icon rail visible
- Expanded: 320px sidebar with icons + panel content
- Click same icon: collapses back
- Click different icon: switches panel content

- [ ] **Step 3: Adjust the panel content to live inside the Sidebar**

If needed based on Step 2, restructure so the panel content is inside the `Sidebar` component. The sidebar already has `SidebarContent` — add the panel content as a separate `SidebarGroup` with `group-data-[collapsible=icon]:hidden`:

In `plugin-sidebar.tsx`, accept `panelContent` as a prop and render it inside the sidebar:

```typescript
export function PluginSidebar({
  activePanel,
  onPanelChange,
  onSignOut,
  connectionStatus,
  panelContent,
}: {
  activePanel: PanelId;
  onPanelChange: (panel: PanelId) => void;
  onSignOut: () => void;
  connectionStatus: "connected" | "partial" | "disconnected";
  panelContent: React.ReactNode;
}) {
```

Then inside the `<Sidebar>`, after the SidebarMenu with nav items, add:

```typescript
<SidebarGroup className="group-data-[collapsible=icon]:hidden flex-1 overflow-y-auto border-l border-white/[0.04]">
  <div className="px-4 py-3.5 border-b border-white/[0.04]">
    <div className="text-[13px] font-semibold text-[#e5e5e5] tracking-tight">
      {activePanel === "chat" && "Chats"}
      {activePanel === "connection" && "Connection"}
      {activePanel === "presets" && "Quick Actions"}
      {activePanel === "settings" && "Settings"}
      {activePanel === "help" && "Help"}
    </div>
  </div>
  {panelContent}
</SidebarGroup>
```

And remove the standalone panel div from `plugin-dashboard.tsx`.

- [ ] **Step 4: Manual visual QA**

Open `http://localhost:3000/plugin?context=plugin` and check:
1. Dark background (#0a0a0a overall, #080808 sidebar, #111 main)
2. Rounded right edge on sidebar
3. No visible borders between rail and panel
4. Claude-style rounded pill input
5. User avatar at bottom of rail with green dot
6. Tooltip on hover when collapsed
7. Dropdown menu on avatar click with "Sign out"
8. Panel content loads (connection shows mock data, presets loads from API)

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/\(plugin\)/plugin/
git commit -m "feat: polish plugin dashboard visual design — rounded sidebar, colors, spacing"
```

---

## Task 10: Integration testing and final verification

- [ ] **Step 1: Test auth flow**

1. Open `http://localhost:3000/plugin?context=plugin`
2. Should see login screen
3. Click "Sign in with Browser" — should open `/link` in browser
4. Complete auth flow — plugin should receive token and show dashboard

- [ ] **Step 2: Test sidebar navigation**

1. Click each sidebar icon — panel should expand with correct content
2. Click same icon — panel should collapse
3. Click different icon while expanded — panel content should switch
4. Tooltips should show on hover when collapsed

- [ ] **Step 3: Test presets CRUD**

1. Open presets panel
2. Click "Create Custom" — dialog should open
3. Fill in name + prompt, click create — preset should appear in list
4. Click a preset — should send prompt to chat immediately

- [ ] **Step 4: Test onboarding wizard**

1. Clear `user_preferences` row for your user (or use a fresh account)
2. Reload plugin page — wizard should appear
3. Step through all 3 steps — should dismiss and not appear on next reload
4. Open Help panel, click "Replay Onboarding" — wizard should reappear

- [ ] **Step 5: Test settings panel**

1. Open settings — should show token expiry date
2. Click "Sign Out" — should clear token and return to login screen

- [ ] **Step 6: Test connection panel**

1. Open connection panel — should show mock data in dev mode (or real data if plugin is running)
2. Click "Refresh" — should re-query status

- [ ] **Step 7: Verify middleware still works**

1. `http://localhost:3000/plugin` without `?context=plugin` — should redirect to `/`
2. `http://localhost:3000/dashboard?context=plugin` — should redirect to `/plugin?context=plugin`
3. `http://localhost:3000/plugin?context=plugin` — should load dashboard

- [ ] **Step 8: Build check**

```bash
cd apps/web && pnpm build
```

Expected: clean build with no errors.

- [ ] **Step 9: Final commit**

```bash
git add -A
git commit -m "feat: complete plugin dashboard with sidebar, panels, onboarding wizard"
```
