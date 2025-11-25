#!/usr/bin/env python3
"""Coletor simples para API eTrac e gravação em PostgreSQL.

Uso:
  - configurar variáveis de ambiente (veja `.env.example`)
  - executar `python collector.py --fetch-latest`

Este script implementa chamadas aos endpoints documentados e armazena
`terminals`, `positions` e `trips` no Postgres.
"""
import os
import argparse
import requests
import json
from datetime import datetime
import calendar
import psycopg2
import psycopg2.extras
from psycopg2 import sql
import re
from dotenv import load_dotenv
import logging
try:
    # when running as part of package
    from .http_retry import post_with_retries
except Exception:
    # when running as script from repository root
    from http_retry import post_with_retries

# configure logging
LOG_LEVEL = os.getenv('ETRAC_LOG_LEVEL', 'INFO').upper()
numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
logging.basicConfig(level=numeric_level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('e-track.collector')

API_BASE = os.getenv('ETRAC_API_BASE', 'https://api.etrac.com.br/monitoramento')
ETRAC_USER = os.getenv('ETRAC_USER')
ETRAC_KEY = os.getenv('ETRAC_KEY')

# Postgres connection (DSN or env)
PG_DSN = os.getenv('DATABASE_URL')
PG_HOST = os.getenv('PGHOST', 'localhost')
PG_PORT = os.getenv('PGPORT', '5432')
PG_DB = os.getenv('PGDATABASE')
PG_USER = os.getenv('PGUSER')
PG_PASSWORD = os.getenv('PGPASSWORD')


def pg_connect():
    logger.debug('Connecting to Postgres: host=%s port=%s dbname=%s user=%s', PG_HOST, PG_PORT, PG_DB, PG_USER)
    try:
        if PG_DSN:
            conn = psycopg2.connect(PG_DSN)
        else:
            missing = []
            if not PG_DB:
                missing.append('PGDATABASE')
            if not PG_USER:
                missing.append('PGUSER')
            if not PG_PASSWORD:
                missing.append('PGPASSWORD')
            if missing:
                logger.error('Missing Postgres configuration: %s', missing)
                raise RuntimeError(f'Missing Postgres configuration: {missing}')
            conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
        # quick sanity check
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        logger.info('Successfully connected to Postgres %s:%s/%s', PG_HOST, PG_PORT, PG_DB)
        return conn
    except Exception:
        logger.exception('Failed to connect to Postgres')
        raise


def ensure_tables(conn):
    cur = conn.cursor()
    # Ensure schema/tables are created. The schema.sql contains a CREATE SCHEMA and SET search_path.
    sql_text = open(os.path.join(os.path.dirname(__file__), 'schema.sql')).read()
    logger.info('Applying schema from schema.sql')
    cur.execute(sql_text)
    # create a unique index to avoid inserting duplicate positions for the same placa+timestamp+coords
    try:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS positions_unique_idx
            ON positions(placa, data_transmissao, latitude, longitude)
        """)
        logger.debug('Ensured unique index positions_unique_idx')
    except Exception:
        logger.exception('Failed to create unique index positions_unique_idx (continuing)')
        conn.rollback()
    conn.commit()
    logger.info('Schema and tables ensured')


def parse_date(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        # assume epoch seconds
        try:
            return datetime.fromtimestamp(int(s))
        except Exception:
            return None
    s = str(s).strip()
    if not s:
        return None
    fmts = [
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%d/%m/%Y %H:%M:%S',
        '%d/%m/%Y',
        '%d-%m-%Y',
        '%d-%m-%Y %H:%M:%S',
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except Exception:
            continue
    # fallback: try ISO parser via fromisoformat
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def auth():
    if not ETRAC_USER or not ETRAC_KEY:
        raise RuntimeError('Set ETRAC_USER and ETRAC_KEY in environment')
    return (ETRAC_USER, ETRAC_KEY)


def extract_list(resp_json):
    # eTrac responses vary; often the useful payload is in 'retorno' or 'terminal'/'posicoes'
    if isinstance(resp_json, list):
        return resp_json
    if not isinstance(resp_json, dict):
        return []
    for key in ('retorno', 'posicoes', 'positions', 'terminal', 'terminals', 'data'):
        if key in resp_json:
            v = resp_json[key]
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                # maybe wrapped
                for kk in ('posicoes', 'positions', 'retorno'):
                    if kk in v and isinstance(v[kk], list):
                        return v[kk]
                # if dict but not list, return single-item list
                return [v]
    # fallback: return any list value
    for v in resp_json.values():
        if isinstance(v, list):
            return v
    return []


def upsert_terminal(conn, item):
    placa = item.get('placa') or item.get('placaVeiculo') or item.get('plate')
    if not placa:
        return
    descricao = item.get('descricao')
    frota = item.get('frota')
    equipamento_serial = item.get('equipamento_serial')
    data_gravacao = parse_date(item.get('data_gravacao') or item.get('data_gravacao'))
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO terminals (placa, descricao, frota, equipamento_serial, data_gravacao, data)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (placa) DO UPDATE SET descricao = EXCLUDED.descricao,
                 frota = EXCLUDED.frota, equipamento_serial = EXCLUDED.equipamento_serial,
                 data_gravacao = EXCLUDED.data_gravacao, data = EXCLUDED.data, data_atualizacao = now()
            """,
            (placa, descricao, frota, equipamento_serial, data_gravacao, psycopg2.extras.Json(item)),
        )
        conn.commit()
        logger.debug('Upserted terminal %s', placa)
    except Exception:
        logger.exception('Failed upserting terminal %s', placa)
        conn.rollback()



def insert_position(conn, item):
    placa = item.get('placa')
    if not placa:
        return
    dt = parse_date(item.get('data_transmissao') or item.get('data_transmissao'))
    lat = None
    lon = None
    try:
        lat = float(item.get('latitude')) if item.get('latitude') not in (None, '') else None
    except Exception:
        lat = None
    try:
        lon = float(item.get('longitude')) if item.get('longitude') not in (None, '') else None
    except Exception:
        lon = None
    # sanitize numeric-like fields: velocidade may come as '0 km/h', bateria as '12.6 V', etc.
    def parse_number(val, integer=False):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return int(val) if integer else float(val)
        s = str(val).strip()
        if s == '':
            return None
        # extract first occurrence of number (handles commas and dots)
        import re
        m = re.search(r"[-+]?[0-9]{1,3}(?:[0-9\.,]*[0-9])?", s)
        if not m:
            return None
        num = m.group(0)
        # normalize comma as decimal if needed
        if num.count(',') == 1 and num.count('.') == 0:
            num = num.replace(',', '.')
        # remove thousands separators
        num = num.replace(',', '')
        try:
            return int(float(num)) if integer else float(num)
        except Exception:
            return None

    velocidade = parse_number(item.get('velocidade'), integer=True)
    ign = item.get('ignicao')
    odometro = parse_number(item.get('odometro'))
    odometro_can = parse_number(item.get('odometro_can'))
    horimetro = parse_number(item.get('horimetro'))
    bateria = parse_number(item.get('bateria'))
    logradouro = item.get('logradouro')
    equipamento_serial = item.get('equipamento_serial')
    data_gravacao = parse_date(item.get('data_gravacao'))
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO positions (placa, data_transmissao, latitude, longitude, logradouro, velocidade,
                ignicao, odometro, odometro_can, horimetro, bateria, equipamento_serial, data_gravacao, raw)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (placa, data_transmissao, latitude, longitude) DO NOTHING
            """,
            (
                placa, dt, lat, lon, logradouro, velocidade,
                (True if ign in (1, '1', True) else False if ign in (0, '0', False) else None),
                odometro, odometro_can, horimetro, bateria, equipamento_serial, data_gravacao, psycopg2.extras.Json(item)
            ),
        )
        conn.commit()
        logger.info('Inserted position for %s at %s', placa, dt)
    except Exception as e:
        # Log the error and the problematic item, but don't raise so processing continues
        logger.exception('Erro inserindo position for %s: %s', placa, e)
        try:
            logger.debug('item: %s', json.dumps(item, ensure_ascii=False))
        except Exception:
            logger.debug('item (repr): %s', repr(item))
        conn.rollback()


def fetch_latest_positions(session, conn):
    url = f"{API_BASE.rstrip('/')}/ultimas-posicoes"
    r = post_with_retries(session, url, auth=auth(), timeout=60)
    r.raise_for_status()
    j = r.json()
    items = extract_list(j)
    logger.info('Fetched %d items from %s', len(items), url)
    processed = 0
    for it in items:
        # cada item deve ser um terminal com campos descritos no manual
        upsert_terminal(conn, it)
        insert_position(conn, it)
        processed += 1
    logger.info('Processed %d positions from latest-positions', processed)


def fetch_last_position_for_plate(session, conn, placa):
    url = f"{API_BASE.rstrip('/')}/ultimaposicao"
    r = post_with_retries(session, url, auth=auth(), json={'placa': placa}, timeout=60)
    r.raise_for_status()
    j = r.json()
    items = extract_list(j)
    logger.info('Fetched %d items for plate %s from %s', len(items), placa, url)
    for it in items:
        upsert_terminal(conn, it)
        insert_position(conn, it)


def fetch_terminal_history(session, conn, placa, data=None, inicio=None, fim=None):
    # The eTrac API has slightly varying endpoint names across installations.
    # Try a set of likely endpoint paths and use the first that responds with 200.
    payload = {'placa': placa}
    if data:
        payload['data'] = data
    if inicio and fim:
        # API expects keys 'data_inicio' and 'data_fim' or full-day 'data'
        payload['data_inicio'] = inicio
        payload['data_fim'] = fim

    candidate_paths = [
        'ultimasposicoesterminal',
        'ultimas-posicoes-terminal',
        'ultimas-posicoes-terminal',
        'ultimasposicoesterminal',
        'historico-terminal',
        'historico-posicoes-terminal',
    ]
    last_exc = None
    for p in candidate_paths:
        url = f"{API_BASE.rstrip('/')}/{p}"
        try:
            r = post_with_retries(session, url, auth=auth(), json=payload, timeout=60)
        except Exception as e:
            last_exc = e
            continue
        # if endpoint not found, try next candidate
        if r.status_code == 404:
            last_exc = requests.exceptions.HTTPError(f'404 for {url}')
            continue
        try:
            r.raise_for_status()
        except Exception as e:
            last_exc = e
            # for other HTTP errors, stop and re-raise
            raise
        j = r.json()
        # response likely contains 'posicoes' list
        items = []
        if isinstance(j, dict) and 'posicoes' in j and isinstance(j['posicoes'], list):
            items = j['posicoes']
        else:
            items = extract_list(j)
        logger.info('Fetched %d history items for plate %s from %s', len(items), placa, url)
        processed = 0
        for it in items:
            # some installations return history items without a 'placa' field
            # ensure the item has the requested placa so upsert/insert work
            if not it.get('placa'):
                try:
                    it['placa'] = placa
                except Exception:
                    pass
            upsert_terminal(conn, it)
            insert_position(conn, it)
            processed += 1
        logger.info('Processed %d historical positions for %s from %s', processed, placa, url)
        # success: return after processing
        return

    # if we reach here, no candidate endpoint worked
    if last_exc:
        raise RuntimeError(f'Could not fetch terminal history: attempted endpoints {candidate_paths}; last error: {last_exc}')
    raise RuntimeError(f'Could not fetch terminal history: attempted endpoints {candidate_paths} but none succeeded')


def get_all_plates(session):
    """Return a list of plate strings from the latest-positions endpoint."""
    candidate_paths = [
        'ultimas-posicoes',
        'ultimasposicoes',
        'ultimas-posicoes',
        'ultimas-posicoes-frota',
        'ultimasposicoesfrota',
    ]
    plates = []
    last_exc = None
    for p in candidate_paths:
        url = f"{API_BASE.rstrip('/')}/{p}"
        try:
            r = post_with_retries(session, url, auth=auth(), timeout=60)
        except Exception as e:
            last_exc = e
            logger.debug('Request to %s failed: %s', url, e)
            continue
        if r.status_code == 404:
            logger.debug('Endpoint not found: %s', url)
            last_exc = requests.exceptions.HTTPError(f'404 for {url}')
            continue
        try:
            r.raise_for_status()
        except Exception as e:
            last_exc = e
            logger.warning('HTTP error for %s: %s', url, e)
            continue
        try:
            j = r.json()
        except Exception as e:
            logger.warning('Failed to decode JSON from %s: %s', url, e)
            last_exc = e
            continue
        items = extract_list(j)
        for it in items:
            pval = it.get('placa') or it.get('plate')
            if pval:
                plates.append(pval)
        if plates:
            logger.info('Discovered %d plates from %s', len(plates), url)
            return plates
    # none succeeded
    if last_exc:
        logger.warning('Could not discover plates via ultimas-posicoes variants; last error: %s', last_exc)
    else:
        logger.warning('Could not discover plates: no ultimas-posicoes endpoint responded')
    return []


def build_and_store_route_for_date(conn, placa, date_obj, session=None, min_points_for_route=3):
    """Aggregate positions for a given placa and date (datetime.date) and store into routes table.
    Returns number of points stored.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    start = datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, 0)
    last_day = calendar.monthrange(date_obj.year, date_obj.month)[1]
    end = datetime(date_obj.year, date_obj.month, last_day, 23, 59, 59)
    cur.execute(
        """SELECT data_transmissao, latitude, longitude, velocidade, raw
           FROM positions
           WHERE placa = %s AND data_transmissao BETWEEN %s AND %s
           ORDER BY data_transmissao ASC
        """,
        (placa, start, end),
    )
    rows = cur.fetchall()
    pts = []
    for r in rows:
        lat = r.get('latitude')
        lon = r.get('longitude')
        if lat is None or lon is None:
            continue
        try:
            latf = float(lat)
            lonf = float(lon)
        except Exception:
            continue
        ts = r.get('data_transmissao')
        ts_iso = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        # include textual address/location fields when available
        addr = r.get('logradouro') or r.get('endereco')
        pts.append({'lat': latf, 'lon': lonf, 'ts': ts_iso, 'vel': r.get('velocidade'), 'addr': addr})

    if not pts:
        # If we have no (or too few) positions, try to fetch terminal history from the API
        if session is not None:
            try:
                logger.info('Few/no positions for %s on %s — attempting fetch_terminal_history', placa, date_obj)
                # API expects date in DD/MM/YYYY for history endpoints
                date_str = date_obj.strftime('%d/%m/%Y')
                fetch_terminal_history(session, conn, placa, data=date_str)
                # re-query positions after attempting to fetch history
                cur.execute(
                    """SELECT data_transmissao, latitude, longitude, velocidade, raw
                       FROM positions
                       WHERE placa = %s AND data_transmissao BETWEEN %s AND %s
                       ORDER BY data_transmissao ASC
                    """,
                    (placa, start, end),
                )
                rows = cur.fetchall()
                pts = []
                for r in rows:
                    lat = r.get('latitude')
                    lon = r.get('longitude')
                    if lat is None or lon is None:
                        continue
                    try:
                        latf = float(lat)
                        lonf = float(lon)
                    except Exception:
                        continue
                    ts = r.get('data_transmissao')
                    ts_iso = ts.isoformat() if isinstance(ts, datetime) else str(ts)
                    pts.append({'lat': latf, 'lon': lonf, 'ts': ts_iso, 'vel': r.get('velocidade')})
            except Exception:
                logger.exception('History fetch failed for %s on %s', placa, date_obj)

        if not pts:
            logger.info('No positions found for %s on %s after history fetch', placa, date_obj)
            # attempt to extract trip endpoints as fallback (trips may have lat/lon and textual locations)
            try:
                cur.execute(
                    """SELECT latitude_inicio_conducao, longitude_inicio_conducao,
                               latitude_fim_conducao, longitude_fim_conducao
                       FROM trips
                       WHERE placa = %s AND data_inicio_conducao BETWEEN %s AND %s
                    """,
                    (placa, start, end),
                )
                trip_rows = cur.fetchall()
                for tr in trip_rows:
                    lat1 = tr.get('latitude_inicio_conducao')
                    lon1 = tr.get('longitude_inicio_conducao')
                    lat2 = tr.get('latitude_fim_conducao')
                    lon2 = tr.get('longitude_fim_conducao')
                    if lat1 and lon1:
                        try:
                            pts.append({'lat': float(lat1), 'lon': float(lon1), 'ts': start.isoformat(), 'vel': None, 'addr': tr.get('localizacao_inicio_conducao') or None})
                        except Exception:
                            pass
                    if lat2 and lon2:
                        try:
                            pts.append({'lat': float(lat2), 'lon': float(lon2), 'ts': end.isoformat(), 'vel': None, 'addr': tr.get('localizacao_fim_conducao') or None})
                        except Exception:
                            pass
            except Exception:
                logger.exception('Failed querying trips fallback for %s on %s', placa, date_obj)

        if not pts:
            return 0

    start_ts = pts[0]['ts']
    end_ts = pts[-1]['ts']
    point_count = len(pts)

    # If we have too few points, optionally skip storing or still store depending on threshold
    if point_count < min_points_for_route:
        logger.info('Route for %s on %s has only %d points (< %d)', placa, date_obj, point_count, min_points_for_route)
        # we still store the route (keeps generated flag), but caller may decide to ignore

    # insert or update routes table
    try:
        cur.execute(
            """INSERT INTO routes (placa, rota_date, points, start_ts, end_ts, point_count, raw)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (placa, rota_date) DO UPDATE SET
                 points = EXCLUDED.points,
                 start_ts = EXCLUDED.start_ts,
                 end_ts = EXCLUDED.end_ts,
                 point_count = EXCLUDED.point_count,
                 raw = EXCLUDED.raw,
                 created_at = now()
            """,
            (placa, date_obj, psycopg2.extras.Json(pts), start_ts, end_ts, point_count, psycopg2.extras.Json({'generated': True}))
        )
        conn.commit()
        logger.info('Stored route for %s on %s (%d points)', placa, date_obj, point_count)
        return point_count
    except Exception:
        logger.exception('Failed to store route for %s on %s', placa, date_obj)
        conn.rollback()
        return 0


def fetch_month_for_plate(session, conn, placa, year, month):
    # build start and end strings in format DD/MM/YYYY HH:MM:SS
    first_day = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    start_str = first_day.strftime('%d/%m/%Y 00:00:00')
    end_dt = datetime(year, month, last_day, 23, 59, 59)
    end_str = end_dt.strftime('%d/%m/%Y %H:%M:%S')
    print(f'Buscando histórico mensal para {placa}: {start_str} -> {end_str}')
    try:
        fetch_terminal_history(session, conn, placa, inicio=start_str, fim=end_str)
        return
    except Exception as e:
        print('Warning: terminal history endpoint failed, falling back to latest-posicoes polling:', e)

    # Fallback: try fetching from /ultimas-posicoes (and variants) and filter locally by date range.
    start_dt = datetime(year, month, 1, 0, 0, 0)
    last_day = calendar.monthrange(year, month)[1]
    end_dt = datetime(year, month, last_day, 23, 59, 59)

    candidate_paths = [
        'ultimas-posicoes',
        'ultimasposicoes',
        'ultimas-posicoes',
        'ultimas-posicoes-por-terminal',
    ]
    found = 0
    for p in candidate_paths:
        url = f"{API_BASE.rstrip('/')}/{p}"
        try:
            r = post_with_retries(session, url, auth=auth(), timeout=60)
        except Exception as e:
            print('Fallback: request failed for', url, e)
            continue
        if r.status_code == 404:
            print('Fallback: endpoint not found', url)
            continue
        try:
            r.raise_for_status()
        except Exception as e:
            print('Fallback: HTTP error for', url, e)
            continue
        j = r.json()
        items = extract_list(j)
        for it in items:
            # match placa
            p_placa = it.get('placa') or it.get('plate') or it.get('placaVeiculo')
            if not p_placa or str(p_placa).strip().upper() != str(placa).strip().upper():
                continue
            # parse timestamp
            dt = parse_date(it.get('data_transmissao') or it.get('data') or it.get('data_gravacao'))
            if not dt:
                continue
            if dt < start_dt or dt > end_dt:
                continue
            # insert
            upsert_terminal(conn, it)
            insert_position(conn, it)
            found += 1
        if found > 0:
            print(f'Fallback: found {found} positions for {placa} using {url}')
            return

    print('Fallback complete: no positions found for', placa)


def fetch_trips(session, conn, placa, data_str):
    url = f"{API_BASE.rstrip('/')}/resumoviagens"
    payload = {'placa': placa, 'data': data_str}
    r = post_with_retries(session, url, auth=auth(), json=payload, timeout=60)
    r.raise_for_status()
    j = r.json()
    items = extract_list(j)
    cur = conn.cursor()
    for it in items:
        # map known fields
        try:
            cur.execute(
                """INSERT INTO trips (placa, cliente, cliente_fantasia, data_inicio_conducao, data_fim_conducao,
                    latitude_inicio_conducao, longitude_inicio_conducao, latitude_fim_conducao, longitude_fim_conducao,
                    localizacao_inicio_conducao, localizacao_fim_conducao, odometro_inicio_conducao, odometro_fim_conducao,
                    duracao_conducao, distancia_conducao, condutor_nome, condutor_identificacao, raw)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    it.get('placa'), it.get('cliente'), it.get('cliente_fantasia'), parse_date(it.get('data_inicio_conducao')),
                    parse_date(it.get('data_fim_conducao')),
                    it.get('latitude_inicio_conducao'), it.get('longitude_inicio_conducao'),
                    it.get('latitude_fim_conducao'), it.get('longitude_fim_conducao'),
                    it.get('localizacao_inicio_conducao'), it.get('localizacao_fim_conducao'),
                    it.get('odometro_inicio_conducao'), it.get('odometro_fim_conducao'),
                    it.get('duracao_conducao'), it.get('distancia_conducao'), it.get('condutor_nome'), it.get('condutor_identificacao'), psycopg2.extras.Json(it)
                ),
            )
        except Exception as e:
            print('Erro inserindo viagem:', e, 'item:', it)
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Coletor eTrac -> Postgres')
    parser.add_argument('--fetch-latest', action='store_true')
    parser.add_argument('--fetch-plate', help='Buscar última posição da placa informada')
    parser.add_argument('--fetch-history', help='Buscar histórico de terminal (placa)')
    parser.add_argument('--date', help='Data (DD/MM/YYYY ou DD-MM-YYYY) para histórico ou viagens')
    parser.add_argument('--date-start', help='Data/hora início para histórico')
    parser.add_argument('--date-end', help='Data/hora fim para histórico')
    parser.add_argument('--fetch-trips', help='Buscar resumo de viagens para placa (requer --date)')
    parser.add_argument('--fetch-current-month-plate', help='Buscar histórico do mês atual para a placa informada')
    parser.add_argument('--fetch-current-month-all', action='store_true', help='Buscar histórico do mês atual para todas as placas')
    parser.add_argument('--compute-route-plate', help='Compute and store route for a plate for given date (use --date)')
    parser.add_argument('--compute-route-date', help='Date for route computation (DD/MM/YYYY or YYYY-mm-dd)', default=None)
    parser.add_argument('--compute-routes-current-day-all', action='store_true', help='Compute and store routes for current day for all plates')
    parser.add_argument('--plates-file', help='Path to file with one plate per line to operate on (overrides discovery)')
    parser.add_argument('--plates', help='Comma-separated list of plates to operate on (overrides discovery)')
    args = parser.parse_args()

    # load environment from repository root .env (do not override existing env vars)
    here = os.path.dirname(__file__)
    repo_root = os.path.abspath(os.path.join(here, '..'))
    load_dotenv(os.path.join(repo_root, '.env'), override=False)

    # Re-read Postgres-related env vars after loading .env so module-level
    # defaults (evaluated at import time) are updated with values from .env.
    global PG_DSN, PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD
    PG_DSN = os.getenv('DATABASE_URL') or PG_DSN
    PG_HOST = os.getenv('PGHOST', PG_HOST or 'localhost')
    PG_PORT = os.getenv('PGPORT', PG_PORT or '5432')
    PG_DB = os.getenv('PGDATABASE') or PG_DB
    PG_USER = os.getenv('PGUSER') or PG_USER
    PG_PASSWORD = os.getenv('PGPASSWORD') or PG_PASSWORD
    # Re-read e-Track API credentials as well so auth() sees .env values
    global ETRAC_USER, ETRAC_KEY
    ETRAC_USER = os.getenv('ETRAC_USER') or ETRAC_USER
    ETRAC_KEY = os.getenv('ETRAC_KEY') or ETRAC_KEY

    session = requests.Session()
    conn = pg_connect()

    # Apply schema search_path based on env or default to e_track
    schema = os.getenv('ETRAC_SCHEMA', 'e_track')
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', schema):
        raise RuntimeError('Invalid schema name in ETRAC_SCHEMA')
    cur = conn.cursor()
    # Use psycopg2.sql to safely compose identifier
    cur.execute(sql.SQL("SET search_path = {}, public").format(sql.Identifier(schema)))
    conn.commit()

    ensure_tables(conn)

    if args.fetch_latest:
        print('Buscando últimas posições da frota...')
        fetch_latest_positions(session, conn)
        print('Concluído fetch-latest')
    if args.fetch_plate:
        print('Buscando última posição para', args.fetch_plate)
        fetch_last_position_for_plate(session, conn, args.fetch_plate)
        print('Concluído fetch-plate')
    if args.fetch_history:
        print('Buscando histórico para', args.fetch_history)
        fetch_terminal_history(session, conn, args.fetch_history, data=args.date, inicio=args.date_start, fim=args.date_end)
        print('Concluído fetch-history')
    if args.fetch_trips:
        if not args.date:
            print('Para buscar trips informe --date')
        else:
            print('Buscando trips para', args.fetch_trips, 'data', args.date)
            fetch_trips(session, conn, args.fetch_trips, args.date)
            print('Concluído fetch-trips')
    if args.fetch_current_month_plate:
        placa = args.fetch_current_month_plate
        now = datetime.now()
        print(f'Buscando mês atual ({now.year}-{now.month}) para placa {placa}...')
        fetch_month_for_plate(session, conn, placa, now.year, now.month)
        print('Concluído fetch-current-month-plate')
    if args.compute_route_plate:
        placa = args.compute_route_plate
        # parse date argument if present, default to today
        if args.compute_route_date:
            d = parse_date(args.compute_route_date)
            if d is None:
                print('Invalid date for --compute-route-date')
            else:
                date_obj = d.date()
        else:
            date_obj = datetime.now().date()
        print(f'Computing route for {placa} on {date_obj}')
        n = build_and_store_route_for_date(conn, placa, date_obj, session=session)
        print(f'Points stored: {n}')
    if args.compute_routes_current_day_all:
        now = datetime.now()
        date_obj = now.date()
        # First, refresh latest positions from the API so new plates are discovered and stored
        try:
            logger.info('Refreshing latest positions from API before computing routes')
            fetch_latest_positions(session, conn)
        except Exception:
            logger.exception('Failed to refresh latest positions; will still attempt to compute routes from DB')

        # Allow overrides: --plates-file or --plates (comma-separated)
        plates = []
        if args.plates_file:
            try:
                with open(args.plates_file, 'r', encoding='utf-8') as fh:
                    plates = [line.strip() for line in fh if line.strip()]
                logger.info('Loaded %d plates from file %s', len(plates), args.plates_file)
            except Exception:
                logger.exception('Failed reading plates file %s', args.plates_file)
                plates = []
        elif args.plates:
            plates = [p.strip() for p in args.plates.split(',') if p.strip()]
            logger.info('Using %d plates from --plates', len(plates))
        else:
            # Prefer plates from DB (includes newly discovered ones from fetch_latest_positions)
            try:
                cur = conn.cursor()
                cur.execute("SELECT DISTINCT placa FROM positions WHERE placa IS NOT NULL")
                rows = cur.fetchall()
                plates = [r[0] for r in rows if r and r[0]]
                logger.info('Discovered %d plates from DB', len(plates))
            except Exception:
                logger.exception('Failed to fetch plates from DB; falling back to API discovery')
                plates = get_all_plates(session)

        if not plates:
            logger.warning('No plates to process for compute-routes-current-day-all')
        for p in plates:
            try:
                build_and_store_route_for_date(conn, p, date_obj, session=session)
            except Exception as e:
                logger.exception('Error computing route for %s: %s', p, e)
        print('Concluído compute-routes-current-day-all')
    if args.fetch_current_month_all:
        now = datetime.now()
        print(f'Buscando mês atual ({now.year}-{now.month}) para todas as placas...')
        plates = get_all_plates(session)
        for p in plates:
            try:
                fetch_month_for_plate(session, conn, p, now.year, now.month)
            except Exception as e:
                print('Erro ao buscar mês para', p, e)
        print('Concluído fetch-current-month-all')
    conn.close()


if __name__ == '__main__':
    main()
