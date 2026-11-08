from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from sqlalchemy import text

from .core import SessionLocal, settings
from .service import import_path

app = FastAPI(title=settings.api_title, version='1.0.0', docs_url='/docs', openapi_url='/openapi.json')


@app.get('/health')
def health() -> dict[str, str]:
    try:
        with SessionLocal() as session:
            session.execute(text('select 1'))
        return {'status': 'ok', 'database': 'ok'}
    except Exception as exc:
        raise HTTPException(503, detail=f'database unavailable: {exc.__class__.__name__}') from exc


@app.get('/v1/sources')
def sources() -> list[dict[str, Any]]:
    with SessionLocal() as session:
        return [dict(row) for row in session.execute(text('select id, code, name, publisher from sources order by code')).mappings()]


@app.get('/v1/releases')
def releases(source: str | None = None, limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    query = 'select r.id, s.code source, r.reference_month, r.region_code, r.title, r.source_file_name, r.imported_at from releases r join sources s on s.id=r.source_id where (cast(:source as text) is null or s.code::text=cast(:source as text)) order by r.reference_month desc limit :limit'
    with SessionLocal() as session:
        return [dict(row) for row in session.execute(text(query), {'source': source.upper() if source else None, 'limit': limit}).mappings()]


@app.get('/v1/items')
def items(q: str | None = None, source: str | None = None, kind: str | None = None, region: str | None = None, reference: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    filters = ['(cast(:q as text) is null or i.code ilike :like_q or i.description ilike :like_q)', '(cast(:source as text) is null or s.code::text=cast(:source as text))', '(cast(:kind as text) is null or i.kind::text=cast(:kind as text))', '(cast(:region as text) is null or p.region_code=:region)', '(cast(:reference as text) is null or to_char(r.reference_month, \'YYYY-MM\')=:reference)']
    sql = f'''select distinct i.id, s.code source, i.code, i.kind, i.description, i.unit, i.category, p.region_code, p.pricing_variant, p.price, r.reference_month from items i join sources s on s.id=i.source_id left join item_prices p on p.item_id=i.id left join releases r on r.id=p.release_id where {' and '.join(filters)} order by i.code limit :limit offset :offset'''
    params = {'q': q, 'like_q': f'%{q}%' if q else None, 'source': source.upper() if source else None, 'kind': kind.upper() if kind else None, 'region': region.upper() if region else None, 'reference': reference, 'limit': page_size, 'offset': (page - 1) * page_size}
    with SessionLocal() as session:
        data = [dict(row) for row in session.execute(text(sql), params).mappings()]
    return {'page': page, 'page_size': page_size, 'data': data}


@app.get('/v1/items/{code}/prices')
def item_prices(code: str, source: str = Query(...), reference: str | None = None) -> list[dict[str, Any]]:
    sql = '''select i.code, i.kind, i.description, i.unit, s.code source, r.reference_month, p.region_code, p.pricing_variant, p.price, p.price_origin from items i join sources s on s.id=i.source_id join item_prices p on p.item_id=i.id join releases r on r.id=p.release_id where i.code=:code and s.code::text=cast(:source as text) and (cast(:reference as text) is null or to_char(r.reference_month, 'YYYY-MM')=:reference) order by p.region_code, p.pricing_variant'''
    with SessionLocal() as session:
        return [dict(row) for row in session.execute(text(sql), {'code': code, 'source': source.upper(), 'reference': reference}).mappings()]


@app.post('/v1/imports', status_code=201)
async def import_file(file: UploadFile = File(...), dry_run: bool = False) -> dict[str, Any]:
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in {'.zip', '.7z', '.xlsx'}:
        raise HTTPException(415, detail='Envie .zip, .7z ou .xlsx')
    with tempfile.NamedTemporaryFile(prefix='precos-', suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        temp_path = tmp.name
    try:
        return import_path(temp_path, dry_run=dry_run)
    except Exception as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    finally:
        Path(temp_path).unlink(missing_ok=True)
