-- Registered devices table
-- Tracks plugin installations per user

CREATE TABLE IF NOT EXISTS public.devices (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  device_name  TEXT,
  device_token TEXT UNIQUE,
  platform     TEXT NOT NULL,
  daw          TEXT NOT NULL,
  last_seen    TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_id      UUID NOT NULL REFERENCES next_auth.users(id) ON DELETE CASCADE,
  CONSTRAINT valid_platform CHECK (platform IN ('macos', 'windows')),
  CONSTRAINT valid_daw CHECK (daw IN ('fl_studio', 'ableton'))
);

CREATE INDEX idx_devices_user_id ON public.devices(user_id);
