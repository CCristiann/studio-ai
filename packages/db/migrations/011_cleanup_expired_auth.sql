-- Periodic cleanup of expired auth rows. Without this the
-- plugin_tokens and device_sessions tables grow unbounded
-- (audit finding H4, 2026-04-15).
--
-- Schedule:
--   - device_sessions: deleted as soon as expired (15-min TTL — no
--     debugging value in keeping them around).
--   - plugin_tokens: kept 7 days past expiry so we can investigate
--     "why was I logged out?" reports without losing context.
--
-- Requires the pg_cron extension (must be enabled by Supabase project owner
-- in dashboard: Database -> Extensions -> pg_cron). The CREATE EXTENSION
-- below is idempotent and will no-op if already enabled.

CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Run daily at 03:17 UTC (off-peak, prime-ish minute to avoid scheduler herd).
SELECT cron.schedule(
  'cleanup-expired-device-sessions',
  '17 3 * * *',
  $$DELETE FROM public.device_sessions WHERE expires_at < now()$$
);

SELECT cron.schedule(
  'cleanup-expired-plugin-tokens',
  '17 3 * * *',
  $$DELETE FROM public.plugin_tokens WHERE expires_at < now() - interval '7 days'$$
);
