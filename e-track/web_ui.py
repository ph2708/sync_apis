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
from datetime import datetime
import logging

# logging for the web UI
LOG_LEVEL = os.getenv('ETRAC_LOG_LEVEL', 'INFO').upper()
numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
logging.basicConfig(level=numeric_level, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('e-track.web_ui')

# load .env if present
here = os.path.dirname(__file__)
load_dotenv(os.path.join(here, '.env'))

API_RESOURCES = ['terminals', 'positions', 'trips']

PG_DSN = os.getenv('PG_DSN')
PG_HOST = os.getenv('PGHOST', 'localhost')
PG_PORT = os.getenv('PGPORT', '5432')
PG_DB = os.getenv('PGDATABASE')
PG_USER = os.getenv('PGUSER')
PG_PASSWORD = os.getenv('PGPASSWORD')
ETRAC_SCHEMA = os.getenv('ETRAC_SCHEMA', 'e_track')


def pg_connect():
    if PG_DSN:
        conn = psycopg2.connect(PG_DSN)
    else:
        if not (PG_DB and PG_USER and PG_PASSWORD):
            raise RuntimeError('Missing Postgres configuration: set PGDATABASE, PGUSER and PGPASSWORD (or PG_DSN)')
        conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    # set search_path to the configured schema so unqualified table names work
    cur = conn.cursor()
    cur.execute(sql.SQL("SET search_path = {}, public").format(sql.Identifier(ETRAC_SCHEMA)))
    conn.commit()
    return conn


app = Flask(__name__)


@app.route('/')
def index():
    links = ''.join([f"<li><a href='/db/{r}'>{r}</a></li>" for r in API_RESOURCES])
    html = f"""
    <html>
      <head><title>e-Track DB Viewer</title></head>
      <body>
        <h2>e-Track DB Viewer</h2>
        <p>Recursos disponíveis:</p>
        <ul>{links}</ul>
        <p>Use <code>?page=1&page_size=20</code> nos links para paginação.</p>
      </body>
    </html>
    """
    return html


def get_candidates(resource):
    if resource == 'terminals':
        return ['placa', 'descricao', 'frota', 'equipamento_serial', 'data_gravacao']
    if resource == 'positions':
        return ['id', 'placa', 'data_transmissao', 'latitude', 'longitude', 'velocidade', 'ignicao']
    if resource == 'trips':
        return ['id', 'placa', 'cliente', 'data_inicio_conducao', 'data_fim_conducao', 'distancia_conducao']
    return []


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
            if isinstance(v, datetime):
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
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    header_cells = ''.join(f"<th>{c}</th>" for c in cols)

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
            if isinstance(v, datetime):
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)


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

