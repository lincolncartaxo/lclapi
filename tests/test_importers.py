from pathlib import Path

import pytest

from app.importers import parse_file

ROOT = Path(__file__).parents[1]


def test_sinapi_fixture_is_normalized():
    if not (ROOT / 'fixtures/SINAPI-2026-08-formato-xlsx.zip').exists():
        pytest.skip('fixture SINAPI não versionado; forneça-o localmente para o teste de integração')
    parsed = parse_file(ROOT / 'fixtures/SINAPI-2026-08-formato-xlsx.zip')
    assert parsed.source == 'SINAPI'
    assert parsed.reference_month.isoformat() == '2026-08-01'
    assert len(parsed.prices) > 800_000
    assert any(item.region_code == 'PB' for item in parsed.prices)
    assert any(item.kind == 'COMPOSICAO' for item in parsed.prices)
    assert len(parsed.components) > 10_000


def test_sicro_fixture_is_normalized():
    if not (ROOT / 'fixtures/pb-07-2026.7z').exists():
        pytest.skip('fixture SICRO não versionado; forneça-o localmente para o teste de integração')
    parsed = parse_file(ROOT / 'fixtures/pb-07-2026.7z')
    assert parsed.source == 'SICRO'
    assert parsed.reference_month.isoformat() == '2026-07-01'
    assert len(parsed.prices) > 9_000
    assert {item.kind for item in parsed.prices} >= {'MATERIAL', 'EQUIPAMENTO', 'MAO_DE_OBRA', 'COMPOSICAO'}
    assert all(item.region_code == 'PB' for item in parsed.prices)
