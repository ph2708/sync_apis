**Migração automática diária (schema normalization)**

Este repositório inclui um script que aplica `migrate_schema.sql` de forma idempotente:

- `run_migration.py` — conecta ao Postgres (lê `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`) e executa `migrate_schema.sql` se não tiver sido executado hoje. Registra execuções na tabela `migrations`.
- `run_migration.sh` — wrapper shell simples para rodar o script.

Opções para agendar a execução uma vez por dia:

1) Cron (host)

Adicione uma entrada crontab para o usuário que deve executar a migração. Exemplo para rodar às 02:10 diariamente:

```bash
# editar crontab
crontab -e

# adicione a linha abaixo (ajuste o caminho absoluto do repo se necessário)
10 2 * * * cd /home/phelipe/integra_maq/sync_api && \
PGHOST=localhost PGPORT=5432 PGUSER=auvo PGPASSWORD=auvo_pass PGDATABASE=auvo ./run_migration.sh >> /var/log/auvo_migration.log 2>&1
```

2) Systemd timer (servidor Linux)

Crie duas unidades: `/etc/systemd/system/auvo-migrate.service` e `/etc/systemd/system/auvo-migrate.timer`.

`/etc/systemd/system/auvo-migrate.service`:

```ini
[Unit]
Description=Run Auvo DB migration

[Service]
Type=oneshot
WorkingDirectory=/home/phelipe/integra_maq/sync_api
Environment=PGHOST=localhost
Environment=PGPORT=5432
Environment=PGUSER=auvo
Environment=PGPASSWORD=auvo_pass
Environment=PGDATABASE=auvo
ExecStart=/usr/bin/env python3 /home/phelipe/integra_maq/sync_api/run_migration.py
```

`/etc/systemd/system/auvo-migrate.timer` (diário às 02:10):

```ini
[Unit]
Description=Daily Auvo DB migration

[Timer]
OnCalendar=*-*-* 02:10:00
Persistent=true

[Install]
WantedBy=timers.target
```

Depois:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now auvo-migrate.timer
```

3) Agendamento via Docker host* (execução `docker-compose exec` a partir de host cron)

Se preferir manter o scheduler no host mas o Postgres rodar em container, adicione no crontab um comando `docker-compose exec` para chamar o script dentro do container que tenha Python/psql disponível. Exemplo (ajuste nomes/paths):

```bash
# exemplo: rodar comando no serviço app que tem python instalado
10 2 * * * cd /home/phelipe/integra_maq/sync_api && docker-compose exec -T app /usr/local/bin/python /app/run_migration.py >> /var/log/auvo_migration.log 2>&1
```

Observações:
- `run_migration.py` já é idempotente por dia — ele checa a tabela `migrations` e não reaplica o mesmo arquivo mais de uma vez no mesmo dia.
- Se quiser que a migração rode toda vez que o `auvo_sync.py` for executado, posso integrar uma chamada a `run_migration.py` no início de `auvo_sync.py` (opcional).

