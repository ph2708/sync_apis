#!/usr/bin/env python3
"""Run `migrate_schema.sql` against the configured Postgres database.

Idempotent: it records runs in a `migrations` table and will skip running
the same migration more than once per day.

Env vars (defaults match docker-compose):
- PGHOST (default: localhost)
- PGPORT (default: 5432)
- PGUSER (default: auvo)
- PGPASSWORD (default: auvo_pass)
- PGDATABASE (default: auvo)
"""
import os
import sys
from datetime import datetime, date

import psycopg2

BASE_DIR = os.path.dirname(__file__)
SQL_FILE = os.path.join(BASE_DIR, "migrate_schema.sql")

DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5432")),
    "user": os.getenv("PGUSER", "auvo"),
    "password": os.getenv("PGPASSWORD", "auvo_pass"),
    "dbname": os.getenv("PGDATABASE", "auvo"),
}


def load_sql():
    if not os.path.exists(SQL_FILE):
        print(f"migrate file not found: {SQL_FILE}")
        sys.exit(1)
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        return f.read()


def ensure_migrations_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS migrations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            run_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def already_run_today(cur, name):
    cur.execute(
        "SELECT run_at FROM migrations WHERE name = %s ORDER BY run_at DESC LIMIT 1",
        (name,),
    )
    row = cur.fetchone()
    if not row:
        return False
    last = row[0].date()
    return last >= date.today()


def record_run(cur, name):
    cur.execute("INSERT INTO migrations (name, run_at) VALUES (%s, now())", (name,))


def run_migration():
    sql = load_sql()
    migration_name = os.path.basename(SQL_FILE)

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            with conn.cursor() as cur:
                ensure_migrations_table(cur)
                if already_run_today(cur, migration_name):
                    print(f"Migration '{migration_name}' already run today ({date.today()}). Skipping.")
                    return 0

                print(f"Running migration '{migration_name}'...")
                # execute whole SQL file; it's expected to be idempotent
                cur.execute(sql)
                record_run(cur, migration_name)
                print("Migration executed successfully.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(run_migration())
    except Exception as e:
        print("Migration failed:", e)
        sys.exit(2)
