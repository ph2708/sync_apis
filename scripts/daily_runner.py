#!/usr/bin/env python3
"""Runner para executar jobs diários para Auvo e e-Track.

Comportamento:
- carrega variáveis de ambiente (.env) se presente
- agenda execução diária (hora/minuto configuráveis via env)
- executa os comandos de sincronização para Auvo e e-Track em sequência

Configuração via ENV (opcionais):
- DAILY_RUN_HOUR (0-23)  default: 1
- DAILY_RUN_MINUTE (0-59) default: 5
- RUN_AUVO (0/1) default: 1
- RUN_ETRAC (0/1) default: 1
- AUVO_CMD default: python3 auvo/auvo_sync.py --db-wait 2
- ETRAC_CMD default: python3 e-track/collector.py --fetch-latest

Também suporta --once para executar imediatamente e sair (útil para testes).
"""
from __future__ import annotations

import os
import shlex
import subprocess
import logging
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
# Delay importing APScheduler until we actually schedule the recurring job so
# that `--once` can run without APScheduler installed (useful for minimal runs).
import psycopg2
import psycopg2.extras


load_dotenv()

LOG = logging.getLogger('daily-runner')
logging.basicConfig(level=os.getenv('DAILY_RUN_LOG_LEVEL', 'INFO').upper(),
                    format='%(asctime)s %(levelname)s %(name)s: %(message)s')


def run_command(cmd: str, cwd: Optional[str] = None) -> int:
    LOG.info('Executando: %s', cmd)
    try:
        args = shlex.split(cmd)
        r = subprocess.run(args, cwd=cwd or os.getcwd(), check=False)
        LOG.info('Comando %s finalizou com código %s', cmd, r.returncode)
        return r.returncode
    except Exception as e:
        LOG.exception('Falha executando %s: %s', cmd, e)
        return 2


def job_run_all():
    LOG.info('Iniciando execução diária de jobs')
    # ordem: Auvo, depois e-Track
    run_auvo = os.getenv('RUN_AUVO', '1') != '0'
    run_etrac = os.getenv('RUN_ETRAC', '1') != '0'

    auvo_cmd = os.getenv('AUVO_CMD', 'python3 auvo/auvo_sync.py --db-wait 2')
    etrac_cmd = os.getenv('ETRAC_CMD', 'python3 e-track/collector.py --fetch-latest')
    # command to compute routes after fetching positions
    etrac_routes_cmd = os.getenv('ETRAC_ROUTES_CMD', 'python3 e-track/collector.py --compute-routes-current-day-all')
    # trips fetching configuration (disabled by default)
    run_etrac_trips = os.getenv('RUN_ETRAC_TRIPS', '0') != '0'
    etrac_trips_cmd_tpl = os.getenv('ETRAC_TRIPS_CMD', 'python3 e-track/collector.py --fetch-trips {plate} --date {date}')
    etrac_trips_date = os.getenv('ETRAC_TRIPS_DATE')  # if None, we will default to yesterday when running
    etrac_trips_sleep = float(os.getenv('ETRAC_TRIPS_SLEEP', '0.3'))
    plates_file_env = os.getenv('PLATES_FILE') or os.getenv('ETRAC_PLATES_FILE')

    if run_auvo:
        rc = run_command(auvo_cmd)
        if rc != 0:
            LOG.warning('Auvo job retornou código %s', rc)

    if run_etrac:
        rc = run_command(etrac_cmd)
        if rc != 0:
            LOG.warning('e-Track job retornou código %s', rc)

        # optionally compute routes after fetching latest positions
        run_etrac_compute = os.getenv('RUN_ETRAC_COMPUTE', '1') != '0'
        if run_etrac_compute:
            rc2 = run_command(etrac_routes_cmd)
            if rc2 != 0:
                LOG.warning('e-Track compute-routes job retornou código %s', rc2)

        # optionally fetch trips (resumo de viagens) per plate
        if run_etrac_trips:
            LOG.info('RUN_ETRAC_TRIPS enabled — collecting trips for date=%s', etrac_trips_date or '(default=yesterday)')
            # determine date default (yesterday) if not provided
            if not etrac_trips_date:
                from datetime import datetime, timedelta
                etrac_trips_date = (datetime.now() - timedelta(days=1)).date().isoformat()

            # build list of plates: prefer PLATES_FILE if provided, else query DB
            plates = []
            if plates_file_env and os.path.isfile(plates_file_env):
                try:
                    with open(plates_file_env, 'r', encoding='utf-8') as fh:
                        plates = [l.strip() for l in fh if l.strip()]
                    LOG.info('Loaded %d plates from file %s', len(plates), plates_file_env)
                except Exception:
                    LOG.exception('Failed reading plates file %s', plates_file_env)

            if not plates:
                # query DB for distinct plates in positions
                try:
                    pg_host = os.getenv('PGHOST', 'localhost')
                    pg_port = int(os.getenv('PGPORT', '5432'))
                    pg_db = os.getenv('PGDATABASE')
                    pg_user = os.getenv('PGUSER')
                    pg_pass = os.getenv('PGPASSWORD')
                    if not (pg_db and pg_user and pg_pass):
                        LOG.error('PGDATABASE/PGUSER/PGPASSWORD not set — cannot query plates from DB')
                    else:
                        conn = psycopg2.connect(host=pg_host, port=pg_port, dbname=pg_db, user=pg_user, password=pg_pass)
                        cur = conn.cursor()
                        cur.execute("SELECT DISTINCT placa FROM e_track.positions WHERE placa IS NOT NULL")
                        rows = cur.fetchall()
                        plates = [r[0] for r in rows if r and r[0]]
                        conn.close()
                        LOG.info('Discovered %d plates from DB', len(plates))
                except Exception:
                    LOG.exception('Failed to query plates from Postgres')

            # iterate plates and run trips command for each
            for p in plates:
                cmd = etrac_trips_cmd_tpl.format(plate=p, date=etrac_trips_date)
                rc3 = run_command(cmd)
                if rc3 != 0:
                    LOG.warning('fetch-trips for %s returned %s', p, rc3)
                time.sleep(etrac_trips_sleep)

    LOG.info('Execução diária finalizada')


def schedule_and_run_once_if_needed():
    import argparse

    parser = argparse.ArgumentParser(description='Daily runner for Auvo and e-Track')
    parser.add_argument('--once', action='store_true', help='Executa os jobs uma vez e sai')
    args = parser.parse_args()

    if args.once:
        job_run_all()
        return

    # schedule daily
    hour = int(os.getenv('DAILY_RUN_HOUR', '1'))
    minute = int(os.getenv('DAILY_RUN_MINUTE', '5'))

    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ModuleNotFoundError:
        LOG.error('APScheduler não instalado. Para agendar jobs recorrentes instale as dependências:')
        LOG.error('  pip install -r requirements.txt')
        LOG.error('Ou rode o runner com --once para executar apenas uma vez.')
        return

    sched = BlockingScheduler()
    trigger = CronTrigger(hour=hour, minute=minute)
    sched.add_job(job_run_all, trigger=trigger, id='daily-run-all')

    LOG.info('Agendado job diário às %02d:%02d', hour, minute)
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        LOG.info('Scheduler encerrado')


if __name__ == '__main__':
    schedule_and_run_once_if_needed()
