-- User preferences: onboarding state and future settings
CREATE TABLE public.user_preferences (
  user_id TEXT PRIMARY KEY,
  onboarding_completed BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

COMMENT ON COLUMN public.user_preferences.user_id IS 'References next_auth.users.id — no FK because NextAuth manages user lifecycle externally';
