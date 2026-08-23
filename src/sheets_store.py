"""Google Sheets as source of truth, SQLite as offline cache/fallback.

Writes go to Sheets first (Apps Script upsert-by-_id); on any network/API
failure the record stays in the local SQLite queue ('pending') and can be
retried later via /api/sync. Reads come from Sheets and are overlaid with
newer local pending records so nothing saved offline ever disappears.
"""

from __future__ import annotations

import logging
from typing import Any

from src import records
from src.sync import build_sync_payload, post_script

log = logging.getLogger(__name__)


def save_record(
    pathology_key: str,
    fields: dict[str, Any],
    record_id: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    rec = records.save_record(
        pathology_key, fields, record_id=record_id, actor=actor
    )
    try:
        post_script(build_sync_payload([rec]))
    except Exception as exc:
        log.warning("Sheets write failed (%s); kept pending locally", exc)
        return rec
    records.mark_synced([rec["_id"]])
    return records.get_record(rec["_id"]) or rec


def get_record(record_id: str) -> dict | None:
    try:
        result = post_script({"action": "get_record", "id": record_id})
        if result.get("found"):
            return result["record"]
        return None
    except Exception as exc:
        log.warning("Sheets read failed (%s); falling back to SQLite", exc)
        return records.get_record(record_id)


def list_records(
    pathology_key: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    if status:
        # Queue/status views are always answered from the local store.
        return records.list_records(
            pathology_key=pathology_key, status=status, limit=limit, offset=offset
        )
    try:
        result = post_script({"action": "get_all"})
        merged: dict[str, dict] = {}
        for entry in result.get("registros", []):
            rec = entry["record"]
            if pathology_key and entry.get("key") != pathology_key:
                continue
            merged[rec["_id"]] = rec
    except Exception as exc:
        log.warning("Sheets read failed (%s); falling back to SQLite", exc)
        return records.list_records(
            pathology_key=pathology_key, limit=limit, offset=offset
        )

    # Overlay unsynced local records (they are newer than what Sheets has).
    for rec in records.list_records(status="pending", limit=10_000)[0]:
        if pathology_key and rec["_patologia"] != pathology_key:
            continue
        merged[rec["_id"]] = rec

    ordered = sorted(merged.values(), key=lambda r: r["_created_at"], reverse=True)
    return ordered[offset : offset + limit], len(ordered)


def delete_record(record_id: str) -> bool:
    sheets_ok = False
    try:
        result = post_script({"action": "delete_record", "id": record_id})
        sheets_ok = bool(result.get("deleted"))
    except Exception as exc:
        log.warning("Sheets delete failed (%s); deleting local copy", exc)
    local_ok = records.delete_record(record_id)
    return sheets_ok or local_ok


def counts_by_status() -> dict[str, Any]:
    counts = records.counts_by_status()
    try:
        _items, total = list_records(limit=0)
        counts["total"] = total
    except Exception:
        pass
    return counts
