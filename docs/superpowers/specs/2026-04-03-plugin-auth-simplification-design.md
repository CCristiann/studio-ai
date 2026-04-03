# Plugin Auth — Secure Device Authorization Flow

**Date:** April 3, 2026
**Status:** Revised (v2)
**Authors:** Cristian Cirje

---

## 1. Problem

The plugin's embedded WebView cannot run Google OAuth directly — Google blocks or degrades OAuth in embedded browser contexts. The WebView also has its own cookie jar, separate from the system browser, so a session established in the browser is not visible to the plugin.

The original code-based flow (generate 6-char code in dashboard, type it in plugin) worked but required manual copying every time the WebView storage was cleared or FL Studio restarted.

## 2. Solution

Implement a **Device Authorization Flow** inspired by OAuth 2.0 RFC 8628. The plugin opens the system browser for Google OAuth. After authentication, a secure token exchange delivers a JWT to the WebView automatically — no manual code copying.

### 2.1 Flow

1. User opens plugin in FL Studio. WebView loads `/plugin?context=plugin`.
2. WebView checks localStorage for an existing JWT.
   - **Token found and valid:** proceed to chat (step 8).
   - **Token found but expired:** clear it, proceed to step 3.
   - **No token:** proceed to step 3.
3. WebView shows "Sign in with Google" button.
4. User clicks the button. WebView calls `POST /api/auth/device` (no auth required).
   - Server generates a `session_id` (UUID) and a `device_code` (32 bytes, crypto-random, base64url).
   - Server stores in `device_sessions` table: `{ session_id, device_code_hash: SHA256(device_code), user_id: null, status: 'pending', expires_at: now + 5 min }`.
   - Returns `{ session_id, device_code, expires_in: 300, interval: 2 }`.
5. WebView opens the system browser to `http://localhost:3000/auth/device/authorize?session_id=UUID`.
   - Browser page checks NextAuth session.
   - **Not logged in:** redirects to Google OAuth, then back to authorize page.
   - **Logged in:** shows "Authorize Studio AI Plugin?" with an Approve button.
   - On Approve: server updates `device_sessions` row — sets `user_id` and `status = 'approved'`.
   - Browser shows "Plugin authorized! You can close this tab."
6. WebView polls `POST /api/auth/device/token` every 2 seconds with `{ session_id, device_code }`.
   - Server looks up `device_sessions` by `session_id`.
   - Verifies `SHA256(device_code)` matches stored `device_code_hash`.
   - If `status = 'pending'`: returns `{ status: 'pending' }`.
   - If `status = 'approved'`: generates JWT (signed with `NEXTAUTH_SECRET`, contains `userId`, 7-day expiry), deletes session row, returns `{ status: 'complete', token }`.
   - If expired or not found: returns `{ status: 'expired' }`.
7. WebView receives JWT, stores it in `localStorage('studio-ai-token')`.
8. WebView sends JWT to Rust via IPC `window.__bridge__.sendToken(jwt)`.
9. WebView renders chat. API calls use `Authorization: Bearer <JWT>`.
10. Rust authenticates WebSocket to FastAPI with the JWT.

### 2.2 Security Properties

| Property | Implementation |
|----------|---------------|
| **device_code never exposed** | Stays in WebView memory. Only `SHA256(device_code)` is stored in DB. Never appears in any URL. |
| **Two-factor exchange** | Token exchange requires both `session_id` (from browser URL) AND `device_code` (from WebView). Intercepting one is insufficient. |
| **One-time use** | Device session row is deleted after successful token exchange. |
| **Short TTL** | Device sessions expire after 5 minutes. Stale rows are ignored. |
| **No tokens in URLs** | Polling uses POST with JSON body. JWT never appears in any URL. `session_id` in browser URL is a UUID with no auth value on its own. |
| **Signed JWT** | HMAC-SHA256 signed with `NEXTAUTH_SECRET`. Payload: `{ userId, iat, exp }`. |
| **Brute-force resistant** | `device_code` is 32 bytes crypto-random (256-bit entropy). |
| **Rate limiting** | Polling interval enforced at 2 seconds. Server rejects faster polling with `{ status: 'slow_down' }`. |

### 2.3 Token Lifecycle

- **JWT expiration:** 7 days (per architecture spec).
- **Storage:** WebView `localStorage` (persists across FL Studio sessions if WebView supports it).
- **On expiry:** WebView detects 401 from API, clears stored token, shows "Sign in" button.
- **Revocation:** Not supported in Phase 1. JWT is stateless. User can re-authenticate to get a new token.

### 2.4 Scalability

| Aspect | Choice |
|--------|--------|
| **Device session storage** | Supabase `device_sessions` table — works across multiple Vercel instances. |
| **JWT stateless** | After exchange, no server-side lookup needed for API calls. |
| **Automatic cleanup** | Expired sessions excluded by `WHERE expires_at > now()` in queries. Periodic cleanup via Supabase cron or on-query deletion. |

## 3. Database Migration

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

## 4. New Files

| File | Responsibility |
|------|---------------|
| `apps/web/src/app/api/auth/device/route.ts` | `POST` — create device session, return `session_id` + `device_code` |
| `apps/web/src/app/api/auth/device/token/route.ts` | `POST` — poll for approval, exchange for JWT |
| `apps/web/src/app/auth/device/authorize/page.tsx` | Browser UI — "Authorize Studio AI Plugin?" with Approve button |
| `apps/web/src/lib/plugin-auth.ts` | `verifyPluginToken()` — verify JWT signed with `NEXTAUTH_SECRET` |
| `apps/web/src/lib/device-session.ts` | Device session CRUD — create, find, approve, delete, with Supabase client |
| `apps/web/src/app/(plugin)/plugin/plugin-login.tsx` | WebView UI — "Sign in with Google" button + polling logic |

## 5. Files to Modify

| File | Change |
|------|--------|
| `apps/web/src/middleware.ts` | Add `/auth/device`, `/api/auth/device` to public paths |
| `apps/web/src/app/(plugin)/plugin/page.tsx` | Check localStorage for existing token, show login or chat |
| `apps/web/src/app/api/ai/execute/route.ts` | Restore Bearer token path in `getUserId()` |
| `apps/web/src/app/(plugin)/plugin/plugin-chat.tsx` | Accept token prop, send as Bearer header |

## 6. Files Unchanged

| File | Reason |
|------|--------|
| `apps/web/src/lib/auth.ts` | NextAuth config unchanged |
| `plugin/src/lib.rs` | Rust IPC `sendToken` flow unchanged |
| `plugin/src/websocket_cloud.rs` | WebSocket JWT auth unchanged |

## 7. Error Handling

| Scenario | Behavior |
|----------|----------|
| Device session expired | Polling returns `{ status: 'expired' }`. WebView shows "Session expired, try again." |
| User denies authorization | Browser shows deny confirmation. Session stays pending, expires after 5 min. WebView times out. |
| Google OAuth fails | NextAuth error page in browser. User can retry. WebView continues polling until timeout. |
| Invalid device_code | Polling returns 401. WebView shows error, resets. |
| JWT expired (during usage) | API returns 401. WebView clears localStorage, shows "Sign in" button. |
| Network error during polling | WebView retries on next interval. Shows "Waiting for authorization..." |
| Polling too fast | Server returns `{ status: 'slow_down' }`. WebView backs off. |
