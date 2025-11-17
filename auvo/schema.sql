-- Basic schema for Auvo project. Creates core tables if they do not exist.
CREATE SCHEMA IF NOT EXISTS auvo;
SET search_path = auvo, public;

CREATE TABLE IF NOT EXISTS users (
  id BIGSERIAL PRIMARY KEY,
  external_id TEXT,
  data JSONB,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS customers (
  id BIGSERIAL PRIMARY KEY,
  customer_id BIGINT,
  external_id TEXT,
  customer_name TEXT,
  address TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  data JSONB,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
  id BIGSERIAL PRIMARY KEY,
  task_id BIGINT,
  task_date TIMESTAMP WITH TIME ZONE,
  customer_id BIGINT,
  user_from BIGINT,
  user_to BIGINT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  task_status INTEGER,
  external_id TEXT,
  data JSONB,
  created_at TIMESTAMP DEFAULT now()
);

-- Indexes useful for joins/queries
CREATE INDEX IF NOT EXISTS idx_users_external_id ON users (external_id);
CREATE INDEX IF NOT EXISTS idx_customers_customer_id ON customers (customer_id);
CREATE INDEX IF NOT EXISTS idx_tasks_task_id ON tasks (task_id);
