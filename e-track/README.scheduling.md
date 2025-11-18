# e-Track Scheduling & Deployment

This document explains recommended ways to run the collector separately from the web UI. Use whichever approach fits your environment: `systemd`, `cron`, or a `docker-compose` sidecar.

Prerequisites
-------------
- A Python virtualenv with project dependencies installed (see root `requirements.txt`):
  ```bash
  .venv/bin/pip install -r requirements.txt
  ```
- Ensure Postgres is available and `PG*` environment variables point to it (or use `PG_DSN`).

Option A — systemd (recommended for servers)
-------------------------------------------
Create a small service unit for the collector. Example `/etc/systemd/system/etrac-collector.service`:

```ini
[Unit]
Description=e-Track Collector
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/sync_apis
Environment=PGHOST=127.0.0.1
Environment=PGPORT=5432
Environment=PGDATABASE=sync_apis
Environment=PGUSER=sync_user
Environment=PGPASSWORD=sync_pass
Environment=ETRAC_USER=your_api_user
Environment=ETRAC_KEY=your_api_key
ExecStart=/path/to/.venv/bin/python e-track/collector.py --fetch-latest --loop
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Notes:
- Use `--loop` if you add an argument to keep it running; otherwise use cron scheduling below. The `collector.py` supports single-run commands like `--fetch-latest` or `--compute-routes-current-day-all`.

Option B — cron (simple and portable)
-----------------------------------
Add crontab entries to run the collector periodically.

Example crontab (edit with `crontab -e`):

```cron
# every 2 minutes: fetch latest positions
*/2 * * * * cd /path/to/sync_apis && /path/to/.venv/bin/python e-track/collector.py --fetch-latest >> /var/log/etrac_fetch_latest.log 2>&1
# daily at 01:00: recompute routes for current day
0 1 * * * cd /path/to/sync_apis && /path/to/.venv/bin/python e-track/collector.py --compute-routes-current-day-all >> /var/log/etrac_routes.log 2>&1
```

Option C — docker-compose sidecar
---------------------------------
If you deploy with Docker Compose you can add a small service that runs the collector on a schedule using a lightweight scheduler container or by running a simple loop with `sleep`.

Example `docker-compose.override.yml` snippet:

```yaml
services:
  etrac-collector:
    image: python:3.11-slim
    working_dir: /app
    volumes:
      - ./:/app:ro
    command: bash -c "while true; do /usr/local/bin/python /app/e-track/collector.py --fetch-latest >> /app/e-track/logs/fetch_latest.log 2>&1; sleep 120; done"
    environment:
      - PGHOST=db
      - PGPORT=5432
      - PGDATABASE=sync_apis
      - PGUSER=sync_user
      - PGPASSWORD=sync_pass
      - ETRAC_USER=${ETRAC_USER}
      - ETRAC_KEY=${ETRAC_KEY}
    depends_on:
      - db
```

Disable embedded scheduler in web UI
-----------------------------------
When running the collector separately you should disable the embedded scheduler in `web_ui.py` to avoid duplicate runs. Start the web UI with the environment variable `DISABLE_UI_SCHEDULER=1`:

```bash
DISABLE_UI_SCHEDULER=1 .venv/bin/gunicorn -w 1 -b 0.0.0.0:5001 e-track.web_ui:app
```

Logging
-------
- Scheduled run logs (when using the embedded scheduler) are written to `e-track/logs/` by default.
- If you use `systemd`, rely on `journalctl -u etrac-collector.service`.

Next steps / options I can implement for you
--------------------------------------------
- Create a ready-to-use `systemd` unit file prefilled with sensible paths for your environment.
- Add a `docker-compose` service with proper healthchecks and resource limits.
- Add a `crontab` install script to automate adding the cron entries.

