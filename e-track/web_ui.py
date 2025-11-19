#!/usr/bin/env python3
"""Small Flask app to browse e-track Postgres data locally.

Routes:
 - /        : links to resources
 - /db/<resource>?page=1&page_size=20 : paginated list
 - /db/<resource>/<id> : full JSON view

Run: set DB env vars (or use .env) and run `python web_ui.py` or `FLASK_APP=web_ui.py flask run`.
"""
from flask import Flask, request, abort
import os
import json
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from html import escape
from dotenv import load_dotenv
from datetime import datetime, date
import logging
import os

# logging for the web UI
LOG_LEVEL = os.getenv('ETRAC_LOG_LEVEL', 'INFO').upper()
numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
logging.basicConfig(level=numeric_level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('e-track.web_ui')

# load .env if present
here = os.path.dirname(__file__)
# load .env from repository root if present (do not override existing env vars)
repo_root = os.path.abspath(os.path.join(here, '..'))
load_dotenv(os.path.join(repo_root, '.env'), override=False)

API_RESOURCES = ['terminals', 'positions', 'trips', 'routes']

PG_DSN = os.getenv('PG_DSN')
PG_HOST = os.getenv('PGHOST', 'localhost')
PG_PORT = os.getenv('PGPORT', '5432')
PG_DB = os.getenv('PGDATABASE')
PG_USER = os.getenv('PGUSER')
PG_PASSWORD = os.getenv('PGPASSWORD')
ETRAC_SCHEMA = os.getenv('ETRAC_SCHEMA', 'e_track')


app = Flask(__name__)


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


def get_candidates(resource):
    """Return preferred column order for `resource` to display in the UI.

    The function lists high-value columns first; existing columns are
    filtered later against the database table columns.
    """
    mapping = {
        'terminals': ['placa', 'descricao', 'frota', 'equipamento_serial', 'data_gravacao', 'data_atualizacao'],
        'positions': ['data_transmissao', 'latitude', 'longitude', 'velocidade', 'ignicao', 'logradouro', 'equipamento_serial', 'created_at'],
        'trips': ['placa', 'cliente', 'data_inicio_conducao', 'data_fim_conducao', 'distancia_conducao', 'condutor_nome', 'created_at'],
        'routes': ['placa', 'rota_date', 'point_count', 'start_ts', 'end_ts', 'created_at'],
    }
    return mapping.get(resource, ['id'])


@app.route('/')
def index():
    return f"<h1>e-track Data Browser</h1><ul>" + "".join(f"<li><a href='/db/{r}'>{r}</a></li>" for r in API_RESOURCES) + "</ul>"


@app.route('/db/<resource>')
def list_resource(resource):
    if resource not in API_RESOURCES:
        abort(404)
    try:
        page = max(1, int(request.args.get('page', '1')))
    except ValueError:
        page = 1
    try:
        page_size = min(200, max(1, int(request.args.get('page_size', '20'))))
    except ValueError:
        page_size = 20
    offset = (page - 1) * page_size

    conn = pg_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    candidates = get_candidates(resource)
    cols = []
    # check which columns exist in the table
    try:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s", (ETRAC_SCHEMA, resource))
        db_cols = {r['column_name'] for r in cur.fetchall()}
    except Exception:
        db_cols = set()

    for c in candidates:
        if c in db_cols:
            cols.append(c)

    # always include raw JSON if exists
    if 'raw' in db_cols:
        cols.append('raw')
    # assemble select
    select_cols = ', '.join(cols) if cols else '*'
    # use schema-qualified table name
    table_ident = sql.Identifier(ETRAC_SCHEMA, resource)
    # execute safe query
    q = sql.SQL("SELECT {fields} FROM {table} ORDER BY {order} DESC LIMIT %s OFFSET %s").format(
        fields=sql.SQL(select_cols), table=table_ident, order=sql.Identifier(cols[0] if cols else 'id')
    )
    cur.execute(q, (page_size, offset))
    rows = cur.fetchall()
    cur.execute(sql.SQL("SELECT COUNT(*) as cnt FROM {table}").format(table=table_ident))
    total = cur.fetchone()['cnt']
    conn.close()

    prev_link = f"/db/{resource}?page={page-1}&page_size={page_size}" if page > 1 else ''
    next_link = f"/db/{resource}?page={page+1}&page_size={page_size}" if offset + page_size < total else ''

    # helper to convert row values (datetimes) into JSON-serializable equivalents
    def row_to_jsonable(row):
        out = {}
        for k, v in dict(row).items():
            if isinstance(v, (datetime, date)):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out

    rows_html = []
    for r in rows:
        rid = escape(str(r.get('id') or r.get('placa') or ''))
        try:
            preview = escape(json.dumps(row_to_jsonable(r), ensure_ascii=False))[:300]
        except Exception:
            preview = escape(str(row_to_jsonable(r)))[:300]
        cells = [f"<td><a href='/db/{resource}/{rid}'>{rid}</a></td>"]
        for c in cols:
            val = r.get(c)
            if isinstance(val, datetime):
                sval = val.isoformat()
            else:
                sval = str(val) if val is not None else ''
            cells.append(f"<td>{escape(sval)}</td>")
        # for routes, add a link to the map view using rota_date
        if resource == 'routes':
            date_val = r.get('rota_date')
            if isinstance(date_val, (datetime, date)):
                date_str = date_val.isoformat()
            else:
                date_str = str(date_val) if date_val is not None else ''
            map_link = f"<a href='/map-route?plate={escape(str(r.get('placa') or ''))}&date={escape(date_str)}' target='_blank'>Mapa</a>"
            cells.append(f"<td>{map_link}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    header_cells = ''.join(f"<th>{c}</th>" for c in cols)
    if resource == 'routes':
        header_cells += '<th>Mapa</th>'

    html = f"""
    <html>
      <head>
        <title>{resource} — page {page}</title>
        <style>table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #ddd;padding:8px;vertical-align:top}}</style>
      </head>
      <body>
        <h2>{resource} (total: {total})</h2>
        <p>Page {page} — Page size {page_size}</p>
        <p>{f'<a href="{prev_link}">Prev</a>' if prev_link else ''} {f'<a href="{next_link}">Next</a>' if next_link else ''}</p>
        <table>
          <thead>
            <tr>
              <th>id/placa</th>
              {header_cells}
            </tr>
          </thead>
          <tbody>
            {''.join(rows_html)}
          </tbody>
        </table>
        <p><a href='/'>Voltar</a></p>
      </body>
    </html>
    """
    return html


@app.route('/db/<resource>/<row_id>')
def show_resource(resource, row_id):
    if resource not in API_RESOURCES:
        abort(404)
    conn = pg_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s", (ETRAC_SCHEMA, resource))
    db_cols = {r['column_name'] for r in cur.fetchall()}

    # select all columns for this row
    table_ident = sql.Identifier(ETRAC_SCHEMA, resource)
    cur.execute(sql.SQL("SELECT * FROM {table} WHERE (id::text = %s OR placa = %s) LIMIT 1").format(table=table_ident), (row_id, row_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        abort(404)
    # convert datetimes for JSON pretty output
    def row_to_jsonable(row):
        out = {}
        for k, v in dict(row).items():
            if isinstance(v, (datetime, date)):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out

    pretty = json.dumps(row_to_jsonable(row), ensure_ascii=False, indent=2)

    html = f"""
    <html>
      <head><title>{resource} {escape(str(row_id))}</title></head>
      <body>
        <h2>{resource} / {escape(str(row_id))}</h2>
        <h3>Raw JSON</h3>
        <pre style='white-space:pre-wrap'>{escape(pretty)}</pre>
        <p><a href='/db/{resource}'>Voltar</a></p>
      </body>
    </html>
    """
    return html





@app.route('/api/positions/<plate>')
def api_positions_plate(plate):
        """Return JSON list of positions for a plate filtered by date or start/end.
        Query params:
            - date=DD/MM/YYYY  -> full day
            - start=YYYY-mm-ddTHH:MM:SS or DD/MM/YYYY HH:MM:SS
            - end=... (same formats)
        """
        date = request.args.get('date')
        start = request.args.get('start')
        end = request.args.get('end')
        # parse date to start/end timestamps
        def parse_dt(s):
                if not s:
                        return None
                for fmt in ('%d/%m/%Y %H:%M:%S','%d/%m/%Y','%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S'):
                        try:
                                return datetime.strptime(s, fmt)
                        except Exception:
                                continue
                try:
                        return datetime.fromisoformat(s)
                except Exception:
                        return None

        if date and not (start or end):
                try:
                        d = datetime.strptime(date, '%d/%m/%Y')
                        start_dt = datetime(d.year, d.month, d.day, 0, 0, 0)
                        end_dt = datetime(d.year, d.month, d.day, 23, 59, 59)
                except Exception:
                        return {'error': 'invalid date format, use DD/MM/YYYY'}, 400
        else:
                start_dt = parse_dt(start) if start else None
                end_dt = parse_dt(end) if end else None

        conn = pg_connect()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        table_ident = sql.Identifier(ETRAC_SCHEMA, 'positions')
        params = [plate]
        where = sql.SQL('placa = %s')
        if start_dt and end_dt:
                where = sql.SQL('placa = %s AND data_transmissao BETWEEN %s AND %s')
                params = [plate, start_dt, end_dt]
        elif start_dt:
                where = sql.SQL('placa = %s AND data_transmissao >= %s')
                params = [plate, start_dt]
        elif end_dt:
                where = sql.SQL('placa = %s AND data_transmissao <= %s')
                params = [plate, end_dt]

        q = sql.SQL('SELECT placa, data_transmissao, latitude, longitude, velocidade, ignicao, raw FROM {table} WHERE {where} ORDER BY data_transmissao ASC').format(
                table=table_ident, where=where
        )
        cur.execute(q, tuple(params))
        rows = cur.fetchall()
        conn.close()
        # convert datetimes to isoformat
        out = []
        for r in rows:
                out.append({
                        'placa': r.get('placa'),
                        'data_transmissao': r.get('data_transmissao').isoformat() if r.get('data_transmissao') else None,
                        'latitude': r.get('latitude'),
                        'longitude': r.get('longitude'),
                        'velocidade': r.get('velocidade'),
                        'ignicao': r.get('ignicao'),
                        'raw': r.get('raw')
                })
        return {'positions': out}


@app.route('/api/routes/<plate>')
def api_routes_plate(plate):
    """Return stored routes for a plate. Query params:
        - date=DD/MM/YYYY or YYYY-mm-dd -> return single route points
        - no date -> return available rota_date list for plate
    """
    date = request.args.get('date')
    # parse simple date formats
    def parse_date_str(s):
        if not s:
            return None
        for fmt in ('%d/%m/%Y','%Y-%m-%d'):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                continue
        try:
            return datetime.fromisoformat(s).date()
        except Exception:
            return None

    conn = pg_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    table_ident = sql.Identifier(ETRAC_SCHEMA, 'routes')
    if date:
        d = parse_date_str(date)
        if not d:
            conn.close()
            return {'error': 'invalid date format, use DD/MM/YYYY or YYYY-mm-dd'}, 400
        cur.execute(sql.SQL('SELECT points, point_count, start_ts, end_ts FROM {table} WHERE placa = %s AND rota_date = %s LIMIT 1').format(table=table_ident), (plate, d))
        row = cur.fetchone()
        # if route missing or sparse, attempt to refresh by calling collector (fetch history + compute route)
        MIN_POINTS = 3
        if (not row) or (row.get('point_count') is None) or (row.get('point_count') < MIN_POINTS):
            # try to run collector to fetch history and recompute route for this plate/date
            try:
                # detect python executable in repo venv (WSL/linux style), fallback to system python
                python_exe = os.path.join(repo_root, '.venv', 'bin', 'python')
                if not os.path.exists(python_exe):
                    python_exe = os.path.join(repo_root, '.venv', 'Scripts', 'python.exe')
                if not os.path.exists(python_exe):
                    python_exe = os.environ.get('PYTHON_EXECUTABLE') or 'python3'

                date_str = d.strftime('%d/%m/%Y')
                fetch_cmd = [python_exe, os.path.join(repo_root, 'e-track', 'collector.py'), '--fetch-history', plate, '--date', date_str]
                compute_cmd = [python_exe, os.path.join(repo_root, 'e-track', 'collector.py'), '--compute-route-plate', plate, '--compute-route-date', date_str]
                logger.info('Attempting on-demand refresh for route %s %s', plate, date_str)
                # run fetch history then compute route (blocking calls)
                subprocess.run(fetch_cmd, cwd=repo_root, timeout=120)
                subprocess.run(compute_cmd, cwd=repo_root, timeout=120)
                # re-query the route
                cur.execute(sql.SQL('SELECT points, point_count, start_ts, end_ts FROM {table} WHERE placa = %s AND rota_date = %s LIMIT 1').format(table=table_ident), (plate, d))
                row = cur.fetchone()
            except Exception:
                logger.exception('On-demand route refresh failed for %s %s', plate, d)

        conn.close()
        if not row:
            return {'route': None}
        return {'route': row.get('points'), 'point_count': row.get('point_count'), 'start_ts': row.get('start_ts').isoformat() if row.get('start_ts') else None, 'end_ts': row.get('end_ts').isoformat() if row.get('end_ts') else None}
    # list available rota_dates for plate
    cur.execute(sql.SQL('SELECT rota_date, point_count, created_at FROM {table} WHERE placa = %s ORDER BY rota_date DESC LIMIT 100').format(table=table_ident), (plate,))
    rows = cur.fetchall()
    conn.close()
    out = [{'rota_date': r.get('rota_date').isoformat() if r.get('rota_date') else None, 'point_count': r.get('point_count'), 'created_at': r.get('created_at').isoformat() if r.get('created_at') else None} for r in rows]
    return {'routes': out}


@app.route('/map')
def map_view():
    plate = request.args.get('plate', '')
    date = request.args.get('date', '')

    # prepare JSON-encoded values to safely embed into JS
    plate_json = json.dumps(plate)
    date_json = json.dumps(date)

    # simple page with Leaflet map that fetches /api/positions/<plate>?date=...
    template = """
        <!doctype html>
        <html>
            <head>
                <meta charset="utf-8" />
                <title>e-Track Map</title>
                <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
                <style>#map{height:90vh;}</style>
            </head>
            <body>
                <h3>Map — placa: <b>%%PLATE_ESC%%</b> date: <b>%%DATE_ESC%%</b></h3>
                <div id="map"></div>
                <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
                <script>
                const plate = %%PLATE_JSON%%;
                const date = %%DATE_JSON%%;
                const map = L.map('map').setView([-23.55, -46.63], 12);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19}).addTo(map);
                if (!plate) {
                    alert('Informe ?plate=PLACA&date=DD/MM/YYYY');
                } else {
                    const url = '/api/positions/' + encodeURIComponent(plate) + '?date=' + encodeURIComponent(date);
                    fetch(url).then(r=>r.json()).then(j=>{
                        const pts = j.positions.filter(p=>p.latitude && p.longitude).map(p=>[parseFloat(p.latitude), parseFloat(p.longitude)]);
                        if (pts.length===0) { alert('Nenhuma posição encontrada para a placa/data'); return; }
                        const poly = L.polyline(pts, {color:'blue'}).addTo(map);
                        map.fitBounds(poly.getBounds());
                        // start and end markers
                        L.circleMarker(pts[0], {color:'green'}).addTo(map).bindPopup('Start');
                        L.circleMarker(pts[pts.length-1], {color:'red'}).addTo(map).bindPopup('End');
                        // add popup on each point with time/speed
                        j.positions.forEach(p=>{
                            if (p.latitude && p.longitude) {
                                const m = L.circleMarker([parseFloat(p.latitude), parseFloat(p.longitude)], {radius:4}).addTo(map);
                                m.bindPopup(p.data_transmissao + '<br>vel: ' + p.velocidade);
                            }
                        });
                    }).catch(err=>{ alert('Erro carregando posições: '+err); });
                }
                </script>
            </body>
        </html>
        """
    # inject the escaped/plain values into the template to avoid f-string brace parsing issues
    html = template.replace('%%PLATE_ESC%%', escape(plate))\
                   .replace('%%DATE_ESC%%', escape(date))\
                   .replace('%%PLATE_JSON%%', plate_json)\
                   .replace('%%DATE_JSON%%', date_json)
    return html



@app.route('/map-route')
def map_route_view():
    plate = request.args.get('plate', '')
    date = request.args.get('date', '')

    plate_json = json.dumps(plate)
    date_json = json.dumps(date)

    template = """
        <!doctype html>
        <html>
            <head>
                <meta charset="utf-8" />
                <title>e-Track Route Map</title>
                <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
                <style>#map{height:90vh;}</style>
            </head>
            <body>
                <h3>Route Map — placa: <b>%%PLATE_ESC%%</b> date: <b>%%DATE_ESC%%</b></h3>
                <div id="map"></div>
                <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
                <script>
                const plate = %%PLATE_JSON%%;
                const date = %%DATE_JSON%%;
                const map = L.map('map').setView([-23.55, -46.63], 12);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 19}).addTo(map);
                if (!plate || !date) {
                    alert('Informe ?plate=PLACA&date=DD/MM/YYYY');
                } else {
                    const url = '/api/routes/' + encodeURIComponent(plate) + '?date=' + encodeURIComponent(date);
                    fetch(url).then(r=>r.json()).then(j=>{
                        const route = j.route;
                        if (!route || route.length===0) { alert('Nenhuma rota encontrada para a placa/data'); return; }
                        const pts = route.filter(p=>p.lat && p.lon).map(p=>[parseFloat(p.lat), parseFloat(p.lon)]);
                        if (pts.length===0) { alert('Nenhuma posição válida na rota'); return; }
                        const poly = L.polyline(pts, {color:'red'}).addTo(map);
                        map.fitBounds(poly.getBounds());
                        // start and end markers with popups including timestamp, speed and address when available
                        const first = route.find(p=>p.lat && p.lon);
                        const last = [...route].reverse().find(p=>p.lat && p.lon);
                        if (first) {
                            L.circleMarker([parseFloat(first.lat), parseFloat(first.lon)], {color:'green'}).addTo(map).bindPopup('Start: ' + first.ts + (first.vel? '<br>vel: '+first.vel:'' ) + (first.addr? '<br>'+first.addr:''));
                        }
                        if (last) {
                            L.circleMarker([parseFloat(last.lat), parseFloat(last.lon)], {color:'red'}).addTo(map).bindPopup('End: ' + last.ts + (last.vel? '<br>vel: '+last.vel:'' ) + (last.addr? '<br>'+last.addr:''));
                        }
                        // markers for each point with popup (addr + ts + vel)
                        route.forEach(p=>{
                            if (p.lat && p.lon) {
                                const m = L.circleMarker([parseFloat(p.lat), parseFloat(p.lon)], {radius:4}).addTo(map);
                                const popup = (p.ts || '') + (p.vel !== undefined && p.vel !== null ? '<br>vel: '+p.vel : '') + (p.addr? '<br>'+p.addr : '');
                                m.bindPopup(popup);
                            }
                        });
                    }).catch(err=>{ alert('Erro carregando rota: '+err); });
                }
                </script>
            </body>
        </html>
        """
    html = template.replace('%%PLATE_ESC%%', escape(plate)).replace('%%DATE_ESC%%', escape(date)).replace('%%PLATE_JSON%%', plate_json).replace('%%DATE_JSON%%', date_json)
    return html


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

