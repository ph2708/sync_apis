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


