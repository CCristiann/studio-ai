-- Defense-in-depth: enable RLS on auth-bearing tables and deny by default.
-- Service-role bypasses RLS, so the FastAPI relay (which uses the service-role
-- key) keeps working. The point is to slam the door if `anon` or
-- `authenticated` keys are ever (mis)used to query these tables — currently
-- only service-role grants exist, but RLS makes that contract explicit and
-- survives future grant changes.

ALTER TABLE public.plugin_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.device_sessions ENABLE ROW LEVEL SECURITY;

-- No policies = deny-all for non-bypass roles.
-- (We intentionally do NOT add an `authenticated` policy for self-row access.
-- Plugin tokens and device sessions are server-side only — clients should
-- never read them directly. The web UI gets state via /api/auth/* routes
-- that run with the service-role key.)

REVOKE ALL ON public.plugin_tokens FROM anon, authenticated;
REVOKE ALL ON public.device_sessions FROM anon, authenticated;
