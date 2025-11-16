-- Optional initialization SQL for Postgres
-- You can add extensions or seed data here.
-- Example: create extension if not exists "uuid-ossp";

CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value JSONB
);
