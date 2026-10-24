"""Isolate every test from the developer's real .env.

Without this, enabling APP_PINS / STORE=sheets / SCRIPT_SECRET in the local
.env leaks into the suite: APIs start demanding login and record CRUD tries
to reach the production Google Sheet. Each test opts back in explicitly.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_real_env(monkeypatch, tmp_path):
    from src import config

    # Point config.load_env() at a nonexistent file so .env is never read.
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "does-not-exist")
    for var in (
        "APP_PINS",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_USERS",
        "APPS_SCRIPT_URL",
        "SCRIPT_SECRET",
        "SESSION_SECRET",
        "STORE",
        "GUONCO_DB_PATH",
    ):
        monkeypatch.delenv(var, raising=False)
