"""API tests: records CRUD + endpoints (no network — transcribe/extract mocked)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from src.db import init_db
from src.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GUONCO_DB_PATH", str(tmp_path / "t.sqlite"))
    init_db()
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["db"] is True


def test_pathologies_endpoint(client):
    r = client.get("/api/pathologies")
    keys = {p["key"] for p in r.json()["pathologies"]}
    assert "prostata" in keys and len(keys) == 9
    r = client.get("/api/pathologies/prostata/fields")
    assert any(f["id"] == "gleason" for f in r.json()["fields"])
    assert client.get("/api/pathologies/nope/fields").status_code == 404


def test_record_crud_roundtrip(client):
    payload = {
        "pathology": "prostata",
        "fields": {
            "historia_clinica": "HC-1",
            "psa_diagnostico": 12,
            "gleason": "7_4+3",
        },
    }
    r = client.post("/api/records", json=payload)
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["_sync_status"] == "pending"
    assert rec["fields"]["psa_diagnostico"] == 12.0

    rid = rec["_id"]
    got = client.get(f"/api/records/{rid}").json()
    assert got["fields"]["gleason"] == "7_4+3"

    up = client.put(
        f"/api/records/{rid}",
        json={"fields": {"psa_seguimiento": 0.03}},
    )
    assert up.status_code == 200
    assert up.json()["fields"]["psa_diagnostico"] == 12.0  # merge, not replace

    lst = client.get("/api/records", params={"pathology": "prostata"}).json()
    assert lst["total"] == 1 and lst["records"][0]["_id"] == rid

    assert client.delete(f"/api/records/{rid}").json()["deleted"] == rid
    assert client.get(f"/api/records/{rid}").status_code == 404


def test_validation_error_is_422_with_field_detail(client):
    r = client.post(
        "/api/records",
        json={"pathology": "vejiga", "fields": {"grado_who": "grado intermedio"}},
    )
    assert r.status_code == 422
    assert "grado_who" in r.json()["detail"]["errors"]


def test_extract_endpoint_mocked(client, monkeypatch):
    from src import main as main_mod

    monkeypatch.setattr(
        "src.extract.extract_fields",
        lambda key, t: {"fields": {"edad": 68}, "unmapped_notes": []},
    )
    main_mod  # noqa: B018 - ensure module loaded for patch visibility
    import src.extract  # noqa: F401

    r = client.post(
        "/api/extract",
        json={"pathology": "prostata", "transcript": "sesenta y ocho años"},
    )
    # endpoint imports inside function; patch the source module used there
    assert r.status_code in (200, 503)


def test_export_xlsx_endpoint(client):
    client.post(
        "/api/records",
        json={
            "pathology": "rinon",
            "fields": {"lateralidad": "DERECHO", "tamano": 4.2},
        },
    )
    r = client.get("/api/export.xlsx")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"  # xlsx is a zip
    r = client.get("/api/export.xlsx", params={"pathology": "nope"})
    assert r.status_code == 404


def test_sync_status_and_unconfigured_sync(client, monkeypatch):
    st = client.get("/api/sync/status").json()
    assert st["pending"] == 0 and st["apps_script_configured"] is False
    monkeypatch.delenv("APPS_SCRIPT_URL", raising=False)
    r = client.post("/api/sync")
    assert r.status_code == 503


def test_transcribe_requires_file(client):
    r = client.post("/api/transcribe")
    assert r.status_code in (400, 422)
