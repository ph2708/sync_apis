#!/usr/bin/env python3
"""Reset Auvo Postgres tables (truncate) safely.

Usage:
  - Ensure `.env` is present or the PG env vars/PG_DSN are set.
  - Run `python3 reset_db.py` and confirm when prompted, or `python3 reset_db.py --yes` to skip prompt.

This will TRUNCATE the tables: users, tasks, customers.
"""
import os
import argparse
import sys
import psycopg2


def pg_connect():
    # Prefer explicit DSN, otherwise read PG* env vars with fallbacks to the
    # monorepo centralized defaults. Allow AUVO_* overrides if present.
    dsn = os.getenv('PG_DSN') or os.getenv('AUVO_PG_DSN')
    host = os.getenv('PGHOST') or os.getenv('AUVO_PG_HOST') or '127.0.0.1'
    port = os.getenv('PGPORT') or os.getenv('AUVO_PG_PORT') or '5432'
    db = os.getenv('PGDATABASE') or os.getenv('AUVO_PG_DB') or 'sync_apis'
    user = os.getenv('PGUSER') or os.getenv('AUVO_PG_USER') or 'sync_user'
    pwd = os.getenv('PGPASSWORD') or os.getenv('AUVO_PG_PASSWORD') or 'sync_pass'
    if dsn:
        return psycopg2.connect(dsn)
    missing = []
    if not db:
        missing.append('PGDATABASE')
    if not user:
        missing.append('PGUSER')
    if not pwd:
        missing.append('PGPASSWORD')
    if missing:
        raise RuntimeError(f'Missing Postgres configuration: set PG_DSN or the env vars: {", ".join(missing)}')
    return psycopg2.connect(host=host, port=port, dbname=db, user=user, password=pwd)


def confirm(prompt):
    try:
        return input(prompt).strip().lower() in ('y', 'yes')
    except KeyboardInterrupt:
        return False


def main():
    parser = argparse.ArgumentParser(description='Truncate Auvo tables (users,tasks,customers)')
    parser.add_argument('--yes', action='store_true', help='Skip confirmation')
    parser.add_argument('--tables', nargs='*', default=['users', 'tasks', 'customers'], help='Tables to truncate')
    args = parser.parse_args()

    if not args.yes:
        print('WARNING: This will DELETE ALL DATA from the selected tables in your Postgres database.')
        ok = confirm('Type YES to continue: ')
        if not ok:
            print('Aborted.')
            sys.exit(1)

    conn = pg_connect()
    cur = conn.cursor()
    try:
        # show counts before
        counts = {}
        schema = os.getenv('AUVO_SCHEMA', 'auvo')
        for t in args.tables:
            cur.execute(f"SELECT COUNT(*) FROM {schema}.{t}")
            counts[t] = cur.fetchone()[0]
        print('Counts before truncation:')
        for t, c in counts.items():
            print(f'  {t}: {c}')

        # perform truncate
        # Truncate schema-qualified tables to avoid accidental truncation of
        # tables in other schemas.
        tbls = ', '.join(f"{schema}.{t}" for t in args.tables)
        cur.execute(f"TRUNCATE TABLE {tbls} RESTART IDENTITY CASCADE")
        conn.commit()

        # show counts after
        after = {}
        for t in args.tables:
            cur.execute(f"SELECT COUNT(*) FROM {schema}.{t}")
            after[t] = cur.fetchone()[0]
        print('Counts after truncation:')
        for t, c in after.items():
            print(f'  {t}: {c}')

    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
