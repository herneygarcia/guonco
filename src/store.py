"""Storage dispatcher: routes record CRUD to Sheets-first or SQLite-only mode.

STORE=sheets  -> Google Sheets is the source of truth, SQLite is the offline
                 cache/fallback (src/sheets_store.py).
STORE=sqlite  -> classic local-only mode (src/records.py), still the default.
If STORE=sheets but APPS_SCRIPT_URL is not configured, SQLite is used so the
app never breaks offline.
"""

from __future__ import annotations

from typing import Any

from src import records
from src.config import apps_script_url, store_mode


def _use_sheets() -> bool:
    return store_mode() == "sheets" and bool(apps_script_url())


def save_record(
    pathology_key: str,
    fields: dict[str, Any],
    record_id: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    if _use_sheets():
        from src import sheets_store

        return sheets_store.save_record(
            pathology_key, fields, record_id=record_id, actor=actor
        )
    return records.save_record(pathology_key, fields, record_id=record_id, actor=actor)


def get_record(record_id: str) -> dict | None:
    if _use_sheets():
        from src import sheets_store

        return sheets_store.get_record(record_id)
    return records.get_record(record_id)


def list_records(
    pathology_key: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    if _use_sheets() and not status:
        from src import sheets_store

        return sheets_store.list_records(
            pathology_key=pathology_key, limit=limit, offset=offset
        )
    return records.list_records(
        pathology_key=pathology_key, status=status, limit=limit, offset=offset
    )


def delete_record(record_id: str) -> bool:
    if _use_sheets():
        from src import sheets_store

        return sheets_store.delete_record(record_id)
    return records.delete_record(record_id)


def counts_by_status() -> dict[str, Any]:
    if _use_sheets():
        from src import sheets_store

        return sheets_store.counts_by_status()
    return records.counts_by_status()
