#!/usr/bin/env python3
"""Write a sample plates file by discovering plates via collector.get_all_plates.

Usage:
  python e-track/write_plates_sample.py 10 plates_sample.txt
"""
import sys
import os
from pathlib import Path

here = os.path.dirname(__file__)
repo_root = os.path.abspath(os.path.join(here, '..'))
sys.path.insert(0, here)  # ensure we can import collector when run as `python e-track/...`

import collector


def main():
    if len(sys.argv) < 3:
        print('Usage: write_plates_sample.py <count> <out_file>')
        return
    try:
        count = int(sys.argv[1])
    except Exception:
        print('Invalid count')
        return
    out = sys.argv[2]

    session = collector.requests.Session()
    plates = collector.get_all_plates(session)
    if not plates:
        print('No plates discovered')
        return

    sample = plates[:count]
    out_path = Path(os.path.join(repo_root, out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', encoding='utf-8') as fh:
        for p in sample:
            fh.write(p + '\n')

    print(f'Wrote {len(sample)} plates to {out_path}')


if __name__ == '__main__':
    main()
