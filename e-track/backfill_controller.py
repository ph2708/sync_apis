#!/usr/bin/env python3
"""Backfill controller: populate routes for plates over a date range.

This script batches plates and dates, uses advisory lock to avoid concurrent runs,
and respects rate limits. It reuses `collector` functions.
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

LOG = logging.getLogger('e-track.backfill')
LOG.setLevel(os.getenv('ETRAC_LOG_LEVEL', 'INFO').upper())
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
LOG.addHandler(ch)

LOCK_ID = int(os.getenv('ETRAC_BACKFILL_LOCK_ID', '987654321'))


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


def daterange(start_date, end_date):
    d = start_date
    while d <= end_date:
        yield d
        d += timedelta(days=1)


def main():
    parser = argparse.ArgumentParser(description='Backfill routes for plates/date range')
    parser.add_argument('--date-start', required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--date-end', required=True, help='End date YYYY-MM-DD')
    parser.add_argument('--plates-file', help='File with plates (one per line)')
    parser.add_argument('--plates', help='Comma-separated plates')
    parser.add_argument('--sleep', type=float, default=float(os.getenv('ETRAC_RATE_SLEEP', '0.5')),
                        help='Seconds to sleep between requests')
    parser.add_argument('--batch-size', type=int, default=int(os.getenv('ETRAC_BATCH_SIZE', '20')))
    args = parser.parse_args()

    try:
        start_date = datetime.fromisoformat(args.date_start).date()
        end_date = datetime.fromisoformat(args.date_end).date()
    except Exception:
        LOG.error('Invalid date format, use YYYY-MM-DD')
        return

    if args.plates_file:
        with open(args.plates_file, 'r', encoding='utf-8') as fh:
            plates = [l.strip() for l in fh if l.strip()]
    elif args.plates:
        plates = [p.strip() for p in args.plates.split(',') if p.strip()]
    else:
        # discover plates from DB (may take long)
        conn = collector.pg_connect()
        cur = conn.cursor()
        cur.execute("SET search_path = %s, public", (os.getenv('ETRAC_SCHEMA', 'e_track'),))
        conn.commit()
        plates = collector.get_all_plates(collector.requests.Session())
        conn.close()

    if not plates:
        LOG.warning('No plates to process')
        return

    conn = collector.pg_connect()
    # set schema
    cur = conn.cursor()
    cur.execute(collector.sql.SQL("SET search_path = {}, public").format(collector.sql.Identifier(os.getenv('ETRAC_SCHEMA', 'e_track'))))
    conn.commit()

    if not acquire_lock(conn):
        LOG.warning('Another backfill is running (lock unavailable). Exiting.')
        conn.close()
        return

    try:
        total_plates = len(plates)
        LOG.info('Starting backfill for %d plates from %s to %s', total_plates, start_date, end_date)
        for idx, p in enumerate(plates, 1):
            LOG.info('Processing plate %d/%d: %s', idx, total_plates, p)
            for d in daterange(start_date, end_date):
                try:
                    # attempt to fetch history and compute
                    LOG.debug('Fetching history for %s on %s', p, d)
                    try:
                        collector.fetch_terminal_history(collector.requests.Session(), conn, p, data=d.strftime('%d/%m/%Y'))
                    except Exception:
                        LOG.debug('fetch_terminal_history may have failed; proceeding to compute from DB')
                    n = collector.build_and_store_route_for_date(conn, p, d, session=collector.requests.Session())
                    LOG.info('Plate %s date %s -> %d points', p, d, n)
                except Exception:
                    LOG.exception('Failed for plate %s date %s', p, d)
                time.sleep(args.sleep)
    finally:
        release_lock(conn)
        conn.close()


if __name__ == '__main__':
    main()
