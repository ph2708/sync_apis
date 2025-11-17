-- Optional initialization SQL for Postgres
-- You can add extensions or seed data here.
-- Example: create extension if not exists "uuid-ossp";

-- Create and use a dedicated schema for this project so multiple projects can
-- share the same Postgres database while keeping objects organized.
CREATE SCHEMA IF NOT EXISTS auvo;
SET search_path = auvo, public;

CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value JSONB
);
