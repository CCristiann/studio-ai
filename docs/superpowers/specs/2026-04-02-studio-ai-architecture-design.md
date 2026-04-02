# Studio AI — Architecture Design Document

**Date:** April 2, 2026
**Status:** Revised (v1.1)
**Authors:** Cristian Cirje
**Version:** 1.1

---

## 1. Introduction

Studio AI is an AI-powered agent that enables musicians to organize and control their Digital Audio Workstation (DAW) projects through natural language. Rather than navigating complex menus and parameter panels, users interact with a conversational interface embedded directly inside their DAW as a VST3 plugin. The agent interprets intent, translates it into concrete DAW operations, and executes them in real time.

The initial release targets FL Studio, with Ableton Live support planned as the second integration. Both DAWs will be served by the same plugin binary — the architecture is designed from the ground up to be DAW-agnostic at the plugin layer.

This document defines the system architecture for Phase 1 of Studio AI. Phase 1 is explicitly scoped to the foundational infrastructure: SaaS structure, authentication, subscription billing, the full plugin-to-cloud communication pipeline, and the AI execution layer. Higher-level features such as intelligent project organization, template engines, and MIDI generation are deferred to subsequent phases. The purpose of this document is to establish a single authoritative reference for every architectural decision, component boundary, data flow, and technology choice so that implementation can proceed without ambiguity.

---

## 2. System Overview

Studio AI is composed of five principal subsystems deployed across two environments:

| Subsystem | Environment | Technology | Responsibility |
|-----------|-------------|------------|----------------|
| Web Application | Cloud (Vercel) | Next.js 16.x, TypeScript | Marketing site, dashboard, plugin UI, AI processing, auth, billing |
| Relay Service | Cloud (Railway / Fly.io) | FastAPI (Python) | WebSocket connection registry, message relay, Stripe webhooks |
| VST3 Plugin | User machine | Rust (nih-plug, nih-plug-webview) | Embedded WebView, dual WebSocket client, WebView-to-Rust IPC |
| DAW Bridge | User machine | Python | Local WebSocket server exposing DAW-specific API over a uniform protocol |
| Database | Cloud (Supabase) | PostgreSQL | Users, sessions, subscriptions, devices, projects |

Supporting infrastructure includes Redis for connection state and pub/sub messaging, and Stripe for subscription billing.

### 2.1 System Topology

```
CLOUD (Vercel + Railway/Fly.io)
├── Next.js (Vercel)
│   ├── (marketing)/  — Landing page, pricing, installer download
│   ├── (dashboard)/  — Account management, billing, settings
│   ├── (plugin)/     — Chatbot UI, project views (plugin WebView mode)
│   └── api/          — Route handlers, AI endpoints (Vercel AI SDK), auth
│       └── HTTP POST /api/relay/{user_id} → FastAPI
│
└── FastAPI (Railway/Fly.io)
    ├── WS  /ws                    — Plugin WebSocket connections (JWT-validated)
    ├── POST /relay/{user_id}      — Receives actions from Next.js, relays to plugin
    ├── POST /stripe/webhook       — Stripe event handler → Supabase
    └── Redis
        ├── Connection registry    — SET plugin:online:{user_id} (TTL 90s, heartbeat 30s)
        └── PubSub relay:{user_id} — Cross-instance message relay

USER MACHINE
├── VST3 Plugin (Rust)
│   ├── WebView         — Loads Next.js app in plugin mode
│   ├── WebView IPC     — Passes JWT to Rust on login
│   ├── Thread A (Tokio) — WSS client → FastAPI cloud
│   └── Thread B (Tokio) — WS client  → localhost:57120
│
└── DAW Bridge Script (Python)
    └── WS server on localhost:57120
        ├── FL Studio: MIDI Script (runs in FL Python environment)
        └── Ableton: Remote Script (runs in Ableton Python environment)

Supabase (PostgreSQL): users, subscriptions, devices, projects
```

---

## 3. Technology Stack

### 3.1 Frontend and Web Application

| Component | Technology | Version |
|-----------|------------|---------|
| Framework | Next.js | 16.x (latest) |
| Language | TypeScript | Latest stable |
| AI SDK | Vercel AI SDK | 5.x (latest) |
| Authentication | NextAuth v5 (Auth.js) | 5.x with Supabase adapter |
| Payments | Stripe | Latest API |
| UI Library | shadcn/ui | Latest |
| Styling | Tailwind CSS | Latest |

### 3.2 Relay Service (Backend)

| Component | Technology | Notes |
|-----------|------------|-------|
| Framework | FastAPI (Python) | WebSocket relay only — no AI processing |
| State Store | Redis | Connection registry + pub/sub |
| Deployment | Railway or Fly.io | Horizontally scalable |

### 3.3 VST3 Plugin

| Component | Technology | Notes |
|-----------|------------|-------|
| Language | Rust | Memory-safe, cross-platform |
| Plugin Framework | nih-plug + nih-plug-webview | VST3 format with embedded WebView |
| Async Runtime | Tokio | Powers both WebSocket client threads |
| WebSocket Client | tokio-tungstenite | Async WebSocket connections |

### 3.4 DAW Bridge

| Component | Technology | Notes |
|-----------|------------|-------|
| Language | Python | Runs inside DAW's embedded Python environment |
| Protocol | WebSocket server on localhost:57120 | Uniform interface for all DAWs |
| FL Studio | MIDI Script | Uses FL Studio's Python API |
| Ableton | Remote Script | Uses Ableton Live's Python API |

### 3.5 Database and Infrastructure

| Component | Technology | Notes |
|-----------|------------|-------|
| Database | Supabase (PostgreSQL) | Managed PostgreSQL with auth adapter support |
| Cache / PubSub | Redis | Connection registry with TTL, cross-instance pub/sub |
| Payments | Stripe | Subscription billing with webhook integration |

---

## 4. Key Decisions and Rationale

This section documents the principal architectural decisions and the reasoning behind each.

### 4.1 Next.js as the AI Brain, FastAPI as Pure Relay

**Decision:** All AI processing (model calls, tool orchestration, streaming) lives in the Next.js application via the Vercel AI SDK. FastAPI handles only WebSocket connection management and message relay.

**Rationale:** The Vercel AI SDK provides first-class support for tool calling, streaming responses, and agentic loops — capabilities that would need to be reimplemented from scratch in Python. Consolidating AI logic in a single layer eliminates the complexity of coordinating AI state across two services. FastAPI's role is deliberately narrow: accept WebSocket connections from plugins, maintain a connection registry, and forward messages. This separation means FastAPI can be scaled horizontally without any concern for AI model state, and the AI layer benefits from Vercel's edge network and serverless scaling.

### 4.2 Local WebSocket on localhost:57120 (Replacing Unix Pipes)

**Decision:** Communication between the VST3 plugin and the DAW bridge uses a WebSocket connection on `localhost:57120`, replacing the previous architecture's Unix pipe approach (`fd 20/21`).

**Rationale:** Unix pipes are not portable to Windows. WebSockets provide a cross-platform, bidirectional, message-framed transport that works identically on macOS and Windows. The localhost connection carries zero network latency overhead while providing a clean, debuggable protocol boundary between the plugin and bridge. Port 57120 is in the IANA ephemeral range (49152–65535). Note: 57120 is also the default port for SuperCollider (scsynth); if conflict is detected during installation, the port is configurable via an installer-set environment variable read by both the bridge script and the plugin.

**Local bridge authentication:** The bridge script generates a random 32-byte secret token on first launch and writes it to a platform-specific config directory (macOS: `~/.config/studio-ai/bridge.token`, Windows: `%APPDATA%\studio-ai\bridge.token`). The VST3 plugin reads this file at startup and includes the token in the first message after connecting (`{ type: "auth", payload: { token: "..." } }`). The bridge rejects connections that fail this handshake. This protects against other local processes sending arbitrary DAW commands. **Phase 1 assumes a single user per machine.** Multi-user and multi-instance scenarios are deferred.

### 4.3 Auth via WebView Storage, No OS Keychain

**Decision:** Authentication state (JWT, refresh tokens) is stored in the WebView's localStorage/IndexedDB. The JWT is passed to the Rust plugin layer via WebView IPC (`window.__bridge__.sendToken(jwt)`). The system does not use the operating system's keychain or credential store.

**Rationale:** OS keychain access from a VST3 plugin context is unreliable across platforms and DAW hosts. Some DAW sandboxing environments restrict keychain access entirely. By keeping auth state in the WebView — which is a standard browser context — the authentication flow is identical to a web application. The JWT is passed to Rust only as an opaque token for WebSocket authentication. This eliminates an entire category of cross-platform credential management bugs at the cost of re-authentication if WebView storage is cleared, which is an acceptable trade-off.

### 4.4 Single VST3 Binary, DAW-Agnostic Plugin

**Decision:** The Rust VST3 plugin is a single compiled binary that works in both FL Studio and Ableton Live. It contains no DAW-specific code. DAW-specific behavior is handled entirely by the bridge scripts.

**Rationale:** The plugin's responsibilities are limited to three things: host a WebView, maintain a WebSocket connection to the cloud, and maintain a WebSocket connection to `localhost:57120`. None of these responsibilities require knowledge of which DAW is hosting the plugin. DAW-specific API calls are the exclusive domain of the bridge scripts, which run inside each DAW's own Python environment. This means adding support for a new DAW requires only a new bridge script — no plugin recompilation, no binary variants, no distribution complexity.

### 4.5 Redis from Day One

**Decision:** Redis is deployed as part of the initial infrastructure, used for the WebSocket connection registry (with TTL) and pub/sub for cross-instance message relay.

**Rationale:** FastAPI instances hold WebSocket connections in-process memory. Without a shared state layer, horizontally scaling FastAPI is impossible — a relay request from Next.js could arrive at an instance that does not hold the target user's connection. Redis solves this immediately: every instance publishes relay messages to a Redis channel, and the instance holding the connection delivers it. Deploying Redis from the start avoids a painful mid-development refactor when scaling becomes necessary. The operational overhead of a managed Redis instance is minimal.

### 4.6 Hybrid AI Execution Strategy

**Decision:** The AI layer uses two execution modes depending on command complexity. Simple commands (e.g., "set BPM to 120") use direct tool calling with `stopWhen: stepCountIs(1)`. Complex operations (e.g., "analyze this project and reorganize it") use an agentic loop with `stopWhen: stepCountIs(N)` where N is bounded.

**Rationale:** Direct tool calling is faster and cheaper for atomic operations — one model call, one tool invocation, one result. Agentic loops are necessary for multi-step operations where the AI must observe intermediate state (e.g., read the current project structure, decide on changes, execute them, verify the result). Bounding the step count prevents runaway loops and controls cost. The Vercel AI SDK's `streamText` with `stopWhen` provides both modes through the same API surface.

**API note:** `stopWhen: stepCountIs(N)` is the correct API in Vercel AI SDK 5.x, where `stepCountIs` is a named export from the `ai` package. This replaced the `maxSteps` parameter from SDK 4.x.

### 4.7 Plugin Mode Detection via Query Parameter

**Decision:** The Next.js application detects whether it is running in a browser or inside the plugin WebView by checking for a `?context=plugin` query parameter (or custom header). Middleware routes requests to the appropriate layout and feature set.

**Rationale:** The same Next.js application serves both the public web experience and the in-plugin interface. Rather than deploying two separate frontends, a single deployment with context-aware routing reduces operational complexity. The plugin WebView always loads a URL with the context parameter, which middleware intercepts to apply the plugin-specific layout (no marketing chrome, no navigation bar, chatbot-first interface). This is a standard pattern for embedded WebView applications.

---

## 5. Authentication and Authorization

### 5.1 Browser Authentication Flow

1. User navigates to the Studio AI web application.
2. NextAuth v5 handles login (OAuth providers or email/password via Supabase adapter).
3. Session JWT and refresh token are stored in httpOnly cookies.
4. User has access to the dashboard, billing management, and installer downloads.

### 5.2 Plugin WebView Authentication Flow

1. The VST3 plugin loads. The embedded WebView opens the Next.js application with `?context=plugin`.
2. The user logs in through the same NextAuth flow rendered inside the WebView.
3. The JWT is stored in WebView localStorage/IndexedDB.
4. WebView IPC call: `window.__bridge__.sendToken(jwt)` passes the token to the Rust layer.
5. Rust Thread A opens a WSS connection to FastAPI with the JWT in the `Authorization` header. Note: this is a native Rust connection via `tokio-tungstenite`, not a browser WebSocket. Custom headers are fully supported. No browser ever connects directly to FastAPI.
6. FastAPI validates the JWT against the NextAuth public key and checks `subscription_status` in Supabase.
7. If valid and subscription is active, the connection is accepted. The plugin transitions to ONLINE status.

### 5.3 JWT Refresh

- NextAuth automatically refreshes the JWT within the WebView session.
- On refresh, the WebView IPC notifies the Rust layer of the new token.
- Rust updates the WSS connection (reconnects if necessary with the fresh JWT).

### 5.4 Stripe Subscription Flow

- Stripe sends webhook events to `POST /stripe/webhook` on FastAPI.
- FastAPI updates the `subscriptions` table in Supabase accordingly.
- Every new plugin WebSocket connection triggers a subscription status check.
- If the subscription is expired or past due, FastAPI rejects the connection with a specific WebSocket close code.
- The WebView receives the close code and renders the appropriate paywall or renewal UI.

---

## 6. Connection and IPC Architecture

### 6.1 Message Envelope

All communication across every connection in the system uses a uniform message envelope:

```json
{
  "id": "uuid-v4",
  "type": "action | response | heartbeat | error | state",
  "payload": { }
}
```

- **action**: A command to be executed (e.g., set BPM, add track).
- **response**: The result of an executed action.
- **heartbeat**: Keep-alive signal (plugin sends every 30 seconds).
- **error**: Error report with code and message.
- **state**: DAW state snapshot or delta.

### 6.2 Plugin Startup Sequence

1. **WebView loads.** User authenticates. JWT is passed to Rust via WebView IPC.
2. **Thread A (Cloud):** Rust opens a WSS connection to FastAPI with the JWT in the header. FastAPI registers the connection in its local dictionary and writes to Redis (`SET plugin:online:{user_id} = instance_id`, TTL 90s).
3. **Thread B (Local):** Rust opens a WS connection to `localhost:57120`. On success, the bridge sends the initial DAW state snapshot.
4. **Plugin status transitions:** `OFFLINE` -> `CONNECTING` -> `CLOUD_CONNECTED` -> `FULLY_CONNECTED`.

### 6.3 Command Execution (Full Flow)

```
User types prompt in WebView
  → WebView fetch POST /api/ai/execute { prompt }
  → Next.js Route Handler (Vercel AI SDK streamText + tools)
  → AI model generates action via tool calling
  → Tool execute() function: HTTP POST /relay/{user_id} to FastAPI
      { id: uuid, action: {...} }
  → FastAPI stores asyncio.Future in pending dict keyed by message id
  → FastAPI looks up WebSocket in local dict
      (or publishes to Redis pub/sub if connection is on a different instance)
  → FastAPI sends JSON to plugin via WebSocket: { id, type: "action", payload: {...} }
  → Plugin Thread A receives → mpsc channel → Thread B
  → Thread B sends JSON to localhost:57120
  → Bridge executes DAW API call (timeout: 4s)
  → Bridge sends response: { id, type: "response", success: bool, data: {...} }
  → Thread B → mpsc → Thread A → FastAPI WebSocket receive loop
  → FastAPI resolves asyncio.Future keyed by id
  → HTTP POST returns result to Next.js tool execute() (overall timeout: 5s)
  → Tool returns result to Vercel AI SDK
  → AI SDK streams response text to WebView
```

**Return path detail:** FastAPI holds the incoming HTTP POST open (non-blocking async) while awaiting the plugin's WebSocket response. A `pending: dict[str, asyncio.Future]` dict correlates requests by message `id`. This eliminates the need for callbacks, polling, or a second connection from Next.js to FastAPI.

**Timeout and error contract:**

| Timeout | Duration | Behavior |
|---------|----------|----------|
| DAW call (bridge) | 4s | Bridge sends `{ type: "error", code: "DAW_TIMEOUT" }` |
| Full relay round-trip | 5s | FastAPI cancels Future, returns HTTP 504 to Next.js tool |
| Plugin offline | immediate | FastAPI returns HTTP 503 `{ code: "PLUGIN_OFFLINE" }` |

**Error codes returned to Next.js tool:**

| Code | Meaning |
|------|---------|
| `PLUGIN_OFFLINE` | No active WebSocket for this user_id |
| `BRIDGE_DISCONNECTED` | Plugin connected but bridge not reachable |
| `DAW_TIMEOUT` | DAW API call exceeded 4s |
| `DAW_ERROR` | DAW API returned an error (e.g., invalid parameter) |
| `RELAY_TIMEOUT` | Full round-trip exceeded 5s |

### 6.4 Reconnection Strategy

| Connection | Strategy | Details |
|------------|----------|---------|
| Thread A (Cloud WSS) | Exponential backoff | 1s, 2s, 4s, 8s, ... max 60s between attempts |
| Thread B (Local WS) | Fixed interval | Retry every 2s; the bridge may start after the plugin |
| JWT expired | IPC notification | WebView notified → refresh token → new JWT → retry connection |

### 6.5 FastAPI Connection Manager

The connection manager maintains two layers of state:

- **Local dictionary:** Maps `user_id` to the active WebSocket object on this FastAPI instance. Used for direct message delivery.
- **Redis connection registry:** `SET plugin:online:{user_id} = instance_id` with a 90-second TTL. Renewed by heartbeat messages every 30 seconds.
- **Redis pub/sub:** Channel `relay:{user_id}`. When a relay request arrives at an instance that does not hold the target connection, it publishes the message to this channel. The instance holding the connection subscribes and delivers it.

---

## 7. AI Processing Layer

All AI processing is handled by the Vercel AI SDK within Next.js route handlers. FastAPI has no AI responsibilities.

### 7.1 Simple Commands (Direct Tool Calling)

For atomic operations that require a single DAW action:

```typescript
// POST /api/ai/execute
streamText({
  model,
  messages,
  tools: {
    set_bpm,
    add_track,
    get_state,
    // ...
  },
  stopWhen: stepCountIs(1)
})
```

The model calls one tool, the tool executes, and the result streams back to the user.

### 7.2 Complex Operations (Agentic Loop)

For multi-step operations that require observation and iteration:

```typescript
// POST /api/ai/execute
streamText({
  model,
  messages,
  tools: {
    get_project_state,
    analyze_project,
    execute_actions,
    // ...
  },
  stopWhen: stepCountIs(10)
})
```

The model may call `get_project_state` to observe, decide on a plan, call `execute_actions` to apply changes, then call `get_project_state` again to verify. The step count bound prevents runaway loops.

### 7.3 DAW Relay Tools

Tools that interact with the DAW execute an HTTP POST to FastAPI's relay endpoint:

```typescript
// Inside a tool's execute function
const response = await fetch(`${FASTAPI_URL}/relay/${userId}`, {
  method: 'POST',
  body: JSON.stringify({ actions: [...] })
})
```

This is the only point where the Next.js AI layer communicates with FastAPI.

---

## 8. Database Schema

### 8.1 NextAuth Tables (next_auth schema)

Managed by the NextAuth Supabase adapter:

- `next_auth.users` — User accounts
- `next_auth.accounts` — OAuth provider links
- `next_auth.sessions` — Active sessions
- `next_auth.verification_tokens` — Email verification tokens

### 8.2 Application Tables (public schema)

```sql
CREATE TABLE subscriptions (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                UUID NOT NULL REFERENCES next_auth.users(id),
  stripe_customer_id     TEXT UNIQUE,
  stripe_subscription_id TEXT UNIQUE,
  plan                   TEXT NOT NULL DEFAULT 'free',    -- 'free' | 'pro' | 'studio'
  status                 TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'canceled' | 'past_due'
  current_period_end     TIMESTAMPTZ,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE devices (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES next_auth.users(id),
  device_name  TEXT,
  device_token TEXT UNIQUE,
  platform     TEXT NOT NULL,  -- 'macos' | 'windows'
  daw          TEXT NOT NULL,  -- 'fl_studio' | 'ableton'
  last_seen    TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES next_auth.users(id),
  name       TEXT NOT NULL,
  daw        TEXT NOT NULL,    -- 'fl_studio' | 'ableton'
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 9. Monorepo Structure

The project is organized as a Turborepo monorepo with pnpm workspaces:

```
studio-ai/
├── apps/
│   ├── web/                        # Next.js application (deployed to Vercel)
│   │   └── src/
│   │       ├── app/
│   │       │   ├── (marketing)/    # Landing page, pricing, installer download
│   │       │   ├── (dashboard)/    # Account management, billing, settings
│   │       │   ├── (plugin)/       # Chatbot interface, project views (plugin WebView mode)
│   │       │   └── api/            # Route handlers: auth, AI endpoints, relay proxy
│   │       ├── components/         # Shared UI components (shadcn/ui)
│   │       ├── lib/                # Core libraries: auth.ts, stripe.ts, supabase.ts
│   │       └── middleware.ts       # Context detection (browser vs. plugin WebView)
│   │
│   └── api/                        # FastAPI relay service (deployed to Railway/Fly.io)
│       ├── routers/                # websocket.py, relay.py, stripe_webhooks.py
│       ├── services/               # connection_manager.py, redis_client.py
│       ├── middleware/             # jwt_validation.py
│       └── main.py                 # Application entry point
│
├── packages/
│   ├── types/                      # Shared TypeScript types (actions, messages, envelopes)
│   └── db/                         # Supabase schema SQL files and migrations
│
├── plugin/                         # Rust VST3 plugin
│   └── src/
│       ├── lib.rs                  # VST3 entry point, plugin lifecycle
│       ├── websocket_cloud.rs      # Thread A — WSS client to FastAPI
│       ├── websocket_bridge.rs     # Thread B — WS client to localhost:57120
│       └── ipc.rs                  # WebView <-> Rust IPC (sendToken, receiveMessage, etc.)
│
├── bridge/                         # Python DAW bridge scripts
│   ├── core/                       # Shared: WS server, message handler, action router
│   ├── fl-studio/                  # FL Studio MIDI Script adapter
│   │   └── device_studio_ai.py    # Implements FL Studio API calls
│   └── ableton/                    # Ableton Remote Script adapter
│       └── StudioAI/              # Implements Ableton Live API calls
│
├── installer/                      # Platform-specific installers
│   ├── macos/                      # .pkg installer
│   └── windows/                    # .exe installer
│
├── turbo.json                      # Turborepo pipeline configuration
├── pnpm-workspace.yaml             # pnpm workspace definition
└── package.json                    # Root package.json
```

---

## 10. Design Principles

The following principles govern all architectural and implementation decisions:

1. **The plugin is DAW-agnostic.** The Rust VST3 binary knows only two endpoints: the FastAPI WSS URL and `localhost:57120`. It contains zero lines of FL Studio or Ableton-specific code. Adding a new DAW requires only a new bridge script.

2. **FastAPI does exactly one thing.** It manages WebSocket connections and relays messages. It performs no AI inference, no business logic beyond subscription validation, and no data transformation. This constraint keeps it simple, fast, and horizontally scalable.

3. **All AI lives in Next.js.** The Vercel AI SDK is the single AI processing layer. There is one place to configure models, define tools, manage prompts, and observe AI behavior. No AI logic is distributed across services.

4. **Bridge scripts are thin adapters.** Each bridge script receives an action JSON envelope, calls the corresponding DAW API method, and returns the result. Bridge scripts contain no business logic, no AI, and no state beyond what the DAW provides.

5. **Redis is deployed from day one.** The connection registry and pub/sub infrastructure are part of the initial deployment, not a future optimization. This eliminates the risk of a disruptive refactor when horizontal scaling becomes necessary.

6. **No OS keychain dependency.** Authentication state lives entirely in the WebView's standard web storage. This avoids cross-platform credential management complexity and DAW sandboxing conflicts at the cost of re-authentication if WebView storage is cleared.

---

## 11. Phase 1 Scope

### 11.1 In Scope

The following deliverables constitute Phase 1:

- **SaaS web application:** Next.js deployment with marketing pages, user dashboard, and plugin WebView mode. Full authentication flow via NextAuth v5 with Supabase adapter.
- **Subscription billing:** Stripe integration with webhook processing, plan management (free/pro/studio tiers), and subscription-gated plugin access.
- **FastAPI relay service:** WebSocket endpoint for plugin connections, HTTP relay endpoint for Next.js, Redis-backed connection registry with TTL and heartbeat, Stripe webhook handler.
- **VST3 plugin (Rust):** Compiled binary with embedded WebView, dual WebSocket client threads (cloud + local), WebView IPC for JWT transfer, connection state management with reconnection logic.
- **FL Studio bridge script:** Python MIDI Script implementing the WebSocket server on `localhost:57120`, action routing for core FL Studio API operations.
- **AI execution layer:** Vercel AI SDK integration with tool definitions for basic DAW operations, support for both direct tool calling and bounded agentic loops.
- **Database schema:** Supabase tables for subscriptions, devices, and projects. NextAuth adapter tables.
- **Installer:** macOS `.pkg` installer for the VST3 plugin and FL Studio bridge script.

### 11.2 Out of Scope

The following are explicitly deferred to subsequent phases:

- **AI project organization and smart organizer** — The intelligent project analysis and reorganization features. Phase 1 establishes the AI execution pipeline; smart organization logic comes later.
- **Template engine** — Project templates and scaffolding.
- **MIDI generation** — AI-driven MIDI content creation.
- **Usage analytics** — Telemetry, usage tracking, and analytics dashboards.
- **Multi-device management UI** — The `devices` table is created in Phase 1 (referenced by bridge token auth), but the UI for managing multiple registered devices is deferred.
- **Multi-user / multi-instance per machine** — Phase 1 assumes a single user per machine. Multiple DAW instances or OS user accounts on one machine are out of scope.
- **Ableton Live bridge implementation** — The bridge directory structure and interface contracts are established in Phase 1. The actual Ableton Remote Script adapter is deferred. The plugin binary is already DAW-agnostic and requires no changes when Ableton support is added.
- **Windows installer** — Phase 1 targets macOS. The Windows `.exe` installer is a Phase 2 deliverable.

---

## 12. Summary

Studio AI's architecture is designed around a clear separation of concerns: the Next.js application owns AI processing and user-facing functionality, FastAPI owns real-time WebSocket connectivity, the Rust plugin owns the in-DAW experience, and thin Python bridge scripts own DAW API translation. Every component communicates through well-defined message envelopes over WebSocket or HTTP. Redis provides the shared state layer that makes horizontal scaling possible from the first deployment. Authentication flows through standard web mechanisms without OS-level dependencies.

Phase 1 delivers the complete infrastructure pipeline from a user's natural language prompt to a DAW API call and back, along with the SaaS scaffolding (auth, billing, installer) required to ship it as a product. This foundation is deliberately over-engineered for extensibility — adding a new DAW, a new AI capability, or a new subscription tier requires changes to exactly one component in the system.
