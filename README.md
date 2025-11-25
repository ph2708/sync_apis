# Sync APIs — Monorepo

Este repositório contém coletores e sincronizadores para dois serviços:

- **Auvo** (pasta `auvo/`)
- **e-Track** (pasta `e-track/`)

Ambos podem compartilhar uma instância Postgres local para desenvolvimento;
cada projeto usa um schema próprio (`auvo`, `e_track`) dentro do mesmo banco
(`sync_apis`).

Objetivo deste README: instruções rápidas para desenvolver, aplicar schemas
e executar os componentes localmente, além dos comandos para atualizar o
repositório (git).

---

## Pré-requisitos

- WSL (para usuários Windows recomenda-se executar os comandos no WSL).
- Docker & Docker Compose (CLI `docker compose`).
- Python 3.10+ e `virtualenv` (recomendado).
- Opcional: `psql` (cliente Postgres). Se não estiver instalado o helper usa o
  container Postgres.

---

## Atualizações recentes (nota rápida)

- 2025-11-25: Ajustado o coletor `e-track` para preferir HTTPS por padrão.
	- Variável de ambiente `ETRAC_API_BASE` foi adicionada ao `.env.example` e ao `.env` de exemplo para apontar para `https://api.etrac.com.br/monitoramento`.
	- O helper de requisições `e-track/http_retry.py` foi melhorado para:
		- Normalizar timeouts numéricos para um par (connect, read), reduzindo o tempo de conexão padrão para falhar mais rápido em problemas de rede;
		- Adicionar jitter ao backoff exponencial para evitar picos de retry simultâneos;
		- Incluir o tipo da exceção nos logs para facilitar diagnóstico (ex.: ConnectTimeout).
	- Recomendação: configure `ETRAC_API_BASE` no seu `.env` local (não comitar `.env`) para controlar ambiente (staging/prod/dev) sem tocar no código.

	## Serviço diário (rodar jobs de Auvo + e-Track)

	Adicionei um runner simples que agenda a execução diária dos jobs de sincronização
	de ambos os projetos. Opções de deployment:

	- Executar localmente com o virtualenv (recomendado):

	```bash
	# a partir da raiz do repositório
	./scripts/run_daily.sh
	# para execução única (útil para teste):
	./scripts/run_daily.sh --once
	```

	- systemd (exemplo): copie os arquivos em `deploy/systemd/` para `/etc/systemd/system/`,
		ajuste `WorkingDirectory` e `ExecStart` no unit file e habilite:

	```bash
	sudo cp deploy/systemd/sync-apis-daily.service /etc/systemd/system/sync-apis-daily.service
	sudo cp deploy/systemd/sync-apis-daily.timer /etc/systemd/system/sync-apis-daily.timer
	sudo systemctl daemon-reload
	sudo systemctl enable --now sync-apis-daily.timer
	```

	- Docker Compose (exemplo): há um `docker-compose.daily.yml` que cria um
		container para executar o runner. Ajuste variáveis de ambiente conforme
		necessário:

	```bash
	docker compose -f docker-compose.daily.yml up -d
	```

	Configuração via ENV (opcional):
	- `DAILY_RUN_HOUR` e `DAILY_RUN_MINUTE` — hora e minuto da execução diária (padrão 01:05)
	- `RUN_AUVO`, `RUN_ETRAC` — setar 0 para pular execução de um dos jobs
	- `AUVO_CMD`, `ETRAC_CMD` — comandos customizados para executar os jobs

	Logs: o runner escreve em stdout/stderr; quando rodando via systemd use `journalctl -u sync-apis-daily.service`.



## Setup rápido (WSL)

1. Criar/ativar virtualenv (recomendado):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

2. Instalar dependências (opcional global ou por projeto):

```bash
# dependências de utilitários (opcional)
pip install -r requirements.txt

# dependências específicas (opcional)
pip install -r e-track/requirements.txt
pip install -r auvo/requirements.txt
```

3. Subir o Postgres local (servirá para ambos os projetos):

```bash
docker compose -f db/docker-compose.yml up -d
docker compose -f db/docker-compose.yml ps
docker compose -f db/docker-compose.yml logs -f db
```

4. Aplicar migrations/schemas (helper):

```bash
./db/apply-all-migrations.sh
```

O helper aplica os SQLs necessários (scripts em `db/init/`, `e-track/schema.sql`,
`auvo/schema.sql`). Se `psql` não existir no WSL, o script executa `psql`
dentro do container.

5. Verificar que os schemas/tabelas existem:

```bash
docker compose -f db/docker-compose.yml exec -T db \
  psql -U sync_user -d sync_apis -c "\dt e_track.*"

docker compose -f db/docker-compose.yml exec -T db \
  psql -U sync_user -d sync_apis -c "\dt auvo.*"
```

---

## Como rodar os componentes localmente

- e-Track (coletor básico):

```bash
python3 e-track/collector.py --fetch-latest
```

- e-Track — UI leve para navegar nos dados (local):

```bash
python3 e-track/web_ui.py
# acessível em http://0.0.0.0:5001
```

- Auvo (sincronizador):

```bash
python3 auvo/auvo_sync.py --db-wait 2
python3 auvo/web_ui.py  # se presente
```

---

## Comandos para atualizar o repositório (git)

Use estes comandos para enviar alterações ao remoto. Ajuste o `branch` conforme
o seu fluxo (branch por feature/bugfix é recomendado).

1) Verificar o que mudou:

```bash
git status --short
```

2) Preparar alterações:

```bash
git add <arquivo1> <arquivo2>
# ou adicionar tudo (use com cuidado):
git add -A
```

3) Commitar com mensagem clara:

```bash
git commit -m "descrição curta e informativa das alterações"
```

4) Publicar (push):

```bash
# se estiver em main (evite push direto em main se equipe usar PRs)
git push origin main

# recomendado: criar branch, push e abrir PR
git checkout -b feat/nome-da-feature
git push -u origin feat/nome-da-feature
```

5) Atualizar branch local com remoto antes de trabalhar (pull/rebase):

```bash
git fetch origin
git switch main
git pull --rebase origin main
```

---

## Troubleshooting rápido

- `psql: command not found`: instale cliente Postgres no WSL:

```bash
sudo apt update && sudo apt install -y postgresql-client
```

- Ver logs do Postgres container:

```bash
docker compose -f db/docker-compose.yml logs --tail=200 db
```

- Tabelas criadas no schema errado: verifique se `schema.sql` define
  `SET search_path` e execute `./db/apply-all-migrations.sh` novamente.

---

## Arquivos importantes

- `db/` — compose e scripts de inicialização do Postgres.
- `db/apply-all-migrations.sh` — aplica schemas/migrations.
- `e-track/` — coletor, runners, UI e utilitários de backfill.
- `auvo/` — sincronizador e utilitários Auvo.

---

Se quiser, eu posso:

- deixar um `README.pt-BR.md` com exemplos por comando (`collector.py` flags),
- adicionar um `CONTRIBUTING.md` com convenções de commits e branch names,
- gerar scripts de `make` ou `just` para simplificar os passos mais comuns.

Diga qual desses extras você prefere que eu adicione primeiro.
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




