-- User projects table
-- Tracks DAW projects associated with each user

CREATE TABLE IF NOT EXISTS public.projects (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES next_auth.users(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  daw        TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT valid_project_daw CHECK (daw IN ('fl_studio', 'ableton'))
);

CREATE INDEX idx_projects_user_id ON public.projects(user_id);
