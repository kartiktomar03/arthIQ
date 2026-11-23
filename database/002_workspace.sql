-- Run once as administrator in querypilot_ai, then set the login password via psql.
BEGIN;
CREATE ROLE querypilot_workspace LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE querypilot_ai TO querypilot_workspace;
CREATE SCHEMA qp_app;
CREATE TABLE qp_app.conversations (
 id uuid PRIMARY KEY, owner text NOT NULL, title text NOT NULL, state jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE qp_app.runs (
 id uuid PRIMARY KEY, conversation_id uuid NOT NULL REFERENCES qp_app.conversations ON DELETE CASCADE,
 question text NOT NULL, result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX runs_conversation_time ON qp_app.runs(conversation_id,created_at);
CREATE TABLE qp_app.cards (
 id uuid PRIMARY KEY, owner text NOT NULL, title text NOT NULL, snapshot jsonb NOT NULL,
 generated_at timestamptz NOT NULL
);
GRANT USAGE ON SCHEMA qp_app TO querypilot_workspace;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA qp_app TO querypilot_workspace;
COMMIT;
