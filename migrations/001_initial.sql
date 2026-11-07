create extension if not exists pgcrypto;

create type source_kind as enum ('SINAPI', 'SICRO');
create type item_kind as enum ('INSUMO', 'COMPOSICAO', 'EQUIPAMENTO', 'MAO_DE_OBRA', 'MATERIAL', 'OUTRO');
create type import_status as enum ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED');

create table if not exists sources (
  id uuid primary key default gen_random_uuid(),
  code source_kind not null unique,
  name text not null,
  publisher text not null,
  created_at timestamptz not null default now()
);

create table if not exists releases (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references sources(id),
  reference_month date not null,
  region_code varchar(8),
  title text,
  source_file_name text not null,
  source_sha256 char(64) not null,
  metadata jsonb not null default '{}'::jsonb,
  imported_at timestamptz not null default now(),
  unique(source_id, reference_month, region_code, source_sha256)
);

create table if not exists regions (
  code varchar(8) primary key,
  name text not null,
  region_type varchar(16) not null default 'UF'
);

create table if not exists items (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references sources(id),
  code varchar(64) not null,
  kind item_kind not null,
  description text not null,
  unit varchar(32),
  category text,
  searchable tsvector generated always as (to_tsvector('simple', coalesce(code,'') || ' ' || coalesce(description,''))) stored,
  created_at timestamptz not null default now(),
  unique(source_id, code, kind)
);

create index if not exists items_search_idx on items using gin(searchable);
create index if not exists items_code_idx on items(source_id, code);

create table if not exists item_prices (
  id uuid primary key default gen_random_uuid(),
  item_id uuid not null references items(id) on delete cascade,
  release_id uuid not null references releases(id) on delete cascade,
  region_code varchar(8) references regions(code),
  pricing_variant varchar(32) not null default 'PADRAO',
  price numeric(18,8) not null,
  price_origin text,
  raw_data jsonb not null default '{}'::jsonb,
  unique(item_id, release_id, region_code, pricing_variant)
);

create table if not exists compositions (
  id uuid primary key default gen_random_uuid(),
  item_id uuid not null unique references items(id) on delete cascade,
  release_id uuid not null references releases(id) on delete cascade,
  productivity numeric(18,8),
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists composition_components (
  id uuid primary key default gen_random_uuid(),
  composition_id uuid not null references compositions(id) on delete cascade,
  component_item_id uuid references items(id),
  component_code varchar(64) not null,
  component_kind item_kind,
  description text,
  unit varchar(32),
  coefficient numeric(18,8),
  total_cost numeric(18,8),
  position integer not null default 0,
  raw_data jsonb not null default '{}'::jsonb,
  unique(composition_id, component_code, position)
);

create table if not exists import_jobs (
  id uuid primary key default gen_random_uuid(),
  source_id uuid references sources(id),
  file_name text not null,
  sha256 char(64) not null,
  status import_status not null default 'PENDING',
  dry_run boolean not null default false,
  rows_read integer not null default 0,
  rows_written integer not null default 0,
  errors_count integer not null default 0,
  summary jsonb not null default '{}'::jsonb,
  error_message text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists prices_lookup_idx on item_prices(release_id, region_code, pricing_variant);
create index if not exists composition_components_lookup_idx on composition_components(composition_id, position);

insert into sources(code, name, publisher) values
 ('SINAPI', 'Sistema Nacional de Pesquisa de Custos e Índices da Construção Civil', 'CAIXA/IBGE'),
 ('SICRO', 'Sistema de Custos Referenciais de Obras', 'DNIT')
on conflict (code) do nothing;
