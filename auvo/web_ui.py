#!/usr/bin/env python3
"""Small Flask app to browse Postgres-synced Auvo data locally.

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
from html import escape

API_RESOURCES = ['users', 'tasks', 'customers']

PG_DSN = os.getenv('PG_DSN') or os.getenv('AUVO_PG_DSN')
PG_HOST = os.getenv('PGHOST') or os.getenv('AUVO_PG_HOST', 'localhost')
PG_PORT = os.getenv('PGPORT') or os.getenv('AUVO_PG_PORT', '5432')
PG_DB = os.getenv('PGDATABASE') or os.getenv('AUVO_PG_DB', 'auvo')
PG_USER = os.getenv('PGUSER') or os.getenv('AUVO_PG_USER', 'auvo')
PG_PASSWORD = os.getenv('PGPASSWORD') or os.getenv('AUVO_PG_PASSWORD', 'auvo_pass')


def pg_connect():
    if PG_DSN:
        conn = psycopg2.connect(PG_DSN)
    else:
        conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    # Ensure we use the project schema `auvo` (fall back to public)
    try:
        cur = conn.cursor()
        cur.execute("CREATE SCHEMA IF NOT EXISTS auvo")
        cur.execute("SET search_path TO auvo, public")
        conn.commit()
    except Exception:
        # If setting search_path fails, return the connection anyway and let callers handle errors
        pass
    return conn


app = Flask(__name__)


@app.route('/')
def index():
    links = ''.join([f"<li><a href='/db/{r}'>{r}</a></li>" for r in API_RESOURCES])
    html = f"""
    <html>
      <head><title>Auvo DB Viewer</title></head>
      <body>
        <h2>Auvo DB Viewer</h2>
        <p>Recursos disponíveis:</p>
        <ul>{links}</ul>
        <p>Use <code>?page=1&page_size=20</code> nos links para paginação.</p>
      </body>
    </html>
    """
    return html


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

    # Decide which normalized columns to include in the listing (if they exist)
    candidates = {
      'users': ['name', 'login', 'email', 'user_id', 'base_lat', 'base_lon'],
      'tasks': ['task_id', 'task_date', 'customer_id', 'latitude', 'longitude', 'task_status', 'user_from', 'user_to', 'external_id'],
      'customers': ['customer_id', 'customer_name', 'address', 'latitude', 'longitude', 'external_id'],
    }
    cols = ['id', 'fetched_at']
    existing_cols = []
    try:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (resource,))
        db_cols = {r['column_name'] for r in cur.fetchall()}

        for c in candidates.get(resource, []):
            if c in db_cols:
                cols.append(c)
                existing_cols.append(c)

        # always include `data` as preview
        cols.append('data')

        select_sql = ', '.join(cols)
        cur.execute(f"SELECT {select_sql} FROM {resource} ORDER BY fetched_at DESC LIMIT %s OFFSET %s", (page_size, offset))
        rows = cur.fetchall()
        cur.execute(f"SELECT COUNT(*) as cnt FROM {resource}")
        total = cur.fetchone()['cnt']
    except Exception as e:
        msg = str(e)
        if 'does not exist' in msg or 'UndefinedTable' in msg or isinstance(e, getattr(psycopg2.errors, 'UndefinedTable', Exception)):
            html = f"""
            <html><body>
              <h2>Table '{resource}' not found</h2>
              <p>The table <strong>{resource}</strong> does not exist in the connected database/schema.</p>
              <p>Possible fixes:</p>
              <ul>
                <li>Run the migrations: apply <code>auvo/schema.sql</code> or <code>auvo/migrate_schema.sql</code>.</li>
                <li>Ensure the app is connecting to the right database/schema (check <code>PG_DSN</code> or <code>PGDATABASE</code> / <code>AUVO_PG_DB</code>).</li>
                <li>Verify the `search_path` includes the <code>auvo</code> schema.</li>
              </ul>
              <p><a href='/'>Back</a></p>
            </body></html>
            """
            conn.close()
            return html
        conn.close()
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass

    prev_link = f"/db/{resource}?page={page-1}&page_size={page_size}" if page > 1 else ''
    next_link = f"/db/{resource}?page={page+1}&page_size={page_size}" if offset + page_size < total else ''

    rows_html = []
    for r in rows:
      rid = escape(str(r['id']))
      fetched = escape(str(r.get('fetched_at', '')))
      preview = escape(json.dumps(r.get('data', {}), ensure_ascii=False))[:300]
      # Build row with normalized columns when available
      cells = [f"<td><a href='/db/{resource}/{rid}'>{rid}</a></td>", f"<td>{fetched}</td>"]
      for c in existing_cols:
        val = r.get(c)
        cells.append(f"<td>{escape(str(val)) if val is not None else ''}</td>")
      cells.append(f"<td><pre style='white-space:pre-wrap'>{preview}</pre></td>")
      rows_html.append(f"<tr>{''.join(cells)}</tr>")

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
              <th>id</th>
              <th>fetched_at</th>
              {''.join(f'<th>{c}</th>' for c in existing_cols)}
              <th>data (preview)</th>
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
    # fetch existing normalized columns for this resource
    try:
      cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (resource,))
      db_cols = {r['column_name'] for r in cur.fetchall()}
    except Exception as e:
      msg = str(e)
      if 'does not exist' in msg or 'UndefinedTable' in msg or isinstance(e, getattr(psycopg2.errors, 'UndefinedTable', Exception)):
        conn.close()
        return f"<html><body><h2>Table '{resource}' not found</h2><p>The table <strong>{resource}</strong> does not exist in the connected database/schema.</p><p>Apply the migrations (see <code>auvo/schema.sql</code>) or check your DB connection.</p><p><a href='/'>Back</a></p></body></html>"
      conn.close()
      raise
    # prefer the common normalized fields if present
    candidates = {
      'users': ['name', 'login', 'email', 'user_id', 'base_lat', 'base_lon'],
      'tasks': ['task_id', 'task_date', 'customer_id', 'latitude', 'longitude', 'task_status', 'user_from', 'user_to', 'external_id'],
      'customers': ['customer_id', 'customer_name', 'address', 'latitude', 'longitude', 'external_id'],
    }
    use_cols = [c for c in candidates.get(resource, []) if c in db_cols]
    select_cols = ', '.join(['id', 'fetched_at'] + use_cols + ['data'])
    cur.execute(f"SELECT {select_cols} FROM {resource} WHERE id = %s", (row_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        abort(404)
    pretty = json.dumps(row.get('data', {}), ensure_ascii=False, indent=2)
    # build a small table of normalized fields if present
    norm_html = ''
    if use_cols:
        rows_norm = ''.join(f"<tr><th style='text-align:left'>{escape(c)}</th><td>{escape(str(row.get(c,'')))}</td></tr>" for c in use_cols)
        norm_html = f"<h3>Normalized fields</h3><table style='border-collapse:collapse'>{rows_norm}</table>"

    html = f"""
    <html>
      <head><title>{resource} {escape(str(row_id))}</title></head>
      <body>
        <h2>{resource} / {escape(str(row_id))}</h2>
        <p>fetched_at: {escape(str(row.get('fetched_at','')))}</p>
        {norm_html}
        <h3>Raw JSON</h3>
        <pre style='white-space:pre-wrap'>{escape(pretty)}</pre>
        <p><a href='/db/{resource}'>Voltar</a></p>
      </body>
    </html>
    """
    return html


if __name__ == '__main__':
    # start local dev server
    app.run(host='0.0.0.0', port=5000, debug=True)
