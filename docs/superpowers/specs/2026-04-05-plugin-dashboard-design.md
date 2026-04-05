# Plugin Dashboard Design

**Date:** 2026-04-05
**Status:** Approved

## Overview

Replace the current chat-only plugin view with a professional dashboard shell featuring an icon rail sidebar, expandable panels, and a Claude-style chat input. The plugin WebView (loaded inside FL Studio) becomes a proper workspace — chat-first, with quick access to connection status, presets, settings, and help.

Users navigating from the plugin context (`?context=plugin`) can only access auth pages and this dashboard. No other routes are accessible.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Layout | Icon rail + expandable panel (VS Code pattern) | Best for hierarchical navigation; chat stays visible while panels expand |
| Navigation | Sidebar, not top navbar | Future multi-workspace/multi-chat is hierarchical — sidebar scales, top bar doesn't |
| Architecture | Incremental refactor (Approach 1) | Single WebView, no URL bar — state-driven panels, not route segments |
| Component library | shadcn `Sidebar` with `collapsible="icon"` + custom styling | Standard shadcn collapse for the rail; custom CSS vars for widths and rounded edge |
| Presets storage | Database (`presets` table) | Syncs across devices |
| Preset click behavior | Immediately sends prompt to AI | Fastest path to action |
| Onboarding | Step-by-step wizard on first login | Database flag (`onboarding_completed`) — doesn't repeat on new devices |
| Theme | Dark only for v1 | DAW plugin context — dark is expected |

## Features (v1)

1. **AI Chat** — main view, always rendered. Refactored from existing `plugin-chat.tsx`.
2. **Connection Status** — cloud relay + DAW bridge status, latency, reconnect button.
3. **AI Presets / Quick Actions** — saved prompt templates, click to send immediately. Stored in database.
4. **Settings** — sign out, token info (expiry, manual refresh). Minimal for v1.
5. **Help & Onboarding** — wizard on first login (database-flagged). Help panel as ongoing reference: capabilities list, example prompts (clickable, send to chat), link to docs/support.

**Deferred to future versions:**
- Project info panel, mixer controls, chat history, account/subscription
- Workspace/project switcher in sidebar (multi-workspace)
- Theme toggle, AI model selection
- Multiple chats per workspace

## Layout

### Collapsed State (default)

```
+--------------------------------------------------+
| [Rail 60px]  |          Main Chat Area            |
|              |                                    |
|   [Logo]     |  [TopBar: "New Chat"  FL Studio..] |
|              |                                    |
|   [Chat*]    |  AI: Welcome to Studio AI...       |
|   [Status]   |                                    |
|   [Presets]  |  You: Set BPM to 128...            |
|              |                                    |
|              |  AI: Done. check set_bpm -> 128    |
|              |                                    |
|   [Help]     |                                    |
|   [Settings] |  +-----------------------------+   |
|              |  | Ask Studio AI anything.. [>] |   |
|   [Avatar]   |  +-----------------------------+   |
+--------------------------------------------------+
```

- Rail: 60px, dark background (#080808), rounded right edge (16px radius)
- Active item: white left accent bar + subtle background highlight
- User avatar: circular, at bottom of rail with green online dot
- Connection status: small green dot at bottom of rail (quick glance)

### Expanded State (panel open)

```
+-----------------------------------------------------------+
| [Rail] | [Panel 260px]         |      Main Chat Area       |
|        |                       |                           |
| [Logo] | Quick Actions         |  [TopBar]                 |
|        | One-click AI commands |                           |
| [Chat] |                       |  Chat messages...         |
| [Stat] | +--Lo-fi Beat Setup-+ |                           |
| [Pres*]| +-------------------+ |                           |
|        | +--Sidechain Comp---+ |                           |
|        | +-------------------+ |                           |
| [Help] | +--Analyze My Mix---+ |                           |
| [Sett] | +-------------------+ |  +-------------------+   |
|        | + Create Custom       |  | Ask Studio AI.. [>]|   |
| [Avtr] |                       |  +-------------------+   |
+-----------------------------------------------------------+
```

- Panel: 260px, same dark background as rail (no border between them)
- Rounded right edge on expanded sidebar (16px radius) — creates visual float effect
- Chat area shrinks to accommodate; click same icon again to collapse

## Visual Design

- **Aesthetic:** Professional, minimal, elegant. No harsh borders — background color contrast only.
- **Colors:** #080808 (rail/panel), #111 (main area), #0a0a0a (frame). Monochrome with white accents.
- **Input:** Rounded pill (24px radius), Claude-style with circular white send button. Subtle border on hover.
- **Messages:** 18px rounded bubbles. Assistant: rgba white 4% bg. User: rgba white 8% bg.
- **Tool results:** Green-tinted card with monospace font, checkmark icons.
- **Icons:** Lucide (feather-style), 20px, 1.8 stroke. Muted (#444) default, white when active.
- **Typography:** SF Pro / Inter / system-ui. -0.2px letter spacing. 13px base.
- **User avatar:** Circular with gradient, green status dot with rail-color border.
- **Dark mode:** Force `dark` class on `<html>` in the plugin layout (`(plugin)/layout.tsx`).
- **Loading states:** Use `Skeleton` components in presets panel (database fetch) and connection panel (IPC query).

## Technical Architecture

### shadcn Components

**Already installed:** `avatar`, `button`, `card`, `dialog`, `dropdown-menu`, `input`, `badge`, `separator`, `sheet`, `switch`, `label`

**Need to install:** `sidebar`, `tooltip`, `popover`, `scroll-area`, `skeleton`, `collapsible`

### Sidebar Behavior

The shadcn `Sidebar` with `collapsible="icon"` toggles between icon-only and expanded states. This matches our design:

- Use `collapsible="icon"` and `variant="sidebar"` (not `floating` — avoids conflicting padding/radius)
- **Collapsed** = icon-only sidebar (the rail, ~60px via `--sidebar-width-icon`)
- **Expanded** = full sidebar with icons + panel content (~320px via `--sidebar-width`)
- Custom CSS overrides: `--sidebar-width: 320px`, `--sidebar-width-icon: 60px`. Apply 16px `border-radius` to the right edge via Tailwind classes on the `Sidebar` component.
- Panel content uses `group-data-[collapsible=icon]:hidden` to hide when collapsed — only icons remain visible.
- Clicking a sidebar icon toggles the sidebar open (via `SidebarTrigger` or `useSidebar().toggleSidebar()`). The expanded panel shows content based on which icon was clicked (tracked via local state: `activePanel`).

### Component Tree (shadcn mapping)

```
SidebarProvider (defaultOpen={false})
+-- Sidebar (collapsible="icon", variant="sidebar", side="left")
|   +-- SidebarHeader -> Logo
|   +-- SidebarContent
|   |   +-- SidebarGroup
|   |       +-- SidebarMenu
|   |           +-- SidebarMenuItem -> Chat (Tooltip wrapped)
|   |           +-- SidebarMenuItem -> Connection (Tooltip wrapped)
|   |           +-- SidebarMenuItem -> Presets (Tooltip wrapped)
|   +-- SidebarFooter
|   |   +-- SidebarMenuItem -> Help (Tooltip wrapped)
|   |   +-- SidebarMenuItem -> Settings (Tooltip wrapped)
|   |   +-- DropdownMenu -> User avatar + sign out
|   +-- SidebarRail
+-- SidebarInset
    +-- TopBar (Button, Badge)
    +-- ChatMessages (ScrollArea)
    +-- ChatInput (Input, Button - custom rounded pill)
```

### File Structure

```
apps/web/src/app/(plugin)/plugin/
  page.tsx                    # Auth orchestrator - swap PluginChat for PluginDashboard
  plugin-dashboard.tsx        # NEW - SidebarProvider shell
  plugin-login.tsx            # Existing - unchanged
  plugin-chat.tsx             # Existing - refactored, chat logic extracted
  components/
    plugin-sidebar.tsx        # Sidebar + rail + menu items + user avatar
    plugin-topbar.tsx         # Top bar: chat title, project info, new chat btn
    chat-input.tsx            # Rounded pill input (Claude-style)
    chat-messages.tsx         # Message list with ScrollArea
    panels/
      connection-panel.tsx    # Cloud relay + DAW bridge status
      presets-panel.tsx       # Preset list + create custom
      settings-panel.tsx      # Sign out, token info
      help-panel.tsx          # Capabilities, examples, docs link
    onboarding-wizard.tsx     # Dialog-based step-by-step wizard
```

### State Management

- `activePanel` state lives in `plugin-dashboard.tsx` and is passed to the sidebar and panel components
- `sendMessage` from `useChat` is lifted to the dashboard level and passed as a callback to `presets-panel.tsx` and `help-panel.tsx` (for clickable example prompts)
- Connection status is queried via `window.sendToPlugin` IPC — see Connection Panel IPC section below

### Changes to Existing Files

- **`page.tsx`**: Replace `<PluginChat token={token} onAuthError={clearToken} />` with `<PluginDashboard token={token} onAuthError={clearToken} />`
- **`(plugin)/layout.tsx`**: Add `className="dark"` to force dark mode in plugin context. Update flex direction if needed for `SidebarProvider`.
- **`plugin-chat.tsx`**: Extract message rendering and chat input into `chat-messages.tsx` and `chat-input.tsx`. Keep `useChat` hook logic in `plugin-dashboard.tsx`.

### API Routes

All plugin API routes require JWT Bearer token auth (validated via `verifyPluginToken` from `lib/plugin-auth.ts`).

**Presets CRUD:**

| Method | Route | Body | Response |
|--------|-------|------|----------|
| GET | `/api/plugin/presets` | — | `{ presets: Preset[] }` |
| POST | `/api/plugin/presets` | `{ name, description?, prompt }` | `{ preset: Preset }` |
| PUT | `/api/plugin/presets/[id]` | `{ name?, description?, prompt? }` | `{ preset: Preset }` |
| DELETE | `/api/plugin/presets/[id]` | — | `{ success: true }` |

**User Preferences:**

| Method | Route | Body | Response |
|--------|-------|------|----------|
| GET | `/api/plugin/preferences` | — | `{ preferences: UserPreferences }` |
| PATCH | `/api/plugin/preferences` | `{ onboarding_completed?: boolean }` | `{ preferences: UserPreferences }` |

**File locations:**
```
apps/web/src/app/api/plugin/
  presets/
    route.ts              # GET, POST
    [id]/
      route.ts            # PUT, DELETE
  preferences/
    route.ts              # GET, PATCH
```

### Connection Panel IPC

The plugin WebView communicates with the Rust plugin via `window.sendToPlugin` / `window.onPluginMessage` (defined in `src/types/webview.d.ts`).

**New IPC message types:**

```typescript
// Request (WebView -> Plugin)
{ type: "getConnectionStatus" }

// Response (Plugin -> WebView)
{
  type: "connectionStatus",
  payload: {
    cloud: { connected: boolean, latency_ms?: number },
    bridge: { connected: boolean, daw?: string, project?: string }
  }
}
```

- Poll every 5 seconds while connection panel is visible
- When panel is hidden, show summary dot on rail (green = all connected, yellow = partial, red = disconnected)
- **Fallback (browser dev mode):** When `window.sendToPlugin` is undefined, show "Running outside plugin — connection status unavailable" with mock data option for development

### Database Changes

**Migration: `007_presets.sql`**
```sql
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

**Migration: `008_user_preferences.sql`**
```sql
CREATE TABLE public.user_preferences (
  user_id TEXT PRIMARY KEY,
  onboarding_completed BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
COMMENT ON COLUMN public.user_preferences.user_id IS 'References next_auth.users.id — no FK because NextAuth manages user lifecycle externally';
```

Note: `user_id TEXT` without FK is consistent with existing tables (`plugin_tokens`, `devices`, `projects`). User IDs come from NextAuth which manages its own schema in `next_auth.*`. The comment documents this decision.

### Onboarding Wizard

- Renders as a `Dialog` overlay on first login (when `onboarding_completed = false`)
- Fetched via `GET /api/plugin/preferences` on dashboard mount
- 3-4 steps: Welcome -> What Studio AI can do -> Try an example command -> Done
- On completion: `PATCH /api/plugin/preferences` with `{ onboarding_completed: true }`
- Can be re-triggered from Help panel ("Replay onboarding")

### Auth & Middleware

No changes to existing auth flow or middleware. The dashboard lives at the same `/plugin` route, behind the same `?context=plugin` gate. Token validation, periodic re-validation, and the device auth flow remain unchanged.

The only layout change is adding `className="dark"` to the plugin layout to force dark mode.
