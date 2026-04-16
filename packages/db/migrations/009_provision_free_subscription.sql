-- Auto-provision a free-tier subscription row for every new user.
-- Pairs with the WS subscription check (apps/api/routers/websocket.py),
-- which fails closed when no row exists. Without this trigger, every new
-- signup would be denied at WSS connect.

CREATE OR REPLACE FUNCTION public.provision_free_subscription()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.subscriptions (user_id, plan, status)
  SELECT NEW.id, 'free', 'active'
  WHERE NOT EXISTS (
    SELECT 1 FROM public.subscriptions WHERE user_id = NEW.id
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_provision_free_subscription ON next_auth.users;

CREATE TRIGGER trg_provision_free_subscription
AFTER INSERT ON next_auth.users
FOR EACH ROW
EXECUTE FUNCTION public.provision_free_subscription();

-- Backfill: existing users without a subscription row get a free/active one.
INSERT INTO public.subscriptions (user_id, plan, status)
SELECT u.id, 'free', 'active'
FROM next_auth.users u
WHERE NOT EXISTS (
  SELECT 1 FROM public.subscriptions s WHERE s.user_id = u.id
);
