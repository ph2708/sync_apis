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


