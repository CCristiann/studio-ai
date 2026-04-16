-- Retention cron for auth_events (audit finding M8, 2026-04-16).
--
-- 90 days is the trade: long enough to investigate "why did my plugin stop
-- working last month?" reports, short enough that the table doesn't balloon
-- on a product with O(login+token-issuance)/user/day baseline volume.
--
-- Schedule aligns with the existing 03:17 UTC cleanup jobs (see migration 011)
-- to keep the maintenance burst in a single off-peak window.

SELECT cron.schedule(
  'cleanup-expired-auth-events',
  '17 3 * * *',
  $$DELETE FROM public.auth_events WHERE created_at < now() - interval '90 days'$$
);
