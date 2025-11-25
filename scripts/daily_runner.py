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

    if run_auvo:
        rc = run_command(auvo_cmd)
        if rc != 0:
            LOG.warning('Auvo job retornou código %s', rc)

    if run_etrac:
        rc = run_command(etrac_cmd)
        if rc != 0:
            LOG.warning('e-Track job retornou código %s', rc)

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
