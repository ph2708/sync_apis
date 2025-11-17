# Auvo Sync (Postgres)

Este projeto sincroniza recursos da API Auvo para um banco PostgreSQL, armazena o JSON bruto em `data` (JSONB)
e popula colunas normalizadas para facilitar consultas e integrações.

Schema e organização do banco
--------------------------------
- Para evitar poluir o schema `public` quando o mesmo banco é usado por
	múltiplos projetos, este projeto usa um schema próprio chamado `auvo`.
	As migrations e a inicialização criam `auvo` automaticamente e definem
	`search_path = auvo, public` — isto garante que as tabelas e índices do
	projeto ficam em `auvo` enquanto ainda é possível consultar objetos do
	`public` quando necessário.

- O outro projeto neste repositório, `e-track`, usa o schema `e_track`.
	Assim ambos os projetos podem ser carregados no mesmo banco Postgres sem
	conflito, cada um no seu schema.

Resumo rápido
- Autentica na API Auvo (/login) e busca recursos paginados (`/users`, `/tasks`, `/customers`).
- Persiste objetos na tabela correspondente (`users`, `tasks`, `customers`) com `data` (JSONB) e colunas normalizadas.
- Fornece um runner de migração `run_migration.py` para adicionar colunas e backfill.
- Inclui uma UI leve `web_ui.py` para navegar os dados localmente.

Requisitos
- Python 3.11+ (recomendado)
- Docker & Docker Compose (para Postgres, opcional se já tiver Postgres)

Setup (rápido)

1. Criar e ativar virtualenv e instalar dependências:

```bash
cd ~/integra_maq/sync_api/auvo
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

2. Subir Postgres via Docker Compose (opcional — o projeto já inclui `docker-compose.yml`):

```bash
# a partir da pasta do projeto
docker-compose up -d
docker-compose ps
```

3. Executar a migração de schema / backfill (uma vez):

```bash
# conecta ao Postgres e aplica migrate_schema.sql (ajuste variáveis se necessário)
# a migration já cria o schema `auvo` e aplica `search_path = auvo, public`.
PGHOST=localhost PGPORT=5432 PGUSER=auvo PGPASSWORD=auvo_pass PGDATABASE=<db> \
python3 run_migration.py

# ou usando o wrapper
PGHOST=localhost PGPORT=5432 PGUSER=auvo PGPASSWORD=auvo_pass PGDATABASE=auvo \
./run_migration.sh
```

4. Executar sincronização com Auvo (sync):

```bash
# helper que instala dependências e roda o sync
./run-sync.sh

# ou diretamente
python3 auvo_sync.py --db-wait 2
```

5. Ver os dados localmente (UI):

```bash
python3 web_ui.py
# abrir http://127.0.0.1:5000
```

Observação sobre a UI
- A UI agora exibe automaticamente as colunas normalizadas (por exemplo `name`, `email` para `users`; `task_id`, `task_date` para `tasks`; `customer_name`, `address` para `customers`) quando essas colunas existirem no banco.
- Se você ainda não aplicou `migrate_schema.sql`, execute a migração para adicionar e backfill das colunas normalizadas. Após aplicar a migração as colunas aparecerão na lista e na visualização detalhada.

Resetar o banco (apagar dados e re-sincronizar)
- Se quiser apagar os dados atuais e re-sincronizar do zero, use o utilitário `reset_db.py`.
- AVISO: isso irá remover TODOS os registros das tabelas selecionadas.

Exemplo:

```bash
# carregar .env e executar (interativo)
./reset-db.sh

# ou sem prompt (tenha certeza):
./reset-db.sh --yes
```

Depois de truncar as tabelas, rode a migração (se necessário) e execute o sync:

```bash
python3 run_migration.py
./run-sync.sh
```

Variáveis de ambiente importantes
- `AUVO_API_KEY`, `AUVO_API_TOKEN` — credenciais Auvo (se não estiverem em env, o script usa valores de teste no código).
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` — conexão Postgres usada por `run_migration.py` e por `auvo_sync.py`.

Usando um único arquivo de configuração
- Há um arquivo de exemplo `.env.example` na raiz do projeto `auvo/`.
- Para usar, copie e preencha os valores (não comite suas chaves reais):

```bash
cp .env.example .env
# editar .env e preencher suas credenciais
```

O script `run-sync.sh` já carrega variáveis de `.env` automaticamente se o arquivo existir.

Notas e compatibilidade
- O código atual espera Postgres; a flag `--db` (SQLite) foi removida. Se precisar compatibilidade SQLite temporária, posso reintroduzir a opção.
- Há um serviço opcional para executar a migração diariamente via Docker: veja `docker-compose.cron.yml` e `docker/migration-cron`.

Se quiser que eu ajuste o `auvo_sync.py` para reativar o modo SQLite ou integrar a chamada de migração automaticamente antes do sync, diga qual opção prefere.
