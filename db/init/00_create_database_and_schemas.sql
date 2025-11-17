-- Initialization script run by postgres image on first boot.
-- This runs as the user defined by POSTGRES_USER and against POSTGRES_DB.

-- Create schemas for each project
CREATE SCHEMA IF NOT EXISTS auvo;
CREATE SCHEMA IF NOT EXISTS e_track;

-- Create project-specific roles (optional) and grant minimal privileges.
-- Passwords here are example values; change them in production or use secrets.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'auvo_user') THEN
    CREATE ROLE auvo_user WITH LOGIN PASSWORD 'auvo_pass';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'etrack_user') THEN
    CREATE ROLE etrack_user WITH LOGIN PASSWORD 'etrack_pass';
  END IF;
END$$;

-- Grant usage on schemas to the project roles
GRANT USAGE ON SCHEMA auvo TO auvo_user;
GRANT USAGE ON SCHEMA e_track TO etrack_user;

-- Grant the database owner (POSTGRES_USER) all privileges on the schemas so
-- migrations run as that user can create objects there.
GRANT ALL ON SCHEMA auvo TO CURRENT_USER;
GRANT ALL ON SCHEMA e_track TO CURRENT_USER;

-- Note: The postgres image already creates the DB and the POSTGRES_USER role.
-- Project migrations should run afterwards (they will create tables/indexes
-- inside their respective schemas). If you prefer different usernames or
-- more restrictive privileges, modify this script accordingly.
