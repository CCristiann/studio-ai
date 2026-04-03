CREATE TABLE device_sessions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       UUID UNIQUE NOT NULL,
  device_code_hash TEXT NOT NULL,
  user_id          UUID REFERENCES public.users(id),
  status           TEXT NOT NULL DEFAULT 'pending',
  expires_at       TIMESTAMPTZ NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_device_sessions_session_id ON device_sessions(session_id);
CREATE INDEX idx_device_sessions_expires ON device_sessions(expires_at);
