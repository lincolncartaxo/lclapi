# PreçosAPI / PreçosDB

Serviço independente do sistema de orçamentos para centralizar referências de preços de construção. O banco usa PostgreSQL e pode ser executado localmente ou em um projeto Supabase separado. Nenhuma tabela do banco de orçamentos é necessária.

## O que está incluído

- Schema normalizado para fontes, releases, regiões, itens, preços por UF/variante, composições, componentes e jobs de importação.
- Parser SINAPI para o pacote `.zip` de planilhas XLSX, incluindo insumos por estado, composições, variantes com/sem desoneração e componentes analíticos.
- Parser SICRO para o pacote `.7z`, extraindo relatórios XLSX de materiais, equipamentos, mão de obra e composições para a UF do pacote.
- Importação idempotente por SHA-256 do arquivo original; reprocessar o mesmo pacote não duplica o release.
- API REST em `/v1` e Swagger em `/docs`.
- CLI e modo `watch` para importar automaticamente arquivos novos em uma pasta.

## Execução local

```bash
cp .env.example .env
docker compose up -d
python -m venv .venv && . .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8080
```

Para usar Supabase separado, configure apenas `DATABASE_URL` com a connection string do projeto PreçosDB e aplique `migrations/001_initial.sql` no SQL Editor. Em produção, mantenha a chave/URL do projeto fora do frontend.

## Importação

Dry-run, sem escrever no banco:

```bash
python -m app.cli import fixtures/SINAPI-2026-08-formato-xlsx.zip --dry-run
python -m app.cli import fixtures/pb-07-2026.7z --dry-run
```

Importação persistente:

```bash
python -m app.cli import /caminho/SINAPI.zip
python -m app.cli import /caminho/SICRO.7z
```

Modo automático:

```bash
mkdir -p inbox
python -m app.cli watch inbox --interval 30
```

Também é possível enviar um pacote para `POST /v1/imports` como multipart `file`; use `?dry_run=true` para validar sem persistir.

## Endpoints principais

- `GET /health`
- `GET /v1/sources`
- `GET /v1/releases?source=SINAPI`
- `GET /v1/items?q=concreto&source=SINAPI&region=PB&reference=2026-08`
- `GET /v1/items/{codigo}/prices?source=SICRO&reference=2026-07`
- `POST /v1/imports`

## Decisões de normalização

`items` representa o código/descrição estável da fonte; `item_prices` representa o valor contextual por release, UF e variante. Uma composição é um item do tipo `COMPOSICAO` e seus insumos são registrados em `composition_components`, mantendo coeficiente, posição e dados brutos. Arquivos e linhas que não permitem determinar um preço são preservados em metadados/fixtures sem gerar valores artificiais.
