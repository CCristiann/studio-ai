CREATE TABLE plugin_tokens (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  jti        TEXT UNIQUE NOT NULL,
  user_id    TEXT NOT NULL,
  revoked    BOOLEAN NOT NULL DEFAULT false,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_plugin_tokens_jti ON plugin_tokens(jti);
CREATE INDEX idx_plugin_tokens_user_id ON plugin_tokens(user_id);

GRANT ALL ON plugin_tokens TO service_role;
GRANT ALL ON plugin_tokens TO postgres;

NOTIFY pgrst, 'reload schema';
