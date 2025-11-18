#!/usr/bin/env python3
"""Daily runner to compute and store routes for all plates.

Reuses logic in `collector.py`. Features:
- advisory lock to avoid concurrent runs
- configurable sleep between plates (rate-limit)
- batch processing and simple logging
"""
import os
import time
import argparse
from datetime import datetime, timedelta
import logging
from dotenv import load_dotenv

here = os.path.dirname(__file__)
repo_root = os.path.abspath(os.path.join(here, '..'))
load_dotenv(os.path.join(repo_root, '.env'), override=False)

import collector

LOG = logging.getLogger('e-track.daily_runner')
LOG.setLevel(os.getenv('ETRAC_LOG_LEVEL', 'INFO').upper())
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
LOG.addHandler(ch)


LOCK_ID = int(os.getenv('ETRAC_DAILY_LOCK_ID', '123456789'))


def acquire_lock(conn):
    cur = conn.cursor()
    cur.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_ID,))
    got = cur.fetchone()[0]
    conn.commit()
    return bool(got)


def release_lock(conn):
    try:
        cur = conn.cursor()
        cur.execute('SELECT pg_advisory_unlock(%s)', (LOCK_ID,))
        conn.commit()
    except Exception:
        LOG.exception('Failed releasing advisory lock')


def discover_plates_from_db(conn):
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT placa FROM positions WHERE placa IS NOT NULL")
        rows = cur.fetchall()
        plates = [r[0] for r in rows if r and r[0]]
        LOG.info('Discovered %d plates from DB', len(plates))
        return plates
    except Exception:
        LOG.exception('Failed to discover plates from DB; falling back to API discovery')
        session = collector.requests.Session()
        return collector.get_all_plates(session)


def process_plates(conn, plates, date_obj, sleep_between=0.2, batch_size=50):
    session = collector.requests.Session()
    total = len(plates)
    LOG.info('Processing %d plates for date %s', total, date_obj)
    processed = 0
    for i in range(0, total, batch_size):
        batch = plates[i:i+batch_size]
        LOG.info('Processing batch %d..%d', i+1, i+len(batch))
        for p in batch:
            try:
                LOG.info('Fetching history for %s', p)
                # API expects DD/MM/YYYY
                date_str = date_obj.strftime('%d/%m/%Y')
                try:
                    collector.fetch_terminal_history(session, conn, p, data=date_str)
                except Exception:
                    LOG.debug('fetch_terminal_history did not succeed (may be optional), continuing to compute')

                n = collector.build_and_store_route_for_date(conn, p, date_obj, session=session)
                LOG.info('Stored route for %s -> %d points', p, n)
            except Exception:
                LOG.exception('Failed processing plate %s', p)
            processed += 1
            time.sleep(sleep_between)
    LOG.info('Completed processing %d plates', processed)


def main():
    parser = argparse.ArgumentParser(description='Daily routes runner for e-track')
    parser.add_argument('--date', help='Date to process (YYYY-MM-DD). Defaults to yesterday', default=None)
    parser.add_argument('--plates-file', help='File with one plate per line (overrides discovery)')
    parser.add_argument('--plates', help='Comma-separated plates (overrides discovery)')
    parser.add_argument('--sleep', type=float, default=float(os.getenv('ETRAC_RATE_SLEEP', '0.2')),
                        help='Seconds to sleep between plates (rate-limit)')
    parser.add_argument('--batch-size', type=int, default=int(os.getenv('ETRAC_BATCH_SIZE', '50')),
                        help='Number of plates per batch')
    args = parser.parse_args()

    # determine date
    if args.date:
        try:
            date_obj = datetime.fromisoformat(args.date).date()
        except Exception:
            LOG.error('Invalid date format -- use YYYY-MM-DD')
            return
    else:
        # default to yesterday
        date_obj = (datetime.now() - timedelta(days=1)).date()

    conn = collector.pg_connect()
    # ensure schema set as collector does in main
    schema = os.getenv('ETRAC_SCHEMA', 'e_track')
    cur = conn.cursor()
    cur.execute(collector.sql.SQL("SET search_path = {}, public").format(collector.sql.Identifier(schema)))
    conn.commit()

    # try to acquire advisory lock
    if not acquire_lock(conn):
        LOG.warning('Another daily runner is already active (advisory lock unavailable). Exiting.')
        return

    try:
        # plates selection
        if args.plates_file:
            with open(args.plates_file, 'r', encoding='utf-8') as fh:
                plates = [l.strip() for l in fh if l.strip()]
        elif args.plates:
            plates = [p.strip() for p in args.plates.split(',') if p.strip()]
        else:
            plates = discover_plates_from_db(conn)

        if not plates:
            LOG.warning('No plates found to process')
            return

        process_plates(conn, plates, date_obj, sleep_between=args.sleep, batch_size=args.batch_size)

    finally:
        release_lock(conn)
        conn.close()


if __name__ == '__main__':
    main()
