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
    assert sess == {
        "enabled": True,
        "user": "jefe",
        "role": "rw",
        "pin_enabled": True,
        "google_client_id": None,
    }

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


# ------------------------------------------------------------------ google --
CLIENT_ID = "test-client.apps.googleusercontent.com"
GOOGLE_USERS = "dra.prueba@example.org,Residente.Prueba@example.org:ro"


@pytest.fixture()
def gclient(tmp_path, monkeypatch):
    """Google-only auth; the token verifier is stubbed (no network).
    The fake credential string is "<email>|<verified 0/1>" or "bad"."""
    from google.oauth2 import id_token

    def fake_verify(credential, _request, audience):
        assert audience == CLIENT_ID
        if credential == "bad":
            raise ValueError("invalid token")
        email, verified = credential.split("|")
        return {"email": email, "email_verified": verified == "1"}

    monkeypatch.setattr(id_token, "verify_oauth2_token", fake_verify)
    monkeypatch.setenv("GUONCO_DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_USERS", GOOGLE_USERS)
    init_db()
    with TestClient(app) as c:
        yield c


def _glogin(client, credential):
    return client.post("/api/login/google", json={"credential": credential})


def test_google_only_enforces_auth_and_advertises_client(gclient):
    assert gclient.get("/api/records").status_code == 401
    sess = gclient.get("/api/session").json()
    assert sess["enabled"] is True
    assert sess["pin_enabled"] is False
    assert sess["google_client_id"] == CLIENT_ID


def test_google_writer_can_write(gclient):
    r = _glogin(gclient, "Dra.Prueba@example.org|1")
    assert r.status_code == 200
    assert r.json() == {"user": "dra.prueba@example.org", "role": "rw"}
    rec = gclient.post(
        "/api/records",
        json={"pathology": "pene", "fields": {"historia_clinica": "G-1"}},
    ).json()
    assert rec["_creado_por"] == "dra.prueba@example.org"


def test_google_read_only_cannot_write(gclient):
    assert _glogin(gclient, "residente.prueba@example.org|1").json()["role"] == "ro"
    assert gclient.get("/api/records").status_code == 200
    r = gclient.post(
        "/api/records",
        json={"pathology": "pene", "fields": {"historia_clinica": "G-2"}},
    )
    assert r.status_code == 403


@pytest.mark.parametrize(
    "credential",
    ["intruso@example.org|1", "dra.prueba@example.org|0", "bad", ""],
)
def test_google_login_rejected(gclient, credential):
    assert _glogin(gclient, credential).status_code == 401
    assert gclient.get("/api/records").status_code == 401


def test_google_login_needs_client_id(gclient, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    assert _glogin(gclient, "dra.prueba@example.org|1").status_code == 401


def test_removed_google_user_session_revoked(gclient, monkeypatch):
    # Fixed secret, so revocation comes from the allowlist, not a new secret.
    monkeypatch.setenv("SESSION_SECRET", "fixed")
    _glogin(gclient, "dra.prueba@example.org|1")
    assert gclient.get("/api/records").status_code == 200
    monkeypatch.setenv("GOOGLE_USERS", "residente.prueba@example.org:ro")
    assert gclient.get("/api/records").status_code == 401


def test_pin_and_google_coexist(gclient, monkeypatch):
    monkeypatch.setenv("APP_PINS", "jefe:1111")
    assert gclient.get("/api/session").json()["pin_enabled"] is True
    assert _login(gclient, "1111").status_code == 200
    assert _glogin(gclient, "dra.prueba@example.org|1").status_code == 200


DOMAIN_USERS = "jefa@uni.example.edu,@uni.example.edu:ro,@hospital.example.org"


def test_google_domain_entries(gclient, monkeypatch):
    monkeypatch.setenv("GOOGLE_USERS", DOMAIN_USERS)
    # Any account of a listed domain gets that domain's role.
    assert _glogin(gclient, "otro@uni.example.edu|1").json()["role"] == "ro"
    assert _glogin(gclient, "medico@hospital.example.org|1").json()["role"] == "rw"
    # An exact email overrides its domain.
    assert _glogin(gclient, "Jefa@Uni.Example.edu|1").json()["role"] == "rw"


@pytest.mark.parametrize(
    "email",
    ["x@fake-uni.example.edu", "x@sub.uni.example.edu", "x@uni.example.edu.co"],
)
def test_google_domain_match_is_exact(gclient, monkeypatch, email):
    monkeypatch.setenv("GOOGLE_USERS", DOMAIN_USERS)
    assert _glogin(gclient, f"{email}|1").status_code == 401


def test_removed_domain_session_revoked(gclient, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "fixed")
    monkeypatch.setenv("GOOGLE_USERS", DOMAIN_USERS)
    _glogin(gclient, "otro@uni.example.edu|1")
    assert gclient.get("/api/records").status_code == 200
    monkeypatch.setenv("GOOGLE_USERS", "jefa@uni.example.edu")
    assert gclient.get("/api/records").status_code == 401


def test_google_logout_clears_session(gclient):
    _glogin(gclient, "dra.prueba@example.org|1")
    assert gclient.get("/api/records").status_code == 200
    assert gclient.post("/api/logout").status_code == 200
    assert gclient.get("/api/records").status_code == 401
    assert gclient.get("/api/session").json()["user"] is None
