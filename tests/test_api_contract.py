import os

os.environ.setdefault("API_KEY", "test-key")

from fastapi.testclient import TestClient

from app.main import app, db_source, public_source, variants_for


def test_source_alias_and_regime_variants():
    assert db_source("SICRO3") == "SICRO"
    assert public_source("SICRO") == "SICRO3"
    assert variants_for("desonerado")[0] == "COM_DESONERACAO"
    assert variants_for("nao_desonerado")[0] == "SEM_DESONERACAO"


def test_openapi_exposes_lclpo_contract_and_requires_key():
    client = TestClient(app, raise_server_exceptions=False)
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/v1/sources",
        "/v1/releases",
        "/v1/items",
        "/v1/catalog",
        "/v1/items/{code}/prices",
        "/v1/compositions/{code}",
        "/v1/compositions/{code}/cost",
        "/v1/imports",
    ):
        assert path in paths
    assert client.get("/v1/sources").status_code == 401
    assert client.get("/v1/sources", headers={"X-API-Key": "wrong"}).status_code == 401
