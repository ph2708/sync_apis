# e-Track — Backfill & Scheduling (consolidado)

Este documento unifica instruções de *backfill*, execução e *scheduling* do
coletor e-Track. Objetivo: ter um guia único e curto para executar o coletor,
fazer backfills históricos e instalar jobs em `cron`/`systemd` ou via
`docker-compose`.

Sumário
- Visão rápida
- Backfill (objetivo + uso)
- Scheduler / Deployment (systemd, cron, docker)
- Execução local / UI
- Boas práticas e troubleshooting

---

Visão rápida
-----------

- `collector.py` — principal script que consulta a API e insere posições/rotas
  no Postgres.
- `daily_routes_runner.py` — runner pensado para executar uma vez por dia
  (cron/systemd) e gerar rotas diárias para todas as placas.
- `backfill_controller.py` — controladora para popular ranges de datas
  históricas por placa.

Backfill (o que e como)
-----------------------

Objetivo: preencher a tabela `routes` com rotas históricas por placa/data.

Uso rápido (exemplo):

```bash
cd /path/to/sync_apis
.venv/bin/python e-track/backfill_controller.py \
  --date-start 2025-01-01 --date-end 2025-01-07 \
  --plates-file plates.txt --sleep 0.5
```

Pontos importantes:
- O backfill processa placas em batches, respeitando `ETRAC_RATE_SLEEP` entre
  placas para evitar rate-limit da API.
- `e-track/http_retry.py` aplica retries exponenciais para requests HTTP.
- Lock IDs padrões: `ETRAC_DAILY_LOCK_ID=123456789` e
  `ETRAC_BACKFILL_LOCK_ID=987654321` (podem ser sobrescritos por env).

Scheduler / Deployment
----------------------

Você pode executar o coletor por `systemd`, `cron` ou como um serviço Docker.

Opção A — systemd (recomendada para servidores)

Crie um unit file, ex.: `/etc/systemd/system/etrac-collector.service` com:

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

Notas:
- Use `--loop` se quiser que o coletor permaneça rodando em ciclo; caso
  contrário, prefira agendar via cron com execuções independentes.

Opção B — cron (simples e portátil)

Exemplo crontab (`crontab -e`):

```cron
*/2 * * * * cd /path/to/sync_apis && /path/to/.venv/bin/python e-track/collector.py --fetch-latest >> /var/log/etrac_fetch_latest.log 2>&1
0 1 * * * cd /path/to/sync_apis && /path/to/.venv/bin/python e-track/collector.py --compute-routes-current-day-all >> /var/log/etrac_routes.log 2>&1
```

Opção C — docker-compose sidecar

Você pode adicionar um serviço que execute o coletor em loop com `sleep`.
Exemplo simples no `docker-compose.override.yml`:

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

Desabilitar scheduler embutido na UI
-----------------------------------

Se você executar o collector separadamente (systemd/cron/docker), defina na
UI `DISABLE_UI_SCHEDULER=1` para evitar execução duplicada de jobs. Exemplo
com `gunicorn`:

```bash
DISABLE_UI_SCHEDULER=1 .venv/bin/gunicorn -w 1 -b 0.0.0.0:5001 e-track.web_ui:app
```

Execução local / On-demand
--------------------------

- Para gerar rotas do dia atual (único-run):

```bash
python3 e-track/collector.py --compute-routes-current-day-all
```

- Para fetch de posições mais recentes:

```bash
python3 e-track/collector.py --fetch-latest
```

Boas práticas e recomendações
----------------------------

- Comece com `ETRAC_RATE_SLEEP=0.2-1.0` e `batch-size` pequeno; aumente com
  cuidado conforme estabilidade da API.
- Execute backfills durante a madrugada para reduzir impacto em produção e
  para evitar bater limites de API.
- Monitore logs (`e-track/logs/` ou `journalctl` / `docker logs`).

Troubleshooting rápido
---------------------

- Se não encontrar rotas após o backfill, verifique se o collector conseguiu
  buscar o histórico (`--fetch-history`) e se a tabela `routes` contém os
  registros esperados.
- Ver logs do collector para ver erros HTTP ou exceções.

---

Se quiser, eu deixo este README ainda mais curto (cheat-sheet) ou então crio
o `systemd` unit file e um script para instalar as entradas de `cron` — diga
qual você prefere.
# e-Track collector

Este projeto faz parte do monorepo `sync_apis`.

Documentação e instruções para subir o banco e aplicar migrations foram
centralizadas no README na raiz do repositório. Consulte `README.md` na
raiz para instruções completas (bootstrap do Postgres, aplicação de
migrations, e passos de execução do coletor).


Resumo rápido
------------
- Schema SQL: `e-track/schema.sql` (cria objetos no schema `e_track`).
- Scripts úteis: `manage_db.sh`, `start-db.sh`, `stop-db.sh` foram atualizados
	para usar o compose central em `db/docker-compose.yml`.

Arquivos principais
------------------
- `schema.sql` — definição das tabelas e índices utilizadas pelo coletor.
- `collector.py` — código principal que faz chamadas à API e persiste os dados.
- `manage_db.sh` — utilitário para subir/parar o DB e aplicar o schema (atualizado para compose central).

Comandos úteis
-------------
- Subir o DB central (raiz do repositório):
	```bash
	docker compose -f db/docker-compose.yml up -d
	```
- Aplicar o schema do e-track manualmente:
	```bash
	PGPASSWORD=sync_pass psql -h 127.0.0.1 -U sync_user -d sync_apis -f e-track/schema.sql
	```
- Rodar o coletor:
	```bash
	python3 e-track/collector.py --fetch-latest
	```

Troubleshooting
---------------
- Se o coletor não conectar ao Postgres, verifique as variáveis `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD` (veja `.env` ou `.env.example`).
 - Se o coletor não conectar ao Postgres, verifique as variáveis `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD` (veja o `.env` na raiz do repositório ou `../.env.example`).
- Se o erro for de autenticação com a API, revalide `ETRAC_USER` e `ETRAC_KEY`.
- Para inspecionar a base, use:
	```bash
	PGPASSWORD=sync_pass psql -h 127.0.0.1 -U sync_user -d sync_apis -c "\dt e_track.*"
	```

Notas sobre configuração da API e comportamento de retry
-------------------------------------------------------

- Variável `ETRAC_API_BASE`: a base da API e-Track pode ser configurada via
  `ETRAC_API_BASE` no `.env` (ex.: `https://api.etrac.com.br/monitoramento`).
  Coloque essa variável no `.env` da raiz para alternar ambientes sem editar
  o código. O `.env.example` foi atualizado para documentar essa variável.

- Conexões e timeouts: o helper `e-track/http_retry.py` agora normaliza
  timeouts numéricos para um par (connect, read) e aplica um connect timeout
  mais curto por padrão (para detectar falhas de conexão rapidamente).

- Comportamento de retry: o helper adiciona jitter ao backoff e faz logs
  mais expressivos (incluindo o tipo da exceção, ex.: ConnectTimeout), o que
  facilita diagnosticar problemas de rede versus problemas do servidor.

- Observação operacional: muitos servidores não respondem ou bloqueiam porta
  80. Recomendamos usar `https://` na `ETRAC_API_BASE` quando possível.

Se quiser que eu adicione exemplos de queries comuns ou um script `e-track/queries.md`, eu posso gerar.

Manual passo-a-passo (e-Track)
1) Preparar variáveis de ambiente
```bash
# copie o exemplo do repositório raiz e edite os valores lá
cp ../.env.example ../.env
# editar ../.env se necessário (ETRAC_USER, ETRAC_KEY, PG* vars)
```

2) Subir o Postgres central (na raiz do repositório)
```bash
docker compose -f db/docker-compose.yml up -d
```

3) Aplicar schema do e-track
```bash
./db/apply-all-migrations.sh
# ou apenas aplicar o schema do e-track se preferir:
docker compose -f db/docker-compose.yml exec -T db psql -U sync_user -d sync_apis < e-track/schema.sql
```

4) Verificar tabelas criadas
```bash
docker compose -f db/docker-compose.yml exec -T db psql -U sync_user -d sync_apis -c "\dt e_track.*"
```

5) Rodar o coletor (exemplos)
```bash
python3 e-track/collector.py --fetch-latest
python3 e-track/collector.py --fetch-plate ABC-1234
```

6) Parar o DB (quando terminar)
```bash
docker compose -f db/docker-compose.yml down
```

Se quiser que eu gere um `e-track/queries.md` com consultas úteis (ex.: contar posições por placa, exportar rota), eu posso criar.

Scheduler integrado (APScheduler)
--------------------------------
O `web_ui.py` inclui um agendador opcional que pode executar o coletor periodicamente (fetch de posições e recomputação de rotas).

- Requisitos: instale o `APScheduler` no seu virtualenv:
```bash
.venv/bin/pip install -r requirements.txt
```

- Comportamento padrão (quando APScheduler estiver instalado):
	- `--fetch-latest` é executado a cada 2 minutos (atualiza `positions`).
	- `--compute-routes-current-day-all` é executado diariamente às `01:00` (recalcula/guarda rotas do dia).

- Logs: as execuções agendadas gravam saídas em `e-track/logs/` (`fetch_latest.log`, `compute_routes.log`).

- Observação importante: se você rodar o `web_ui.py` com um servidor que cria múltiplos processos (ex.: Gunicorn com >1 worker), cada processo pode iniciar o agendador e causar execuções duplicadas. Para produção recomendamos:
	- Rodar o web UI com 1 worker que contém o scheduler, e usar outro processo/cron para o collector; ou
	- Desabilitar o scheduler embutido e usar `cron`/`systemd`/`docker cron` para agendar o collector.

Exemplo rápido para produção (systemd + cron recomendado):

1. Instale dependências:
```bash
.venv/bin/pip install -r requirements.txt
```

2. Rodar apenas o web UI em Gunicorn (sem scheduler):
```bash
# se quiser evitar o scheduler embutido, execute com uma variável de ambiente para desativar
DISABLE_UI_SCHEDULER=1 .venv/bin/gunicorn -w 1 -b 0.0.0.0:5001 e-track.web_ui:app
```

3. Agendar o collector via crontab (exemplo):
```cron
# fetch latest every 2 minutes
*/2 * * * * cd /caminho/para/sync_apis && /caminho/para/.venv/bin/python e-track/collector.py --fetch-latest >> /var/log/etrac_fetch_latest.log 2>&1
# recompute daily at 01:00
0 1 * * * cd /caminho/para/sync_apis && /caminho/para/.venv/bin/python e-track/collector.py --compute-routes-current-day-all >> /var/log/etrac_routes.log 2>&1
```


