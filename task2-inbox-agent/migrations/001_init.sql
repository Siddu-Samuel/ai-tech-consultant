CREATE TABLE IF NOT EXISTS email_cases (
  id TEXT PRIMARY KEY,
  request_id TEXT UNIQUE,
  input_json JSONB NOT NULL,
  fixture_expected JSONB,
  classification_json JSONB,
  knowledge_json JSONB,
  original_draft TEXT,
  final_reply TEXT,
  source_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
  model_id TEXT,
  prompt_version TEXT,
  latency_ms INTEGER,
  input_tokens INTEGER,
  output_tokens INTEGER,
  cost_usd NUMERIC(14,8),
  status TEXT NOT NULL DEFAULT 'new',
  approval_status TEXT NOT NULL DEFAULT 'pending',
  needs_human_approval BOOLEAN NOT NULL DEFAULT TRUE,
  reason_for_escalation TEXT,
  next_action TEXT,
  modified BOOLEAN NOT NULL DEFAULT FALSE,
  mode TEXT NOT NULL DEFAULT 'demo',
  actual_sent BOOLEAN NOT NULL DEFAULT FALSE,
  send_provider_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_email_cases_status_created ON email_cases(status, created_at DESC);

CREATE TABLE IF NOT EXISTS feedback_events (
  id UUID PRIMARY KEY,
  email_case_id TEXT NOT NULL REFERENCES email_cases(id),
  event_type TEXT NOT NULL,
  before_text TEXT,
  after_text TEXT,
  reviewer TEXT,
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feedback_events_case_time ON feedback_events(email_case_id, created_at);

CREATE TABLE IF NOT EXISTS autonomy_state (
  category_key TEXT PRIMARY KEY,
  consecutive_unchanged_count INTEGER NOT NULL DEFAULT 0,
  eligible BOOLEAN NOT NULL DEFAULT FALSE,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  last_qualifying_event TIMESTAMPTZ,
  last_failure TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
