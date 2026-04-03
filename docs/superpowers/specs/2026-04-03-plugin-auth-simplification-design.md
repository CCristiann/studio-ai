# Plugin Auth Simplification

**Date:** April 3, 2026
**Status:** Draft
**Authors:** Cristian Cirje

---

## 1. Problem

The current plugin authentication flow requires users to:

1. Log into the dashboard in their browser
2. Generate a 6-character code (valid 5 minutes)
3. Open the plugin in FL Studio
4. Manually type the code into the plugin WebView
5. Repeat this every time the WebView storage is cleared or FL Studio restarts

This creates unnecessary friction. The plugin WebView is a standard browser context capable of running the same Google OAuth flow used by the dashboard.

## 2. Solution

Replace the code-based authentication with direct Google OAuth in the plugin WebView via NextAuth. The plugin uses the same session mechanism as the dashboard — no custom JWT, no code exchange, no separate auth path.

### 2.1 New Flow

1. User opens plugin in FL Studio. WebView loads `/?context=plugin`.
2. Middleware checks NextAuth session cookie.
3. **Not authenticated:** redirect to `/api/auth/signin` (Google OAuth in WebView).
4. Google OAuth completes. NextAuth sets session cookie in WebView cookie jar.
5. Redirect back to `/plugin`. User sees the chat interface.
6. WebView sends JWT to Rust via IPC (`window.__bridge__.sendToken(jwt)`).
7. Rust authenticates WebSocket to FastAPI with the JWT.

**On subsequent opens:** if WebView retains cookies, user goes directly to step 5. If cookies are cleared, user re-authenticates with Google (one click if already signed into Google). This is an acceptable trade-off per architecture decision 4.3.

### 2.2 Session Persistence

All authentication state lives in the WebView's standard web storage (cookies, localStorage). No tokens are persisted on the file system or OS keychain, per architecture principle #6.

NextAuth handles JWT refresh automatically within the WebView session. On refresh, the WebView notifies the Rust plugin via `sendToken` with the new JWT.

### 2.3 API Authentication

The `/api/ai/execute` endpoint uses `auth()` from NextAuth for both contexts (dashboard and plugin). The Bearer token path is removed.

## 3. Files to Delete

| File | Reason |
|------|--------|
| `apps/web/src/lib/plugin-codes.ts` | In-memory code store, no longer needed |
| `apps/web/src/lib/plugin-auth.ts` | Custom JWT verification for plugin tokens |
| `apps/web/src/app/(plugin)/plugin/plugin-login.tsx` | Code entry UI |
| `apps/web/src/app/api/auth/plugin-token/route.ts` | Code generation and token exchange endpoint |
| `apps/web/src/app/dashboard/` | Plugin connection page with "generate code" UI |

## 4. Files to Modify

### 4.1 `apps/web/src/middleware.ts`

Simplify plugin route handling. Routes under `/plugin` use the same NextAuth session check as the dashboard. Remove special handling for `?token=` query parameter. If not authenticated, redirect to sign-in.

### 4.2 `apps/web/src/app/(plugin)/plugin/page.tsx`

Remove token detection logic (URL params, sessionStorage). Read session via `auth()` server-side. Render `PluginChat` directly when authenticated.

### 4.3 `apps/web/src/app/api/ai/execute/route.ts`

Remove the Bearer token path in `getUserId()`. Use only `auth()` from NextAuth. Both plugin and dashboard requests carry the same NextAuth session cookie.

### 4.4 `plugin/src/lib.rs`

No functional change. The Rust plugin continues to receive JWT via IPC `sendToken`. The only difference is the token now comes from the NextAuth OAuth flow instead of the code exchange.

## 5. Files Unchanged

| File | Reason |
|------|--------|
| `apps/web/src/lib/auth.ts` | NextAuth config stays the same |
| `plugin/src/websocket_cloud.rs` | WebSocket auth unchanged |
| `apps/web/src/app/(plugin)/plugin/plugin-chat.tsx` | Chat UI unchanged |

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| Google OAuth fails in WebView | NextAuth error page renders in WebView. User can retry. |
| Session cookie expired | Middleware redirects to sign-in. One-click re-auth. |
| JWT refresh fails | WebView shows sign-in. Rust WebSocket disconnects, reconnects after new `sendToken`. |
| WebView storage cleared | Same as session expired — redirect to sign-in. |
