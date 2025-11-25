-- Migration script: add normalized columns and backfill from JSONB `data`.
-- Ensure this migration runs inside the dedicated `auvo` schema so the project
-- objects don't pollute the public schema when sharing the same database with
-- other projects (for example `e-track`).
CREATE SCHEMA IF NOT EXISTS auvo;
SET search_path = auvo, public;

-- Run once: docker-compose exec -T db psql -U auvo -d <db> -f migrate_schema.sql
BEGIN;

-- USERS: add normalized columns
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS name TEXT,
  ADD COLUMN IF NOT EXISTS login TEXT,
  ADD COLUMN IF NOT EXISTS email TEXT,
  ADD COLUMN IF NOT EXISTS user_id BIGINT,
  ADD COLUMN IF NOT EXISTS base_lat DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS base_lon DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMP DEFAULT now();

-- TASKS: add normalized columns
ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS task_id BIGINT,
  ADD COLUMN IF NOT EXISTS task_date TIMESTAMP WITH TIME ZONE,
  ADD COLUMN IF NOT EXISTS customer_id BIGINT,
  ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS task_status INTEGER,
  ADD COLUMN IF NOT EXISTS user_from BIGINT,
  ADD COLUMN IF NOT EXISTS user_to BIGINT,
  ADD COLUMN IF NOT EXISTS external_id TEXT;
  -- ensure fetched_at exists for compatibility with current upsert logic
  ALTER TABLE tasks ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMP DEFAULT now();

-- CUSTOMERS: add normalized columns
ALTER TABLE customers
  ADD COLUMN IF NOT EXISTS customer_id BIGINT,
  ADD COLUMN IF NOT EXISTS external_id TEXT,
  ADD COLUMN IF NOT EXISTS customer_name TEXT,
  ADD COLUMN IF NOT EXISTS address TEXT,
  ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMP DEFAULT now();

-- Backfill users
UPDATE users SET
  name = COALESCE(data->>'name', data->'result'->0->>'name'),
  login = COALESCE(data->>'login', data->'result'->0->>'login'),
  email = data->>'email',
  user_id = (COALESCE((data->>'userId'), (data->>'userID')) )::BIGINT
WHERE (data ? 'name') OR (data ? 'login') OR (data ? 'userId');

-- Backfill tasks
UPDATE tasks SET
  task_id = (COALESCE(data->>'taskID', data->>'taskId'))::BIGINT,
  task_date = (COALESCE(data->>'taskDate', data->'result'->0->>'taskDate'))::timestamp with time zone,
  customer_id = (data->>'customerId')::BIGINT,
  latitude = (data->>'latitude')::DOUBLE PRECISION,
  longitude = (data->>'longitude')::DOUBLE PRECISION,
  task_status = (data->>'taskStatus')::INTEGER,
  user_from = (COALESCE(data->>'idUserFrom', data->>'userIdFrom'))::BIGINT,
  user_to = (COALESCE(data->>'idUserTo', data->>'userIdTo'))::BIGINT,
  external_id = data->>'externalId'
WHERE (data ? 'taskID') OR (data ? 'taskDate');

-- Backfill customers
UPDATE customers SET
  customer_id = (COALESCE(data->>'customerId', data->>'id'))::BIGINT,
  external_id = data->>'externalId',
  customer_name = COALESCE(data->>'name', data->'result'->0->>'name'),
  address = COALESCE(data->>'address', data->'BasePoint'->>'address'),
  latitude = (COALESCE(data->>'latitude', data->'BasePoint'->>'latitude'))::DOUBLE PRECISION,
  longitude = (COALESCE(data->>'longitude', data->'BasePoint'->>'longitude'))::DOUBLE PRECISION
WHERE (data ? 'customerId') OR (data ? 'name');

-- Indexes for faster joins/queries
CREATE INDEX IF NOT EXISTS idx_tasks_task_date ON tasks (task_date);
CREATE INDEX IF NOT EXISTS idx_tasks_customer_id ON tasks (customer_id);
CREATE INDEX IF NOT EXISTS idx_tasks_task_id ON tasks (task_id);
CREATE INDEX IF NOT EXISTS idx_users_user_id ON users (user_id);
CREATE INDEX IF NOT EXISTS idx_customers_customer_id ON customers (customer_id);

COMMIT;

-- Notes:
-- The backfill uses simple jsonb ->> extraction; depending on your real payload nesting you
-- may need to adapt the paths (e.g. `data->'result'->'entityList'->0->>'taskDate'`).
