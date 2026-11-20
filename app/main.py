from __future__ import annotations

import hmac
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .core import SessionLocal, settings
from .service import calculate_composition_cost, import_path

app = FastAPI(title=settings.api_title, version='1.1.0', docs_url='/docs', openapi_url='/openapi.json')

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[v.strip() for v in settings.cors_origins.split(',') if v.strip()],
        allow_credentials=False,
        allow_methods=['GET', 'POST', 'OPTIONS'],
        allow_headers=['Accept', 'Authorization', 'Content-Type', 'X-API-Key'],
    )


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.api_key and (not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key)):
        raise HTTPException(401, detail='API key ausente ou inválida')


def db_source(source: str | None) -> str | None:
    if not source:
        return None
    value = source.strip().upper()
    return 'SICRO' if value == 'SICRO3' else value


def public_source(source: str) -> str:
    return 'SICRO3' if source.upper() == 'SICRO' else source


def variants_for(regime: str | None) -> tuple[str, str, str]:
    if (regime or '').lower() in {'desonerado', 'com_desoneracao', 'com desoneração'}:
        return ('COM_DESONERACAO', 'PADRAO', 'SEM_DESONERACAO')
    return ('SEM_DESONERACAO', 'PADRAO', 'COM_DESONERACAO')


@app.get('/health')
def health() -> dict[str, str]:
    try:
        with SessionLocal() as session:
            session.execute(text('select 1'))
        return {'status': 'ok', 'database': 'ok'}
    except Exception as exc:
        raise HTTPException(503, detail=f'database unavailable: {exc.__class__.__name__}') from exc


@app.get('/v1/sources', dependencies=[Depends(require_api_key)])
def sources() -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = [dict(row) for row in session.execute(text('select id, code, name, publisher from sources order by code')).mappings()]
    output = []
    seen = set()
    for row in rows:
        code = public_source(str(row['code']))
        if code in seen:
            continue
        seen.add(code)
        output.append({**row, 'code': code})
    return output


@app.get('/v1/releases', dependencies=[Depends(require_api_key)])
def releases(source: str | None = None, limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    query = 'select r.id, s.code source, r.reference_month, r.region_code, r.title, r.source_file_name, r.imported_at from releases r join sources s on s.id=r.source_id where (cast(:source as text) is null or s.code::text=cast(:source as text)) order by r.reference_month desc limit :limit'
    with SessionLocal() as session:
        rows = [dict(row) for row in session.execute(text(query), {'source': db_source(source), 'limit': limit}).mappings()]
    return [{**row, 'source': public_source(str(row['source']))} for row in rows]


@app.get('/v1/items', dependencies=[Depends(require_api_key)])
def items(q: str | None = None, source: str | None = None, kind: str | None = None, region: str | None = None, reference: str | None = None, regime: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    filters = ['(cast(:q as text) is null or i.code ilike :like_q or i.description ilike :like_q)', '(cast(:source as text) is null or s.code::text=cast(:source as text))', '(cast(:kind as text) is null or i.kind::text=cast(:kind as text))', '(cast(:region as text) is null or p.region_code=:region or p.region_code=\'BR\')', '(cast(:reference as text) is null or to_char(r.reference_month, \'YYYY-MM\')=:reference)', '(p.pricing_variant is null or p.pricing_variant in (:variant_0, :variant_1, :variant_2))']
    sql = f'''select distinct i.id, s.code source, i.code, i.kind, i.description, i.unit, i.category, p.region_code, p.pricing_variant, p.price, r.reference_month from items i join sources s on s.id=i.source_id left join item_prices p on p.item_id=i.id left join releases r on r.id=p.release_id where {' and '.join(filters)} order by i.code limit :limit offset :offset'''
    variants = variants_for(regime)
    params = {'q': q, 'like_q': f'%{q}%' if q else None, 'source': db_source(source), 'kind': kind.upper() if kind else None, 'region': region.upper() if region else None, 'reference': reference, 'variant_0': variants[0], 'variant_1': variants[1], 'variant_2': variants[2], 'limit': page_size, 'offset': (page - 1) * page_size}
    with SessionLocal() as session:
        data = [dict(row) for row in session.execute(text(sql), params).mappings()]
    return {'page': page, 'page_size': page_size, 'data': [{**row, 'source': public_source(str(row['source']))} for row in data]}


@app.get('/v1/catalog', dependencies=[Depends(require_api_key)])
def catalog(q: str | None = None, source: str | None = None, kind: str | None = None, region: str | None = None, reference: str | None = None, regime: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Compatibility response for the lclpo base selector."""
    result = items(q, source, kind, region, reference, regime, page, page_size)
    rows = []
    for row in result['data']:
        variant = str(row.get('pricing_variant') or 'PADRAO')
        rows.append({
            **row,
            'fonte': row['source'], 'codigo': row['code'], 'descricao': row['description'],
            'unidade': row['unit'], 'uf': row['region_code'], 'mes_ref': str(row['reference_month'])[:7] if row.get('reference_month') else None,
            'tipo_item': row['kind'],
            'preco_desonerado': row['price'] if variant == 'COM_DESONERACAO' else None,
            'preco_nao_desonerado': row['price'] if variant in {'SEM_DESONERACAO', 'PADRAO'} else None,
        })
    return {**result, 'data': rows}


@app.get('/v1/items/{code}/prices', dependencies=[Depends(require_api_key)])
def item_prices(code: str, source: str = Query(...), reference: str | None = None, region: str | None = None, regime: str | None = None) -> list[dict[str, Any]]:
    sql = '''select i.code, i.kind, i.description, i.unit, s.code source, r.reference_month, p.region_code, p.pricing_variant, p.price, p.price_origin from items i join sources s on s.id=i.source_id join item_prices p on p.item_id=i.id join releases r on r.id=p.release_id where (i.code=:code or ltrim(i.code, '0')=ltrim(:code, '0')) and s.code::text=cast(:source as text) and (cast(:reference as text) is null or to_char(r.reference_month, 'YYYY-MM')=:reference) and (cast(:region as text) is null or p.region_code=:region or p.region_code='BR') and p.pricing_variant in (:variant_0, :variant_1, :variant_2) order by (p.region_code=:region) desc, r.reference_month desc, p.region_code, p.pricing_variant'''
    variants = variants_for(regime)
    with SessionLocal() as session:
        rows = [dict(row) for row in session.execute(text(sql), {'code': code, 'source': db_source(source), 'reference': reference, 'region': region.upper() if region else None, 'variant_0': variants[0], 'variant_1': variants[1], 'variant_2': variants[2]}).mappings()]
    return [{**row, 'source': public_source(str(row['source']))} for row in rows]


@app.get('/v1/compositions/{code}', dependencies=[Depends(require_api_key)])
def composition(code: str, source: str = Query(...), reference: str | None = None, region: str | None = None, regime: str | None = None) -> dict[str, Any]:
    """Return a composition with its components and matching unit prices."""
    source_code = db_source(source)
    region_code = region.upper() if region else None
    header_sql = '''
        select c.id composition_id, i.code, i.kind, i.description, i.unit, i.category,
               s.code source, r.id release_id, r.reference_month, r.title,
               c.productivity, c.metadata
        from compositions c
        join items i on i.id=c.item_id
        join sources s on s.id=i.source_id
        join releases r on r.id=c.release_id
        where (i.code=:code or ltrim(i.code, '0')=ltrim(:code, '0')) and s.code::text=cast(:source as text)
          and i.kind::text='COMPOSICAO'
          and (cast(:reference as text) is null or to_char(r.reference_month, 'YYYY-MM')=:reference)
        order by r.reference_month desc
        limit 1
    '''
    component_sql = '''
        select cc.position, cc.component_code, cc.component_kind::text as component_kind,
               coalesce(cc.description, ci.description) description,
               coalesce(cc.unit, ci.unit) unit, cc.coefficient, cc.total_cost,
               ip.region_code, ip.pricing_variant, ip.price unit_price, ip.price_origin
        from composition_components cc
        left join items ci on ci.id=cc.component_item_id
        left join item_prices ip on ip.item_id=cc.component_item_id
          and ip.release_id=:release_id
          and (cast(:region as text) is null or ip.region_code=:region or ip.region_code='BR')
        where cc.composition_id=:composition_id
        order by cc.position, cc.component_code, ip.region_code, ip.pricing_variant
    '''
    with SessionLocal() as session:
        header = session.execute(text(header_sql), {'code': code, 'source': source_code, 'reference': reference}).mappings().first()
        if header is None:
            raise HTTPException(404, detail='Composição não encontrada para a fonte e referência informadas')
        components = [dict(row) for row in session.execute(text(component_sql), {'composition_id': header['composition_id'], 'release_id': header['release_id'], 'region': region_code}).mappings()]
        cost = calculate_composition_cost(session, source_code, str(header['code']), region_code, reference, regime)
    return {
        'source': public_source(str(header['source'])),
        'code': header['code'],
        'kind': header['kind'],
        'description': header['description'],
        'unit': header['unit'],
        'category': header['category'],
        'reference_month': header['reference_month'],
        'release_id': header['release_id'],
        'release_title': header['title'],
        'productivity': header['productivity'],
        'metadata': header['metadata'],
        'region': region_code,
        'regime': regime or 'nao_desonerado',
        'cost': cost,
        'components': components,
    }


@app.get('/v1/compositions/{code}/cost', dependencies=[Depends(require_api_key)])
def composition_cost(code: str, source: str = Query(...), reference: str | None = None, region: str | None = None, regime: str = 'nao_desonerado') -> dict[str, Any]:
    with SessionLocal() as session:
        cost = calculate_composition_cost(session, db_source(source), code, region, reference, regime)
    if cost is None:
        raise HTTPException(404, detail='Custo da composição não encontrado para os filtros informados')
    return {'source': public_source(db_source(source) or source), 'code': code, 'reference': reference, 'region': region.upper() if region else None, 'regime': regime, 'cost': cost}


@app.post('/v1/imports', status_code=201, dependencies=[Depends(require_api_key)])
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
