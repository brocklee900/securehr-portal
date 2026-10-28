-- Runs on first Postgres start (empty DB). App-owned objects live in schema `app`;
-- migrated employee data lands in schema `hr` (see scripts/migrate_mysql_to_pg.sh).
\set app_pw `echo "$PORTAL_APP_PASSWORD"`
CREATE ROLE portal_app LOGIN PASSWORD :'app_pw' NOSUPERUSER NOBYPASSRLS;

CREATE SCHEMA app;
CREATE TABLE app.audit_log (
  id          BIGSERIAL PRIMARY KEY,
  at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  username    TEXT NOT NULL,
  role        TEXT NOT NULL,
  action      TEXT NOT NULL,
  resource    TEXT NOT NULL,
  detail      JSONB
);
CREATE INDEX ON app.audit_log (at DESC);
CREATE INDEX ON app.audit_log (username);

GRANT USAGE ON SCHEMA app TO portal_app;
GRANT INSERT ON app.audit_log TO portal_app;       -- append-only for the API
GRANT USAGE ON SEQUENCE app.audit_log_id_seq TO portal_app;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
