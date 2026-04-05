-- Presets: saved AI prompt templates per user
CREATE TABLE public.presets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  prompt TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_presets_user_id ON public.presets(user_id);

COMMENT ON COLUMN public.presets.user_id IS 'References next_auth.users.id — no FK because NextAuth manages user lifecycle externally';
