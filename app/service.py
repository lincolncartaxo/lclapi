from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text

from .core import SessionLocal
from .importers import ParsedRelease


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
        item_ids: dict[tuple[str, str], UUID] = {}
        for record in parsed.prices:
            item_id = _upsert_item(session, source_id, record.code, record.kind, record.description, record.unit, record.category)
            item_ids[(record.code, record.kind)] = item_id
            session.execute(text('''
                insert into item_prices(item_id, release_id, region_code, pricing_variant, price, price_origin, raw_data)
                values (:item_id, :release_id, :region, :variant, :price, :origin, cast(:raw as jsonb))
                on conflict(item_id, release_id, region_code, pricing_variant) do update set price=excluded.price, price_origin=excluded.price_origin, raw_data=excluded.raw_data
            '''), {'item_id': item_id, 'release_id': release_id, 'region': record.region_code or '', 'variant': record.variant, 'price': record.price, 'origin': record.origin, 'raw': _json(record.raw)})
        composition_ids: dict[str, UUID] = {}
        for record in parsed.components:
            composition_item_id = item_ids.get((record.composition_code, 'COMPOSICAO'))
            if composition_item_id is None:
                composition_item_id = _upsert_item(session, source_id, record.composition_code, 'COMPOSICAO', record.composition_code, None, parsed.source)
            composition_id = composition_ids.get(record.composition_code)
            if composition_id is None:
                composition_id = session.execute(text('''insert into compositions(item_id, release_id) values (:item, :release) returning id'''), {'item': composition_item_id, 'release': release_id}).scalar_one()
                composition_ids[record.composition_code] = composition_id
            component_id = item_ids.get((record.component_code, record.component_kind or 'INSUMO'))
            session.execute(text('''
                insert into composition_components(composition_id, component_item_id, component_code, component_kind, description, unit, coefficient, total_cost, position, raw_data)
                values (:composition, :component, :code, :kind, :description, :unit, :coefficient, :total_cost, :position, cast(:raw as jsonb))
                on conflict(composition_id, component_code, position) do update set coefficient=excluded.coefficient, total_cost=excluded.total_cost, raw_data=excluded.raw_data
            '''), {'composition': composition_id, 'component': component_id, 'code': record.component_code, 'kind': record.component_kind, 'description': record.description, 'unit': record.unit, 'coefficient': record.coefficient, 'total_cost': record.total_cost, 'position': record.position, 'raw': _json(record.raw)})
        return summary | {'release_id': str(release_id), 'skipped': False}


def _upsert_item(session, source_id: UUID, code: str, kind: str, description: str, unit: str | None, category: str | None) -> UUID:
    return session.execute(text('''
        insert into items(source_id, code, kind, description, unit, category)
        values (:source, :code, cast(:kind as item_kind), :description, :unit, :category)
        on conflict(source_id, code, kind) do update set description=excluded.description, unit=excluded.unit, category=excluded.category
        returning id
    '''), {'source': source_id, 'code': code, 'kind': kind, 'description': description, 'unit': unit, 'category': category}).scalar_one()


def _json(value: dict[str, Any]) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, default=str)


def import_path(path: str | Path, dry_run: bool = False) -> dict[str, Any]:
    from .importers import parse_file
    parsed = parse_file(Path(path))
    return persist_release(parsed, dry_run=dry_run)
