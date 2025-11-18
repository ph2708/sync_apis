**Backfill & Scheduler**

**Purpose:** populate `routes` for historical dates and keep daily updates scheduled.

**Daily runner:** `e-track/daily_routes_runner.py` — intended to run once per day (cron/systemd). It:
- acquires a Postgres advisory lock to avoid concurrent runs
- discovers plates (from DB or provided file) and processes them in batches
- rate-limits between plates via `ETRAC_RATE_SLEEP`

**Backfill controller:** `e-track/backfill_controller.py` — run to populate ranges of dates for plates. Usage example:

```bash
cd /path/to/sync_apis
.venv/bin/python e-track/backfill_controller.py --date-start 2025-01-01 --date-end 2025-01-07 --plates-file plates.txt --sleep 0.5
```

**Retries:** HTTP requests now use `e-track/http_retry.py` with exponential backoff. Configure by environment or defaults.

**Lock IDs:** defaults are `ETRAC_DAILY_LOCK_ID=123456789` and `ETRAC_BACKFILL_LOCK_ID=987654321`. You can override via env.

**Cron example (daily at 02:00):**

```bash
0 2 * * * cd /path/to/sync_apis && /path/to/venv/bin/python e-track/daily_routes_runner.py >> /var/log/e-track/daily_routes.log 2>&1
```

**Systemd example:** create `e-track-routes.service` with ExecStart pointing to the runner and enable a timer.

**Notes & recommendations:**
- Keep `DISABLE_UI_SCHEDULER=true` for the Web UI in production.
- Start with small `ETRAC_RATE_SLEEP` (0.2-1.0s) and small `batch-size` and increase carefully.
- Run backfill overnight and monitor API rate-limits.
