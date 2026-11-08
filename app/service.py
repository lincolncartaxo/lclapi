from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text

from .core import SessionLocal
from .importers import ParsedRelease

BATCH_SIZE = 5000


def persist_release(parsed: ParsedRelease, dry_run: bool = False) -> dict[str, Any]:
    summary = {'source': parsed.source, 'reference': parsed.reference_month.isoformat(), 'prices': len(parsed.prices), 'components': len(parsed.components)}
    if dry_run:
        return summary | {'dry_run': True}
    with SessionLocal.begin() as session:
        source_id = session.execute(text('select id from sources where code = :code'), {'code': parsed.source}).scalar_one()
        existing = session.execute(text('select id from releases where source_id = :source_id and source_sha256 = :sha'), {'source_id': source_id, 'sha': parsed.sha256}).scalar_one_or_none()
        if existing:
            return summary | {'skipped': True, 'release_id': str(existing)}
        release_id = session.execute(text('''
            insert into releases(source_id, reference_month, region_code, title, source_file_name, source_sha256, metadata)
            values (:source_id, :reference_month, :region_code, :title, :file_name, :sha, cast(:metadata as jsonb)) returning id
        '''), {'source_id': source_id, 'reference_month': parsed.reference_month, 'region_code': '', 'title': parsed.title, 'file_name': parsed.source_file_name, 'sha': parsed.sha256, 'metadata': _json(parsed.metadata)}).scalar_one()

        item_rows: dict[tuple[str, str], dict[str, Any]] = {}
        for record in parsed.prices:
            item_rows.setdefault((record.code, record.kind), {'source': source_id, 'code': record.code, 'kind': record.kind, 'description': record.description, 'unit': record.unit, 'category': record.category})
        for record in parsed.components:
            item_rows.setdefault((record.composition_code, 'COMPOSICAO'), {'source': source_id, 'code': record.composition_code, 'kind': 'COMPOSICAO', 'description': record.composition_code, 'unit': None, 'category': parsed.source})
            component_kind = record.component_kind or 'INSUMO'
            item_rows.setdefault((record.component_code, component_kind), {'source': source_id, 'code': record.component_code, 'kind': component_kind, 'description': record.description or record.component_code, 'unit': record.unit, 'category': parsed.source})
        item_sql = text('''
            insert into items(source_id, code, kind, description, unit, category)
            values (:source, :code, cast(:kind as item_kind), :description, :unit, :category)
            on conflict(source_id, code, kind) do update set description=excluded.description, unit=excluded.unit, category=excluded.category
        ''')
        rows = list(item_rows.values())
        for batch in _batches(rows):
            session.execute(item_sql, batch)
        item_ids = {(row.code, row.kind): row.id for row in session.execute(text('select id, code, kind::text as kind from items where source_id=:source'), {'source': source_id})}

        price_sql = text('''
            insert into item_prices(item_id, release_id, region_code, pricing_variant, price, price_origin, raw_data)
            values (:item_id, :release_id, :region, :variant, :price, :origin, cast(:raw as jsonb))
            on conflict(item_id, release_id, region_code, pricing_variant) do update set price=excluded.price, price_origin=excluded.price_origin, raw_data=excluded.raw_data
        ''')
        price_rows = ({'item_id': item_ids[(r.code, r.kind)], 'release_id': release_id, 'region': r.region_code or '', 'variant': r.variant, 'price': r.price, 'origin': r.origin, 'raw': _json(r.raw)} for r in parsed.prices)
        for batch in _batches(price_rows):
            session.execute(price_sql, batch)

        composition_codes = sorted({r.composition_code for r in parsed.components})
        if composition_codes:
            composition_sql = text('''
                insert into compositions(item_id, release_id) values (:item, :release)
                on conflict(item_id) do update set release_id=excluded.release_id
            ''')
            composition_rows = ({'item': item_ids[(code, 'COMPOSICAO')], 'release': release_id} for code in composition_codes)
            for batch in _batches(composition_rows):
                session.execute(composition_sql, batch)
            composition_ids = {row.code: row.id for row in session.execute(text('''
                select i.code, c.id from compositions c join items i on i.id=c.item_id where c.release_id=:release
            '''), {'release': release_id})}
            component_sql = text('''
                insert into composition_components(composition_id, component_item_id, component_code, component_kind, description, unit, coefficient, total_cost, position, raw_data)
                values (:composition, :component, :code, :kind, :description, :unit, :coefficient, :total_cost, :position, cast(:raw as jsonb))
                on conflict(composition_id, component_code, position) do update set coefficient=excluded.coefficient, total_cost=excluded.total_cost, raw_data=excluded.raw_data
            ''')
            component_rows = ({'composition': composition_ids[r.composition_code], 'component': item_ids.get((r.component_code, r.component_kind or 'INSUMO')), 'code': r.component_code, 'kind': r.component_kind, 'description': r.description, 'unit': r.unit, 'coefficient': r.coefficient, 'total_cost': r.total_cost, 'position': r.position, 'raw': _json(r.raw)} for r in parsed.components)
            for batch in _batches(component_rows):
                session.execute(component_sql, batch)
        return summary | {'release_id': str(release_id), 'skipped': False}


def _batches(rows):
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH_SIZE:
            yield batch
            batch = []
    if batch:
        yield batch


def _json(value: dict[str, Any]) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, default=str)


def import_path(path: str | Path, dry_run: bool = False) -> dict[str, Any]:
    from .importers import parse_file
    parsed = parse_file(Path(path))
    return persist_release(parsed, dry_run=dry_run)
