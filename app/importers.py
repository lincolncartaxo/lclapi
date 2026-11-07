from __future__ import annotations

import hashlib
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import openpyxl
import py7zr


UF_NAMES = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas', 'BA': 'Bahia',
    'CE': 'Ceará', 'DF': 'Distrito Federal', 'ES': 'Espírito Santo', 'GO': 'Goiás',
    'MA': 'Maranhão', 'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais',
    'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná', 'PE': 'Pernambuco', 'PI': 'Piauí',
    'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte', 'RS': 'Rio Grande do Sul',
    'RO': 'Rondônia', 'RR': 'Roraima', 'SC': 'Santa Catarina', 'SP': 'São Paulo',
    'SE': 'Sergipe', 'TO': 'Tocantins',
}


@dataclass
class PriceRecord:
    code: str
    kind: str
    description: str
    unit: str | None
    category: str | None
    region_code: str | None
    variant: str
    price: float
    origin: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentRecord:
    composition_code: str
    component_code: str
    component_kind: str | None
    description: str | None
    unit: str | None
    coefficient: float | None
    total_cost: float | None
    position: int
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedRelease:
    source: str
    reference_month: date
    title: str
    source_file_name: str
    sha256: str
    prices: list[PriceRecord] = field(default_factory=list)
    components: list[ComponentRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def rows_read(self) -> int:
        return len(self.prices) + len(self.components)


def _text(value: Any) -> str:
    return re.sub(r'\s+', ' ', str('' if value is None else value).replace('\xa0', ' ')).strip()


def _key(value: Any) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', _text(value).lower()) if not unicodedata.combining(c))


def _number(value: Any) -> float | None:
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = _text(value).replace('R$', '').replace(' ', '')
    if not raw:
        return None
    if ',' in raw and '.' in raw:
        raw = raw.replace('.', '').replace(',', '.')
    else:
        raw = raw.replace(',', '.')
    try:
        return float(raw)
    except ValueError:
        return None


def _reference(text: str) -> date:
    m = re.search(r'(20\d{2})[^0-9]?((?:0?[1-9])|(?:1[0-2]))', text)
    if not m:
        m = re.search(r'((?:0?[1-9])|(?:1[0-2]))[^0-9]?(20\d{2})', text)
        return date(int(m.group(2)), int(m.group(1)), 1) if m else date.today().replace(day=1)
    return date(int(m.group(1)), int(m.group(2)), 1)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _header_row(ws, max_scan: int = 40) -> tuple[int, list[str]]:
    for index, row in enumerate(ws.iter_rows(min_row=1, max_row=min(max_scan, ws.max_row), values_only=True), 1):
        values = [_text(value) for value in row]
        joined = ' | '.join(values).lower()
        if ('código' in joined or 'codigo' in joined) and ('descrição' in joined or 'descricao' in joined):
            return index, values
    raise ValueError(f'Cabeçalho não encontrado na aba {ws.title!r}')


def parse_sinapi(path: Path) -> ParsedRelease:
    extracted: list[Path] = []
    if path.suffix.lower() == '.zip':
        temp = path.parent / f'.{path.stem}_unzipped'
        temp.mkdir(exist_ok=True)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(temp)
        extracted = list(temp.glob('*.xlsx'))
    else:
        extracted = [path]
    if not extracted:
        raise ValueError('ZIP SINAPI sem planilhas XLSX')

    reference = date.today().replace(day=1)
    prices: list[PriceRecord] = []
    components: list[ComponentRecord] = []
    metadata: dict[str, Any] = {'files': [p.name for p in extracted]}

    for workbook_path in extracted:
        wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            if 'familias' in _key(workbook_path.name) or 'coeficientes' in _key(ws.title):
                continue
            # A referência oficial aparece nos metadados das primeiras linhas.
            for row in ws.iter_rows(min_row=1, max_row=min(5, ws.max_row), values_only=True):
                row_text = ' '.join(_text(v) for v in row)
                if 'Referência' in row_text or 'Referencia' in row_text:
                    reference = _reference(row_text)
            try:
                header_index, headers = _header_row(ws)
            except ValueError:
                continue
            normalized = [re.sub(r'[^a-z0-9]+', ' ', _key(h)).strip() for h in headers]
            def find(*terms: str) -> int | None:
                for i, h in enumerate(normalized):
                    if any(term in h for term in terms): return i
                return None
            code_i = find('codigo do insumo', 'codigo da composicao', 'codigo')
            desc_i = find('descricao do insumo', 'descricao')
            unit_i = find('unidade')
            if code_i is None or desc_i is None:
                continue
            sheet_name = ws.title
            is_analytic = 'analítico' in sheet_name.lower() or 'analitico' in sheet_name.lower()
            is_composition_summary = any(x in sheet_name.upper() for x in ('CSD', 'CCD', 'CSE'))
            uf_indexes = {h: i for i, h in enumerate(headers) if _text(h).upper() in UF_NAMES}
            if is_composition_summary:
                region_row = list(next(ws.iter_rows(min_row=header_index - 1, max_row=header_index - 1, values_only=True)))
                uf_indexes = {
                    _text(region_row[i]).upper(): i
                    for i in range(4, len(region_row), 2)
                    if _text(region_row[i]).upper() in UF_NAMES
                }
            variant = 'COM_DESONERACAO' if sheet_name.upper() in ('ICD', 'CCD') or 'COM DESONERA' in workbook_path.name.upper() else 'SEM_DESONERACAO' if sheet_name.upper() in ('ISD', 'CSD') or 'SEM DESONERA' in workbook_path.name.upper() else 'PADRAO'
            for row_number, row in enumerate(ws.iter_rows(min_row=header_index + 1, values_only=True), header_index + 1):
                values = list(row)
                code = _text(values[code_i] if code_i < len(values) else '')
                if code in ('', '0') and is_composition_summary:
                    code = f'{sheet_name}:{row_number}'
                desc = _text(values[desc_i] if desc_i < len(values) else '')
                if not code or not desc:
                    continue
                unit = _text(values[unit_i]) if unit_i is not None and unit_i < len(values) else None
                kind = 'COMPOSICAO' if ('composi' in sheet_name.lower() or 'composi' in workbook_path.name.lower() or (code[:1].isdigit() and is_composition_summary)) else 'INSUMO'
                if is_analytic:
                    composition_code = code
                    # A linha analítica alterna composição e seus componentes; somente linhas com tipo item são componentes.
                    type_i = find('tipo item')
                    component_code_i = find('codigo do item')
                    if type_i is not None and component_code_i is not None and _text(values[type_i]).upper() not in ('', 'COMPOSICAO'):
                        components.append(ComponentRecord(composition_code, _text(values[component_code_i]), _text(values[type_i]).upper(), desc, unit, _number(values[find('coeficiente')]) if find('coeficiente') is not None else None, None, row_number, {'sheet': sheet_name}))
                    continue
                if is_composition_summary and uf_indexes:
                    # Relatórios C* repetem Custo e %AS por UF, iniciando na coluna E.
                    for uf, uf_idx in uf_indexes.items():
                        value = _number(values[uf_idx]) if uf_idx < len(values) else None
                        if value is not None:
                            prices.append(PriceRecord(code, 'COMPOSICAO', desc, unit, 'SINAPI', uf, variant, value, sheet_name, {'row': row_number, 'sheet': sheet_name}))
                elif uf_indexes:
                    for uf, uf_idx in uf_indexes.items():
                        value = _number(values[uf_idx]) if uf_idx < len(values) else None
                        if value is not None:
                            prices.append(PriceRecord(code, kind, desc, unit, 'SINAPI', uf, variant, value, sheet_name, {'row': row_number, 'sheet': sheet_name}))
                else:
                    # Manutenções e relatórios auxiliares: preserva o item sem inventar preço.
                    continue
    return ParsedRelease('SINAPI', reference, f'SINAPI {reference:%m/%Y}', path.name, _sha256(path), prices, components, metadata)


def parse_sicro(path: Path) -> ParsedRelease:
    extracted = path.parent / f'.{path.stem}_unzipped'
    extracted.mkdir(exist_ok=True)
    with py7zr.SevenZipFile(path, 'r') as archive:
        archive.extractall(extracted)
    reference = _reference(path.name)
    prices: list[PriceRecord] = []
    components: list[ComponentRecord] = []
    files = list(extracted.glob('*.xlsx'))
    for workbook_path in files:
        wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            try:
                header_index, headers = _header_row(ws)
            except ValueError:
                continue
            norm = [re.sub(r'[^a-z0-9]+', ' ', _key(h)).strip() for h in headers]
            def idx(*terms: str) -> int | None:
                for i, h in enumerate(norm):
                    if any(t in h for t in terms): return i
                return None
            code_i, desc_i, unit_i = idx('codigo'), idx('descricao'), idx('unidade')
            price_i = idx('custo unitario', 'custo r', 'preco unitario', 'custo')
            if code_i is None or desc_i is None:
                continue
            filename = workbook_path.name.upper()
            if 'COMPOSIÇÕES DE CUSTOS' in filename and 'SINTÉTICO' in filename:
                kind, category = 'COMPOSICAO', 'SICRO'
            elif 'MATERIAIS' in filename:
                kind, category = 'MATERIAL', 'SICRO'
            elif 'EQUIPAMENTOS' in filename:
                kind, category = 'EQUIPAMENTO', 'SICRO'
            elif 'MÃO DE OBRA' in filename:
                kind, category = 'MAO_DE_OBRA', 'SICRO'
            else:
                continue
            for row_number, row in enumerate(ws.iter_rows(min_row=header_index + 1, values_only=True), header_index + 1):
                values = list(row)
                code, desc = _text(values[code_i]), _text(values[desc_i])
                if not code or not desc:
                    continue
                unit = _text(values[unit_i]) if unit_i is not None and unit_i < len(values) else None
                price = _number(values[price_i]) if price_i is not None and price_i < len(values) else None
                if price is not None:
                    prices.append(PriceRecord(code, kind, desc, unit, category, 'PB', 'PADRAO', price, workbook_path.name, {'row': row_number}))
    return ParsedRelease('SICRO', reference, f'SICRO {reference:%m/%Y}', path.name, _sha256(path), prices, components, {'files': [p.name for p in files], 'region': 'PB'})


def parse_file(path: Path) -> ParsedRelease:
    suffix = path.suffix.lower()
    if suffix == '.7z': return parse_sicro(path)
    if suffix in ('.zip', '.xlsx'): return parse_sinapi(path)
    raise ValueError(f'Formato não suportado: {path.suffix}')
