#!/usr/bin/env python3
"""Summarize backfill results for given plates and date range.

Usage:
  python e-track/summarize_backfill.py --plates-file plates_sample.txt --date-start 2025-11-10 --date-end 2025-11-16
"""
import os
import argparse
from datetime import datetime
from pathlib import Path

here = os.path.dirname(__file__)
repo_root = os.path.abspath(os.path.join(here, '..'))
import sys
sys.path.insert(0, here)

import collector


def load_plates(path):
    p = Path(path)
    if not p.exists():
        raise SystemExit(f'Plates file not found: {path}')
    return [l.strip() for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plates-file', required=True)
    parser.add_argument('--date-start', required=True)
    parser.add_argument('--date-end', required=True)
    args = parser.parse_args()

    plates = load_plates(os.path.join(repo_root, args.plates_file))
    try:
        ds = datetime.fromisoformat(args.date_start).date()
        de = datetime.fromisoformat(args.date_end).date()
    except Exception:
        raise SystemExit('Invalid date format; use YYYY-MM-DD')

    conn = collector.pg_connect()
    cur = conn.cursor()
    schema = os.getenv('ETRAC_SCHEMA', 'e_track')
    cur.execute(collector.sql.SQL("SET search_path = {}, public").format(collector.sql.Identifier(schema)))
    conn.commit()

    total_routes = 0
    per_plate = {}
    for p in plates:
        cur.execute(
            "SELECT rota_date, point_count FROM routes WHERE placa = %s AND rota_date >= %s AND rota_date <= %s ORDER BY rota_date",
            (p, ds, de),
        )
        rows = cur.fetchall()
        if not rows:
            per_plate[p] = []
        else:
            per_plate[p] = [{'rota_date': r[0].isoformat(), 'point_count': r[1]} for r in rows]
            total_routes += len(rows)

    print('Backfill summary')
    print('Date range:', ds, '->', de)
    print('Plates:', len(plates))
    print('Total routes found:', total_routes)
    print('---')
    for p, routes in per_plate.items():
        if not routes:
            print(f'{p}: no routes stored in range')
        else:
            print(f"{p}: {len(routes)} routes")
            for r in routes:
                print(f"  - {r['rota_date']} : {r['point_count']} points")

    conn.close()


if __name__ == '__main__':
    main()
