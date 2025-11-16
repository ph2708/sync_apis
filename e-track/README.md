# e-Track collector

Este pequeno coletor busca dados da API eTrac (endpoints documentados) e armazena em um banco PostgreSQL.

Rápido start

1. Criar um virtualenv e instalar dependências:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Ajustar variáveis de ambiente. Exemplo:

```bash
export ETRAC_USER=user@api
export ETRAC_KEY=passwordapi
export PGHOST=localhost
export PGPORT=5432
export PGDATABASE=mydb
export PGUSER=myuser
export PGPASSWORD=mypassword
```

Ou crie um arquivo `.env` copiando `.env.example`.

3. Importar o schema (opcional):

```bash
# Para criar um schema dedicado `e_track` e as tabelas dentro dele (recomendado):
psql "postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE" -f e-track/schema.sql

# Alternativamente, se preferir criar apenas o schema e depois aplicar os objetos, rode:
psql "postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE" -c "CREATE SCHEMA IF NOT EXISTS e_track;"
psql "postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE" -f e-track/schema.sql
```

4. Executar o coletor:

```bash
python collector.py --fetch-latest
python collector.py --fetch-plate ABC-1234
python collector.py --fetch-history ABC-1234 --date "15/11/2025"
python collector.py --fetch-trips ABC-1234 --date "15-11-2025"
```

Observações
- O script usa autenticação Basic Auth com `ETRAC_USER` e `ETRAC_KEY`.
- O esquema SQL está em `schema.sql`.
- O script tenta identificar estruturas de resposta comuns do WebService documentado; caso a API retorne formatos variados, pode ser necessário ajustar o mapeamento de campos.
 - As tabelas são criadas dentro do schema `e_track` por padrão. O coletor define o `search_path` para o schema especificado por `ETRAC_SCHEMA` (padrão `e_track`).
 - Se preferir outro schema, ajuste a variável `ETRAC_SCHEMA` no ambiente ou no `.env`.

Docker Compose (Postgres dedicado para e-track)
-------------------------------------------

Há um `docker-compose.yml` dedicado em `e-track/docker-compose.yml` que cria um container Postgres para o e-track. Ele usa o banco `e_track` e mapeia a porta do host `5433` para `5432` do container para evitar conflito com outros DBs locais.

Comandos rápidos (na pasta do repositório raiz):

```bash
# subir o DB do e-track
cd e-track
./start-db.sh

# parar o DB
./stop-db.sh
```

Variáveis de conexão quando usar o DB via docker-compose:

```bash
export PGHOST=127.0.0.1
export PGPORT=5433
export PGDATABASE=e_track
export PGUSER=etrack
export PGPASSWORD=etrack_pass
```

Depois de subir o DB, aplique o schema (caso não tenha aplicado):

```bash
psql "postgresql://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$PGDATABASE" -f schema.sql
```

Utilitário `manage_db.sh`
-------------------------

Há um script utilitário `manage_db.sh` que combina subir/parar o DB e aplicar o schema.
Ele carrega `.env` se presente e aceita os seguintes comandos:

- `./manage_db.sh up` — sobe o container e espera readiness
- `./manage_db.sh down` — para o compose
- `./manage_db.sh status` — mostra status do container
- `./manage_db.sh apply-schema` — aplica `schema.sql` no DB configurado
- `./manage_db.sh init` — sobe o DB e aplica o schema (prático para bootstrap)
- `./manage_db.sh exec-psql` — abre um `psql` interativo no DB

Exemplo de uso para bootstrap:

```bash
cd e-track
chmod +x manage_db.sh start-db.sh stop-db.sh
./manage_db.sh init
```

Automatizando execução diária
----------------------------

Você pode agendar o coletor para rodar diariamente e gravar o mês atual incrementamente. Crie um arquivo `.env` com suas credenciais (`ETRAC_USER`/`ETRAC_KEY`) e as variáveis de conexão do Postgres, e use um script wrapper que carrega o `.env` antes de executar o coletor.

Exemplo de `crontab` (rodando todo dia às 03:00):

```cron
# m h  dom mon dow   command
0 3 * * * cd /home/phelipe/integra_maq/sync_api/e-track && . .venv/bin/activate && ./run_daily_collect.sh >> /var/log/e-track-collector.log 2>&1
```

O script `run_daily_collect.sh` (criado no repositório) apenas carrega `.env` e executa:

```bash
./run_daily_collect.sh
```

Collector configuration and running
----------------------------------

You can store credentials in a `.env` file in the `e-track` directory (see `e-track/.env.example`). The collector will load `.env` automatically (it uses `python-dotenv` and will not override environment variables already exported).

Example `.env` (do not commit this file):

```dotenv
ETRAC_USER=phelipe.figueiredo@maquigeral.com.br
ETRAC_KEY=24941762861901
ETRAC_SCHEMA=e_track
# Postgres created by manage_db.sh/docker-compose
PGHOST=127.0.0.1
PGPORT=5433
PGDATABASE=e_track
PGUSER=etrack
PGPASSWORD=etrack_pass
```

Run collector examples:

```bash
# Latest positions for the fleet
python collector.py --fetch-latest

# Last position for a given plate
python collector.py --fetch-plate ABC-1234

# History for a plate on a date
python collector.py --fetch-history ABC-1234 --date "15/11/2025"

# Trips summary for a plate on a date
python collector.py --fetch-trips ABC-1234 --date "15-11-2025"

# Run for all plates / month
You can instruct the collector to fetch the current month's history for all plates discovered by the `ultimas-posicoes` endpoint. This is handy to run daily (the collector is idempotent and will not insert duplicates).

```bash
# Fetch current month for every plate returned by the API (may take time)
python collector.py --fetch-current-month-all

# Or fetch the current month for a specific plate
python collector.py --fetch-current-month-plate FCY7I77
```

Notes on logs and verbosity
- The collector logs info-level messages by default. To enable more verbose debugging output (including HTTP request tracing), export:

```bash
export ETRAC_LOG_LEVEL=DEBUG
```

Wrapper script and scheduling
- The repository includes `run_daily_collect.sh` which loads `.env`, activates the virtualenv and runs the collector for the current month for all plates. Make it executable and add to `crontab` as shown in the "Automatizando execução diária" section.

Example quick-run (one-off):

```bash
# make sure env vars or .env contain ETRAC_USER/ETRAC_KEY and PG* connection values
source .venv/bin/activate
# optional: set debug logging
export ETRAC_LOG_LEVEL=INFO

python collector.py --fetch-current-month-all
```

Routes (daily)
---------------
The collector can compute and persist a per-vehicle daily route (aggregated from `positions`) into the database. This stores an array of points (lat/lon/timestamp/vel) in `routes.points` (JSONB) and is useful for replay/export.

Commands:

```bash
# Compute route for a single plate for a specific date
python collector.py --compute-route-plate FCY7I77 --compute-route-date 15/11/2025

# Compute route for a single plate for today (no date argument)
python collector.py --compute-route-plate FCY7I77

# Compute routes for *all* plates for the current day (useful in the daily cron)
python collector.py --compute-routes-current-day-all
```

Notes:
- Routes are stored in table `routes` with a uniqueness constraint on `(placa, rota_date)` so re-running is safe.
- You can export `routes.points` to GPX/GeoJSON in a later step, or render them directly in the web UI (I can add a viewer endpoint if you want).
```

Troubleshooting
---------------
- If the collector fails to connect to Postgres, ensure `PGHOST` points to `127.0.0.1` and `PGPORT` matches the port exposed by the compose file (default `5433`).
- If the API returns authentication errors, re-check `ETRAC_USER` and `ETRAC_KEY`.
- Use `./manage_db.sh exec-psql` to open an interactive `psql` and inspect tables: `\dt e_track.*` and `SELECT count(*) FROM e_track.positions;`.


