Claro! Aqui está uma **versão reorganizada, limpa e mais objetiva** do seu README — mantendo todas as informações importantes, mas estruturadas de forma clara, com seções bem definidas e hierarquia simples.

Se quiser, posso gerar também uma versão **pt-BR** e uma versão **en-US**, ou separar em vários arquivos (`README`, `CONTRIBUTING`, `docs/setup.md`, etc.).

---

# 📦 Sync APIs — Monorepo

Coletor e sincronizador de dados dos serviços **Auvo** e **e-Track**, organizados em um único repositório e compartilhando o mesmo banco Postgres (schemas separados).

---

# 🧱 Estrutura Geral

```
sync_apis/
├── auvo/                 # Sincronizador Auvo
├── e-track/              # Coletor e utilitários e-Track
├── db/                   # Banco central: compose, init e migrations
├── scripts/              # Scripts de execução diária
└── deploy/               # Exemplos para systemd e docker-compose diário
```

---

# ✔ Pré-requisitos

| Ferramenta                   | Uso                                         |
| ---------------------------- | ------------------------------------------- |
| **WSL (Ubuntu recomendado)** | Execução local no Windows                   |
| **Docker + Docker Compose**  | Banco de dados Postgres                     |
| **Python 3.10+**             | Execução dos coletores                      |
| **virtualenv (recomendado)** | Isolamento do ambiente                      |
| **psql (opcional)**          | Cliente local do Postgres – não obrigatório |

---

# 🚀 Setup Rápido

### 1) Criar e ativar virtualenv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

### 2) Instalar dependências

```bash
pip install -r requirements.txt
# ou dependências por projeto
pip install -r auvo/requirements.txt
pip install -r e-track/requirements.txt
```

### 3) Subir o Postgres

```bash
docker compose -f db/docker-compose.yml up -d
```

### 4) Aplicar schemas/migrations

```bash
./db/apply-all-migrations.sh
```

O script detecta automaticamente se existe `psql` local; se não houver, usa o `psql` do container.

### 5) Verificar tabelas criadas

```bash
docker compose -f db/docker-compose.yml exec -T db \
  psql -U sync_user -d sync_apis -c "\dt auvo.*"

docker compose -f db/docker-compose.yml exec -T db \
  psql -U sync_user -d sync_apis -c "\dt e_track.*"
```

---

# 🏗 Executando os Projetos

## Auvo — Sincronizador

```bash
python3 auvo/auvo_sync.py --db-wait 2
```

UI (se habilitada):

```bash
python3 auvo/web_ui.py
# http://127.0.0.1:5000
```

## e-Track — Coletor

```bash
python3 e-track/collector.py --fetch-latest
```

UI leve:

```bash
python3 e-track/web_ui.py
# http://0.0.0.0:5001
```

---

# ⏰ Execução diária (jobs)

O runner integrado executa Auvo + e-Track diariamente.

### Local (virtualenv)

```bash
./scripts/run_daily.sh
# ou execução única:
./scripts/run_daily.sh --once
```

### Via systemd

```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo cp deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sync-apis-daily.timer
```

### Via Docker Compose

```bash
docker compose -f docker-compose.daily.yml up -d
```

### Variáveis de ambiente úteis

| Variável                              | Descrição                  |
| ------------------------------------- | -------------------------- |
| `DAILY_RUN_HOUR` / `DAILY_RUN_MINUTE` | Horário do job             |
| `RUN_AUVO`, `RUN_ETRAC`               | Ativar/desativar execuções |
| `AUVO_CMD`, `ETRAC_CMD`               | Comandos customizados      |

---

# 🔧 Troubleshooting

### ❌ `Permission denied` em scripts `.sh`

Execute:

```bash
chmod +x db/*.sh scripts/*.sh
dos2unix db/*.sh scripts/*.sh
```

### ❌ `psql: command not found`

```bash
sudo apt update && sudo apt install postgresql-client
```

### ❌ Migrations não aplicadas

```bash
docker compose -f db/docker-compose.yml logs --tail=200 db
```

---

# 🧬 Banco de Dados

* DB central: **sync_apis**
* Schemas:

  * `auvo`
  * `e_track`
* Arquivos importantes:

  * `db/init/` — inicialização do container
  * `auvo/schema.sql`
  * `auvo/migrate_schema.sql`
  * `e-track/schema.sql`

