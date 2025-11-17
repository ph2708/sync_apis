# Sync APIs — Monorepo

Este repositório reúne coletores/sincronizadores (Auvo e e-Track) organizados
para compartilhar uma única instância Postgres em desenvolvimento, usando
schemas separados (`auvo` e `e_track`) dentro do mesmo banco `sync_apis`.

**Pré-requisitos**
- Docker & Docker Compose (CLI `docker compose`).
- Python 3.11+ para executar os coletores.
- (Opcional) `psql` cliente no WSL; se não tiver, os helpers usam fallback
	para executar `psql` dentro do container Postgres.

**Instalar dependências Python**
- Recomendo usar um virtualenv no WSL para isolar dependências:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
# instalar dependências raiz (contém psycopg2-binary)
pip install -r requirements.txt
```

Se preferir instalar apenas para um projeto, uso:

```bash
# para Auvo
pip install -r auvo/requirements.txt

# para e-Track
pip install -r e-track/requirements.txt
```

**Visão geral**
- Banco central: `db/docker-compose.yml` — serviço Postgres que monta os
	scripts de inicialização em `db/init/`.
- Schemas: `auvo` e `e_track` no database `sync_apis`.
- Helper: `db/apply-all-migrations.sh` — aplica os arquivos de schema/migration
	para ambos os projetos; detecta `psql` local ou usa o container como fallback.

**Quickstart (passo-a-passo)**

1) Copiar variáveis de exemplo (opcional):

```bash
cp .env.example .env
# editar .env se quiser trocar senhas, host ou porta
```

2) Subir o Postgres central:

```bash
docker compose -f db/docker-compose.yml up -d
```

3) Confirmar que o Postgres está rodando:

```bash
docker compose -f db/docker-compose.yml ps
docker compose -f db/docker-compose.yml logs -f db
```

4) Aplicar todas as migrations/schemas (helper):

```bash
./db/apply-all-migrations.sh
```

O helper aplica, na ordem, os arquivos necessários para criar schemas e
tabelas. Se o `psql` não estiver disponível no seu WSL, o script executará o
`psql` dentro do container Postgres.

5) Verificar tabelas criadas para cada projeto:

```bash
# listar tabelas no schema auvo
docker compose -f db/docker-compose.yml exec -T db \
	psql -U sync_user -d sync_apis -c "\dt auvo.*"

# listar tabelas no schema e_track
docker compose -f db/docker-compose.yml exec -T db \
	psql -U sync_user -d sync_apis -c "\dt e_track.*"
```

6) Exemplos de execução dos projetos

Auvo (sincronizador):

```bash
# Exemplos — se estiver dentro da pasta `auvo` execute:
#   python3 auvo_sync.py --db-wait 2
# Se estiver na raiz do repositório execute:
#   python3 auvo/auvo_sync.py --db-wait 2
# Para iniciar a UI leve (a partir da pasta `auvo`):
python3 auvo/web_ui.py
# abrir http://127.0.0.1:5000
```

e-Track (coletor):

```bash
python3 e-track/collector.py --fetch-latest
```

**Arquivos e utilitários importantes**
- `db/docker-compose.yml` — compose do Postgres central.
- `db/init/` — scripts aplicados na primeira inicialização do container.
- `db/apply-all-migrations.sh` — helper para aplicar `auvo` e `e-track`.
- `auvo/schema.sql` — criação idempotente das tabelas base do Auvo.
- `auvo/migrate_schema.sql` — migração/ALTER e backfill (executada após
	`auvo/schema.sql`).
- `e-track/schema.sql` — criação das tabelas do e-Track (schema `e_track`).

**Parar o banco central**

```bash
docker compose -f db/docker-compose.yml down
```

**Solução de problemas (troubleshooting)**
- `psql: command not found`: Instale `postgresql-client` no WSL
	(`sudo apt update && sudo apt install postgresql-client`) ou use o helper
	(`db/apply-all-migrations.sh`) que tem fallback para executar `psql` dentro
	do container.
- Migrations falhando: verifique os logs do container:

```bash
docker compose -f db/docker-compose.yml logs --tail=200 db
```

- Tabelas ausentes em `auvo`: verifique se `auvo/schema.sql` foi aplicado antes
	de `auvo/migrate_schema.sql`. O helper já aplica `auvo/schema.sql` antes do
	backfill.

**Boas práticas**
- Em desenvolvimento, use o DB central local. Em produção, gerencie credenciais
	com secrets e não exponha a porta 5432 publicamente.
- Sempre faça backup antes de mover tabelas entre schemas ou truncar dados.

**Estrutura do repositório (resumo)**
- `db/` — compose e scripts de inicialização do Postgres.
- `auvo/` — código, migrations, utilitários do Auvo.
- `e-track/` — código, schema e utilitários do e-Track.
- `.env.example` — exemplo de variáveis de ambiente de conexão com o DB.




