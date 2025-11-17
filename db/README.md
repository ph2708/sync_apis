DB (Postgres) — Centralized development instance
===============================================

Pasta `db/` contém a configuração e scripts para subir uma instância
Postgres usada por todos os projetos do monorepo em desenvolvimento.

Conteúdo relevante
- `docker-compose.yml` — define o serviço `db` (Postgres 15), mapeia a porta
  5432 e monta `./init` em `/docker-entrypoint-initdb.d` para executar os
  scripts de inicialização na primeira vez que o container for criado.
- `init/00_create_database_and_schemas.sql` — script que cria os schemas
  `auvo` e `e_track` e roles de exemplo (`auvo_user`, `etrack_user`).
- `apply-all-migrations.sh` (na raiz `db/`) — helper que aplica as migrations
  de ambos os projetos no database `sync_apis`.

Como funciona a inicialização
- Ao subir o container Postgres pela primeira vez, todos os arquivos em
  `/docker-entrypoint-initdb.d` são executados pelo entrypoint do Postgres.
  Por isso o script `00_create_database_and_schemas.sql` cria os schemas e
  roles necessários automaticamente.

Variáveis e customização
- O `docker-compose.yml` define `POSTGRES_USER`, `POSTGRES_PASSWORD` e
  `POSTGRES_DB` usados para inicializar o banco. Estes valores estão em
  `db/docker-compose.yml` e o `.env.example` na raiz mostra as variáveis de
  conexão que os projetos devem usar.
- Em produção não use senhas em texto; prefira Docker secrets ou outro
  mecanismo de gestão de credenciais.

Comandos úteis
-------------
- Subir o DB central (a partir da raiz do repositório):
  ```bash
  docker compose -f db/docker-compose.yml up -d
  ```
- Parar o DB:
  ```bash
  docker compose -f db/docker-compose.yml down
  ```
- Ver logs do DB:
  ```bash
  docker compose -f db/docker-compose.yml logs -f db
  ```

Notas finais
- Se você já tem um Postgres local e prefere não usar o compose, apenas
  garanta que as migrations sejam aplicadas no database `sync_apis` e que os
  projetos usem as mesmas variáveis PG*.

Comandos passo a passo: iniciar o DB, inspecionar, personalizar
1) A partir da raiz do repositório, inicie o serviço Postgres:

```bash
docker compose -f db/docker-compose.yml up -d
```

2) Aguarde e inspecione a prontidão:

```bash
docker compose -f db/docker-compose.yml ps
docker compose -f db/docker-compose.yml logs -f db
```

3) Se você quiser executar as migrations a partir da máquina host, mas não tem `psql`:
- Opção A (instalar psql no WSL):
  ```bash
  sudo apt update && sudo apt install -y postgresql-client
  ```

- Opção B (usar helper que executa psql dentro do container):
  ```bash
  ./db/apply-all-migrations.sh
  ```

4) Para alterar credenciais ou nome do DB, edite `db/docker-compose.yml` e os
   arquivos `db/init/*.sql` conforme necessário. Se você alterar o SQL de inicialização, remova o
   volume existente `db_data` ou redefina o diretório de dados para que os scripts
   de inicialização sejam executados novamente na primeira inicialização.

Nota sobre volumes e reinicialização
- A imagem do Postgres executa `docker-entrypoint-initdb.d` apenas em um diretório de banco de dados novo. Se você precisar reexecutar scripts de inicialização, remova o volume nomeado usado por `db/docker-compose.yml` (isso remove os dados):

```bash
docker compose -f db/docker-compose.yml down -v
docker volume rm sync_apis_db_data || true
docker compose -f db/docker-compose.yml up -d
```

