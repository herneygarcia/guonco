"""Auth tests: PIN login, roles, session cookies, attribution."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from src import auth
from src.db import init_db
from src.main import app

PINS = "jefe:1111,ayudante:2222:ro"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GUONCO_DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("APP_PINS", PINS)
    init_db()
    with TestClient(app) as c:
        yield c


def _login(client, code):
    return client.post("/api/login", json={"code": code})


def test_auth_disabled_without_pins(tmp_path, monkeypatch):
    monkeypatch.setenv("GUONCO_DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.delenv("APP_PINS", raising=False)
    init_db()
    with TestClient(app) as c:
        assert c.get("/api/records").status_code == 200
        assert c.post(
            "/api/records",
            json={"pathology": "pene", "fields": {"historia_clinica": "X1"}},
        ).status_code == 200
        sess = c.get("/api/session").json()
        assert sess["enabled"] is False


def test_api_requires_login(client):
    assert client.get("/api/pathologies").status_code == 401
    assert client.get("/api/records").status_code == 401


def test_login_rejects_bad_code(client):
    assert _login(client, "wrong").status_code == 401
    assert _login(client, "").status_code == 401
    assert _login(client, None).status_code == 401


def test_login_and_session_roundtrip(client):
    r = _login(client, "1111")
    assert r.status_code == 200
    assert r.json() == {"user": "jefe", "role": "rw"}
    assert "guonco_session" in r.cookies or any(
        c.name == "guonco_session" for c in client.cookies.jar
    )

    sess = client.get("/api/session").json()
    assert sess == {"enabled": True, "user": "jefe", "role": "rw"}

    # Authenticated API access works now.
    assert client.get("/api/pathologies").status_code == 200


def test_read_only_role_cannot_write(client):
    assert _login(client, "2222").json()["role"] == "ro"
    assert client.get("/api/records").status_code == 200  # read OK
    r = client.post(
        "/api/records",
        json={"pathology": "pene", "fields": {"historia_clinica": "RO-1"}},
    )
    assert r.status_code == 403
    assert client.delete("/api/records/nope").status_code == 403
    assert client.post("/api/sync").status_code == 403


def test_logout_clears_session(client):
    _login(client, "1111")
    assert client.get("/api/records").status_code == 200
    client.post("/api/logout")
    assert client.get("/api/records").status_code == 401


def test_record_attributed_to_writer(client):
    _login(client, "1111")
    r = client.post(
        "/api/records",
        json={
            "pathology": "pene",
            "fields": {"historia_clinica": "ATTR-1"},
        },
    )
    rec = r.json()
    assert rec["_creado_por"] == "jefe"
    assert rec["_actualizado_por"] == "jefe"

    rid = rec["_id"]
    up = client.put(f"/api/records/{rid}", json={"fields": {}})
    body = up.json()
    assert body["_creado_por"] == "jefe"      # creator preserved on update
    assert body["_actualizado_por"] == "jefe"


# ------------------------------------------------------------------ tokens --
def test_token_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("GUONCO_DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("APP_PINS", "ana:4321")
    init_db()
    token = auth.create_token("ana", "s3cret", ttl_s=60)
    assert auth.verify_token(token, "s3cret") == ("ana", "rw")


def test_tampered_or_wrong_secret_token_rejected():
    token = auth.create_token("ana", "s3cret", ttl_s=60)
    assert auth.verify_token(token + "x", "s3cret") is None
    assert auth.verify_token(token, "other") is None
    expired = auth.create_token("ana", "s3cret", ttl_s=-10)
    assert auth.verify_token(expired, "s3cret") is None


def test_removed_user_sessions_revoked(tmp_path, monkeypatch):
    monkeypatch.setenv("GUONCO_DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("APP_PINS", "ana:4321")
    token = auth.create_token("ana", "k", ttl_s=60)
    monkeypatch.setenv("APP_PINS", "")  # user removed
    assert auth.verify_token(token, "k") is None
