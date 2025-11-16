#!/usr/bin/env python3
import os
import time
import requests
import json
import calendar
import argparse
import uuid
from datetime import datetime

import psycopg2
import psycopg2.extras

API_BASE = os.getenv('AUVO_API_BASE', 'https://api.auvo.com.br/v2')
API_KEY = os.getenv('AUVO_API_KEY')
API_TOKEN = os.getenv('AUVO_API_TOKEN')
PAGE_SIZE = int(os.getenv('AUVO_PAGE_SIZE', '100'))

# Postgres connection (either DSN or individual vars)
# Support both generic PG_* env names and AUVO-prefixed names for backwards compatibility
PG_DSN = os.getenv('PG_DSN') or os.getenv('AUVO_PG_DSN')
PG_HOST = os.getenv('PGHOST') or os.getenv('AUVO_PG_HOST', 'localhost')
PG_PORT = os.getenv('PGPORT') or os.getenv('AUVO_PG_PORT', '5432')
# Note: avoid hardcoding DB name/user/password here. Require them from env or a DSN.
PG_DB = os.getenv('PGDATABASE') or os.getenv('AUVO_PG_DB')
PG_USER = os.getenv('PGUSER') or os.getenv('AUVO_PG_USER')
PG_PASSWORD = os.getenv('PGPASSWORD') or os.getenv('AUVO_PG_PASSWORD')


def get_auth_token():
    url = f"{API_BASE.rstrip('/')}/login/"
    if not API_KEY or not API_TOKEN:
        raise RuntimeError('Faltando credenciais: defina AUVO_API_KEY e AUVO_API_TOKEN no ambiente ou em .env')
    params = {'apiKey': API_KEY, 'apiToken': API_TOKEN}
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        j = r.json()
        for k in ('token', 'Token', 'authorizationToken', 'AuthorizationToken', 'authToken', 'authorization', 'result'):
            if k in j:
                v = j[k]
                if isinstance(v, dict) and 'token' in v:
                    return v['token']
                if isinstance(v, str):
                    return v
        def find_token(obj):
            if isinstance(obj, dict):
                for kk, vv in obj.items():
                    if kk.lower().endswith('token') and isinstance(vv, str):
                        return vv
                    res = find_token(vv)
                    if res:
                        return res
            elif isinstance(obj, list):
                for item in obj:
                    res = find_token(item)
                    if res:
                        return res
            return None
        res = find_token(j)
        if res:
            return res
        print('Aviso: token não encontrado explicitamente na resposta de /login; usando resposta completa como token.')
        return json.dumps(j)
    except Exception as e:
        print('Erro ao autenticar:', e)
        raise


def build_headers(token):
    return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def extract_items(resp_json):
    # Normalize various Auvo response wrappers and return the actual list of items.
    if isinstance(resp_json, list):
        return resp_json
    if not isinstance(resp_json, dict):
        return []

    # Common top-level wrappers we might see
    #  - { "result": { "entityList": [ ... ], "pagedSearchReturnData": {...} } }
    #  - { "result": [ ... ] }
    #  - { "data": [ ... ] }
    for key in ('result', 'data', 'items', 'results', 'rows'):
        if key in resp_json:
            val = resp_json[key]
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                # common inner list keys used by Auvo
                for inner in ('entityList', 'result', 'data', 'items', 'rows', 'results'):
                    if inner in val and isinstance(val[inner], list):
                        return val[inner]
                # fallback: return first list value found inside this dict
                for v in val.values():
                    if isinstance(v, list):
                        return v

    # If no wrapper keys matched, search any dict value that's a list and return it
    for v in resp_json.values():
        if isinstance(v, list):
            return v

    return []


def fetch_list(session, token, endpoint, param_filter=None):
    headers = build_headers(token)
    page = 1
    all_items = []
    max_retries_5xx = 5
    while True:
        params = {}
        path = endpoint if endpoint.endswith('/') else f"{endpoint}/"
        if param_filter is not None:
            params['paramFilter'] = json.dumps(param_filter, ensure_ascii=False)
        params['page'] = page
        params['pageSize'] = PAGE_SIZE
        params['order'] = 'asc'
        params['selectfields'] = ''
        url = f"{API_BASE.rstrip('/')}{path}"
        r = session.get(url, headers=headers, params=params, timeout=60)
        # handle rate limiting
        if r.status_code == 403:
            print('Rate limit atingido. Aguardando 5s...')
            time.sleep(5)
            continue
        # handle server errors with retries/backoff
        if 500 <= r.status_code < 600:
            backoff = 1
            retries = 0
            while retries < max_retries_5xx and 500 <= r.status_code < 600:
                print(f'Server error {r.status_code} ao acessar {url}. Retry {retries+1}/{max_retries_5xx} em {backoff}s')
                time.sleep(backoff)
                backoff *= 2
                retries += 1
                r = session.get(url, headers=headers, params=params, timeout=60)
            if 500 <= r.status_code < 600:
                # give up for this resource/page
                r.raise_for_status()
        try:
            r.raise_for_status()
        except requests.HTTPError as he:
            # If a provided filter returns 400, try a minimal alternative
            if r.status_code == 400 and param_filter is not None:
                try_alt_filter = {'externalId': ''}
                print('Filtro fornecido retornou 400; tentando filtro alternativo:', try_alt_filter)
                params_alt = {k: v for k, v in params.items()}
                params_alt['paramFilter'] = json.dumps(try_alt_filter, ensure_ascii=False)
                r3 = session.get(url, headers=headers, params=params_alt, timeout=60)
                if r3.status_code == 403:
                    time.sleep(5)
                    continue
                r3.raise_for_status()
                j = r3.json()
                items = extract_items(j)
                if not items:
                    break
                all_items.extend(items)
                if len(items) < PAGE_SIZE:
                    break
                page += 1
                time.sleep(0.2)
                continue
            raise
        j = r.json()
        items = extract_items(j)
        if not items:
            break
        all_items.extend(items)
        if len(items) < PAGE_SIZE:
            break
        page += 1
        time.sleep(0.2)
    return all_items


def pg_connect():
    if PG_DSN:
        return psycopg2.connect(PG_DSN)
    # Require explicit DB connection values when DSN is not provided
    missing = []
    if not PG_DB:
        missing.append('PGDATABASE')
    if not PG_USER:
        missing.append('PGUSER')
    if not PG_PASSWORD:
        missing.append('PGPASSWORD')
    if missing:
        raise RuntimeError(f'Missing Postgres configuration: set PG_DSN or the env vars: {", ".join(missing)}')
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)


def ensure_tables(conn):
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            data JSONB,
            fetched_at TIMESTAMP DEFAULT now(),
            name TEXT,
            login TEXT,
            email TEXT,
            user_id BIGINT,
            base_lat DOUBLE PRECISION,
            base_lon DOUBLE PRECISION
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            data JSONB,
            fetched_at TIMESTAMP DEFAULT now(),
            task_id BIGINT,
            task_date TIMESTAMP WITH TIME ZONE,
            customer_id BIGINT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            task_status INTEGER,
            user_from BIGINT,
            user_to BIGINT,
            external_id TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            data JSONB,
            fetched_at TIMESTAMP DEFAULT now(),
            customer_id BIGINT,
            external_id TEXT,
            customer_name TEXT,
            address TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION
        )
        """
    )
    conn.commit()


def get_pk_from_item(item):
    if not isinstance(item, dict):
        return None
    for key in ('id', 'Id', 'userId', 'customerId', 'taskId', 'gpsId', 'GpsId', 'externalId'):
        if key in item and item[key] is not None:
            return str(item[key])
    return None


def extract_normalized(table, item):
    # Return a dict of normalized fields for the given table
    if not isinstance(item, dict):
        return {}
    def sget(keys):
        for k in keys:
            if k in item and item[k] not in (None, ''):
                return item[k]
        return None

    if table == 'users':
        base = item.get('BasePoint') or item.get('basePoint') or {}
        return {
            'name': sget(['name', 'Name']),
            'login': sget(['login']),
            'email': sget(['email']),
            'user_id': sget(['userId', 'userID', 'user_id']),
            'base_lat': base.get('latitude') if isinstance(base, dict) else None,
            'base_lon': base.get('longitude') if isinstance(base, dict) else None,
        }
    if table == 'tasks':
        return {
            'task_id': sget(['taskID', 'taskId', 'id']),
            'task_date': sget(['taskDate', 'dateLastUpdate']),
            'customer_id': sget(['customerId']),
            'latitude': sget(['latitude']),
            'longitude': sget(['longitude']),
            'task_status': sget(['taskStatus']),
            'user_from': sget(['idUserFrom', 'userIdFrom']),
            'user_to': sget(['idUserTo', 'userIdTo']),
            'external_id': sget(['externalId']),
        }
    if table == 'customers':
        base = item.get('BasePoint') or item.get('basePoint') or {}
        return {
            'customer_id': sget(['customerId', 'id']),
            'external_id': sget(['externalId']),
            'customer_name': sget(['name', 'Name']),
            'address': sget(['address']),
            'latitude': base.get('latitude') if isinstance(base, dict) else sget(['latitude']),
            'longitude': base.get('longitude') if isinstance(base, dict) else sget(['longitude']),
        }
    return {}


def upsert(conn, table, item):
    pk = get_pk_from_item(item)
    if not pk:
        pk = str(uuid.uuid4())
    cur = conn.cursor()
    # use psycopg2 Json adapter so JSONB is stored correctly
    norm = extract_normalized(table, item)
    # Build upsert with normalized columns included when available
    cols = ['id', 'data']
    vals = [pk, psycopg2.extras.Json(item)]
    updates = ['data = EXCLUDED.data', 'fetched_at = now()']
    for k, v in norm.items():
        if v is not None:
            cols.append(k)
            vals.append(v)
            updates.append(f"{k} = EXCLUDED.{k}")

    cols_sql = ', '.join(cols) + ', fetched_at'
    placeholders = ', '.join(['%s'] * len(vals)) + ', now()'
    update_sql = ', '.join(updates)
    sql = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders}) ON CONFLICT (id) DO UPDATE SET {update_sql}"
    cur.execute(sql, tuple(vals))
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Sincroniza recursos Auvo para um banco PostgreSQL')
    parser.add_argument('--pg-dsn', default=None, help='Postgres DSN (overrides other PG env vars)')
    parser.add_argument('--db-wait', type=int, default=5, help='Segundos para aguardar o banco ficar disponível')
    parser.add_argument('--resources', nargs='*', default=['users', 'tasks', 'customers'], help='Recursos a sincronizar')
    parser.add_argument('--page-size', type=int, default=None)
    args = parser.parse_args()

    global PAGE_SIZE, PG_DSN
    if args.page_size is not None:
        PAGE_SIZE = args.page_size
    if args.pg_dsn:
        PG_DSN = args.pg_dsn

    session = requests.Session()
    token = get_auth_token()
    print('Token obtido (início):', str(token)[:20])

    # connect to Postgres, retry a few times while container starts
    conn = None
    for i in range(10):
        try:
            conn = pg_connect()
            break
        except Exception as e:
            print(f'Aguardando Postgres ({i+1}/10): {e}')
            time.sleep(args.db_wait)
    if conn is None:
        print('Não foi possível conectar ao Postgres. Abortando.')
        return

    ensure_tables(conn)

    for res in args.resources:
        print('Buscando', res)
        try:
            # By default, if resource is 'tasks' we fetch the current month only (Auvo often requires paramFilter)
            filter_obj = None
            if res.lower() == 'tasks':
                # current month range using API's expected keys: StartDate / EndDate
                now = datetime.utcnow()
                year = now.year
                month = now.month
                first_day = datetime(year, month, 1).strftime('%Y-%m-%dT00:00:00')
                last_day = datetime(year, month, calendar.monthrange(year, month)[1]).strftime('%Y-%m-%dT23:59:59')
                filter_obj = {'StartDate': first_day, 'EndDate': last_day}
                print(f'Aplicando filtro de mês atual para tasks: {filter_obj}')
            items = fetch_list(session, token, f"/{res}", param_filter=filter_obj)
        except requests.HTTPError as e:
            print(f"Falha ao buscar {res}: {e}. Pulando {res}.")
            continue
        except Exception as e:
            print(f"Erro inesperado ao buscar {res}: {e}. Pulando {res}.")
            continue
        print(f"-> {len(items)} {res} obtidos.")
        for it in items:
            upsert(conn, res, it)
    conn.close()
    print('Concluído.')


if __name__ == '__main__':
    main()
