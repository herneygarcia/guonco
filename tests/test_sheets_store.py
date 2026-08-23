"""Sheets-first store tests: success paths, failure fallbacks, pending overlay."""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")

from src import records, sheets_store


@pytest.fixture()
def local_db(tmp_path, monkeypatch):
    monkeypatch.setenv("GUONCO_DB_PATH", str(tmp_path / "t.sqlite"))
    from src.db import init_db

    init_db()


class ScriptDown(Exception):
    pass


def _fields(**overrides):
    base = {"historia_clinica": "HC-9", "psa_diagnostico": 7.1}
    base.update(overrides)
    return base


def test_save_success_marks_synced(local_db, monkeypatch):
    captured = {}

    def fake_post(payload):
        captured.update(payload)
        return {"ok": True, "synced": 1}

    monkeypatch.setattr(sheets_store, "post_script", fake_post)
    rec = sheets_store.save_record("prostata", _fields(), actor="jefe")
    assert rec["_sync_status"] == "synced"
    assert rec["_creado_por"] == "jefe"
    # Row carries the machine-readable raw-code record in its last column.
    rows = captured["registros_por_patologia"]["prostata"]["rows"]
    assert f'"_id":"{rec["_id"]}"' in rows[0][-1]
    assert rows[0][-2] == "jefe"  # registrado_por attribution column


def test_save_failure_keeps_record_pending(local_db, monkeypatch):
    def boom(_payload):
        raise RuntimeError("network down")

    monkeypatch.setattr(sheets_store, "post_script", boom)
    rec = sheets_store.save_record("prostata", _fields())
    assert rec["_sync_status"] == "pending"
    assert records.pending_count() == 1  # queued for later retry via /api/sync


def test_get_record_falls_back_to_sqlite(local_db, monkeypatch):
    local = records.save_record("prostata", _fields())

    def boom(_payload):
        raise RuntimeError("offline")

    monkeypatch.setattr(sheets_store, "post_script", boom)
    got = sheets_store.get_record(local["_id"])
    assert got is not None and got["_id"] == local["_id"]


def test_list_overlays_pending_local_records(local_db, monkeypatch):
    """A record edited offline (pending) must shadow its stale Sheets copy,
    and local-only pendings must appear even though Sheets lacks them."""
    stale = records.save_record("prostata", {"historia_clinica": "HC-1"})
    records.save_record(
        "prostata", {"historia_clinica": "HC-2"}, record_id=stale["_id"]
    )
    offline_new = records.save_record("vejiga", {"historia_clinica": "HC-3"})
    # The local prostata copy stays 'pending' (edited offline after its last
    # sync), so it must shadow the older copy stored in Sheets.

    def fake_get_all(_payload):
        return {
            "ok": True,
            "registros": [
                {
                    "key": "prostata",
                    "record": {**stale, "_updated_at": "2026-01-01T00:00:00+00:00"},
                }
            ],
        }

    monkeypatch.setattr(sheets_store, "post_script", fake_get_all)

    items, total = sheets_store.list_records()
    by_id = {r["_id"]: r for r in items}
    assert total == 2
    assert by_id[stale["_id"]]["_sync_status"] == "pending"
    assert by_id[stale["_id"]]["fields"]["historia_clinica"] == "HC-2"  # local wins
    assert by_id[offline_new["_id"]]["_patologia"] == "vejiga"


def test_list_falls_back_when_sheets_down(local_db, monkeypatch):
    records.save_record("prostata", _fields())

    def boom(_payload):
        raise RuntimeError("offline")

    monkeypatch.setattr(sheets_store, "post_script", boom)
    items, total = sheets_store.list_records(pathology_key="prostata")
    assert total == 1 and items[0]["fields"]["historia_clinica"] == "HC-9"


def test_delete_tries_sheets_and_local(local_db, monkeypatch):
    local = records.save_record("prostata", _fields())
    calls = []

    def fake_post(payload):
        calls.append(payload["action"])
        return {"ok": True, "deleted": True}

    monkeypatch.setattr(sheets_store, "post_script", fake_post)
    assert sheets_store.delete_record(local["_id"]) is True
    assert calls == ["delete_record"]
    assert records.get_record(local["_id"]) is None


def test_delete_reports_success_if_only_local_possible(local_db, monkeypatch):
    local = records.save_record("prostata", _fields())

    def boom(_payload):
        raise RuntimeError("offline")

    monkeypatch.setattr(sheets_store, "post_script", boom)
    assert sheets_store.delete_record(local["_id"]) is True
    assert records.get_record(local["_id"]) is None


def test_post_script_injects_secret(tmp_path, monkeypatch):
    """The shared SCRIPT_SECRET must be attached to every Apps Script call."""
    from src import sync as sync_mod

    monkeypatch.setenv("APPS_SCRIPT_URL", "https://script.example/exec")
    monkeypatch.setenv("SCRIPT_SECRET", "topsecret")
    sent = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_post(url, json=None, **kwargs):
        sent["url"] = url
        sent["body"] = json
        assert kwargs.get("follow_redirects") is True
        return FakeResponse()

    monkeypatch.setattr(sync_mod.httpx, "post", fake_post)
    result = sync_mod.post_script({"action": "get_all"})
    assert sent["url"] == "https://script.example/exec"
    assert sent["body"]["script_secret"] == "topsecret"
    assert result == {"ok": True}


def test_post_script_rejects_error_responses(tmp_path, monkeypatch):

    from src import sync as sync_mod

    monkeypatch.setenv("APPS_SCRIPT_URL", "https://script.example/exec")
    monkeypatch.delenv("SCRIPT_SECRET", raising=False)

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": False, "error": "invalid secret"}

    monkeypatch.setattr(
        sync_mod.httpx, "post", lambda *a, **k: FakeResponse()
    )
    with pytest.raises(RuntimeError):
        sync_mod.post_script({"action": "get_all"})
