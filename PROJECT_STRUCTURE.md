# Estrutura

- `app/main.py`: API FastAPI `/health` e `/v1`.
- `app/importers.py`: parsers independentes SINAPI e SICRO; retorna registros normalizados em memória.
- `app/service.py`: persistência idempotente e upsert no PostgreSQL/Supabase.
- `app/cli.py`: importação pontual e watcher automático de inbox.
- `app/core.py`: configuração e conexão SQLAlchemy.
- `migrations/001_initial.sql`: schema do PreçosDB.
- `tests/test_importers.py`: testes com os arquivos SINAPI e SICRO anexados.
- `docker-compose.yml`: PostgreSQL local na porta 5433, separado da aplicação de orçamentos.

Os diretórios `fixtures/` e `extracted/` são apenas locais para validação e estão no `.gitignore`; os arquivos originais não são copiados para o banco do orçamento.
