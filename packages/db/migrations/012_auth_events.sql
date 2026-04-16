-- Audit trail for authentication lifecycle events (audit finding M8, 2026-04-16).
--
-- Writes happen via `apps/web/src/lib/auth-events.ts`. The helper is best-effort:
-- insert errors are logged but never thrown, so a broken audit pipe cannot
-- break sign-in / token issuance / device approval.
--
-- Event types in use (keep in sync with AuthEventType in the helper):
--   plugin_token_issued   — new plugin JWT minted and row stored
--   plugin_token_revoked  — user-initiated sign-out revokes active tokens
--   device_code_approved  — /link page approves a pending device session
--   login_succeeded       — NextAuth `events.signIn` fired
--   login_failed          — /login page observed ?error=... callback
--
-- Retention: 90 days. Audit data is a cost/benefit trade — older events rarely
-- help investigations and we don't want table bloat. See migration 013.

CREATE TABLE auth_events (
  id         BIGSERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  user_id    TEXT,
  session_id UUID,
  jti        TEXT,
  ip         TEXT,
  user_agent TEXT,
  success    BOOLEAN NOT NULL,
  reason     TEXT,
  metadata   JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT auth_events_event_type_check CHECK (event_type IN (
    'plugin_token_issued',
    'plugin_token_revoked',
    'device_code_approved',
    'login_succeeded',
    'login_failed'
  ))
);

-- Per-user audit view: "show me the last N events for user X"
CREATE INDEX idx_auth_events_user_created
  ON auth_events (user_id, created_at DESC)
  WHERE user_id IS NOT NULL;

-- Type-scoped investigations: "all failed logins in the last 24h"
CREATE INDEX idx_auth_events_type_created
  ON auth_events (event_type, created_at DESC);

-- Global recency: "last N events across everything"
CREATE INDEX idx_auth_events_created
  ON auth_events (created_at DESC);

GRANT ALL ON auth_events TO service_role;
GRANT ALL ON auth_events TO postgres;
GRANT USAGE, SELECT ON SEQUENCE auth_events_id_seq TO service_role;
GRANT USAGE, SELECT ON SEQUENCE auth_events_id_seq TO postgres;

NOTIFY pgrst, 'reload schema';
