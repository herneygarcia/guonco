"""SQLite record CRUD: upsert by _id, sync status tracking."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from src import schema
from src.db import get_connection
from src.validation import validate_fields


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_record(row: sqlite3.Row, pathology_key: str) -> dict[str, Any]:
    fields = schema.PATHOLOGIES[pathology_key]["fields"]
    fmap = {f["id"]: f for f in fields}
    out = {
        "_id": row["_id"],
        "_patologia": pathology_key,
        "_created_at": row["_created_at"],
        "_updated_at": row["_updated_at"],
        "_sync_status": row["_sync_status"],
        "fields": {},
    }
    for fid, f in fmap.items():
        value = row[fid]
        if f["type"] == "boolean" and value is not None:
            value = bool(value)
        elif f["type"] == "number" and value is not None:
            value = float(value)
        out["fields"][fid] = value
    return out


def apply_auto_fields(pathology_key: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Fill fields marked `auto: today` (per dictionary) when omitted/empty."""
    out = {k: v for k, v in fields.items() if v not in ("", None)}
    for f in schema.PATHOLOGIES[pathology_key]["fields"]:
        if f.get("auto") == "today" and f["id"] not in out:
            out[f["id"]] = datetime.now(timezone.utc).date().isoformat()
    return out


def save_record(
    pathology_key: str,
    fields: dict[str, Any],
    record_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    if pathology_key not in schema.PATHOLOGIES:
        raise KeyError(f"unknown pathology '{pathology_key}'")
    cleaned = validate_fields(pathology_key, apply_auto_fields(pathology_key, fields))

    own = conn is None
    conn = conn or get_connection()
    try:
        now = _now()
        rid = record_id or uuid.uuid4().hex
        existing = conn.execute(
            f"SELECT _created_at FROM {pathology_key} WHERE _id = ?", (rid,)
        ).fetchone()
        created_at = existing["_created_at"] if existing else now
        cols = ["_id", "_created_at", "_updated_at", "_sync_status", *cleaned]
        placeholders = ",".join("?" for _ in cols)
        values = [rid, created_at, now, "pending", *cleaned.values()]
        conn.execute(
            f"INSERT OR REPLACE INTO {pathology_key} ({','.join(cols)}) "
            f"VALUES ({placeholders})",
            values,
        )
        conn.commit()
        row = conn.execute(
            f"SELECT * FROM {pathology_key} WHERE _id = ?", (rid,)
        ).fetchone()
        return _row_to_record(row, pathology_key)
    finally:
        if own:
            conn.close()


def get_record(record_id: str, conn: sqlite3.Connection | None = None) -> dict | None:
    own = conn is None
    conn = conn or get_connection()
    try:
        for key in schema.PATHOLOGIES:
            row = conn.execute(
                f"SELECT * FROM {key} WHERE _id = ?", (record_id,)
            ).fetchone()
            if row:
                return _row_to_record(row, key)
        return None
    finally:
        if own:
            conn.close()


def list_records(
    pathology_key: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    conn: sqlite3.Connection | None = None,
) -> tuple[list[dict], int]:
    own = conn is None
    conn = conn or get_connection()
    try:
        keys = [pathology_key] if pathology_key else list(schema.PATHOLOGIES)
        records: list[dict] = []
        total = 0
        for key in keys:
            where, params = "", []
            if status:
                where = "WHERE _sync_status = ?"
                params = [status]
            total += conn.execute(
                f"SELECT COUNT(*) FROM {key} {where}", params
            ).fetchone()[0]
            sql = (
                f"SELECT * FROM {key} {where} ORDER BY _created_at DESC "
                f"LIMIT ? OFFSET ?"
            )
            rows = conn.execute(sql, [*params, limit, offset]).fetchall()
            records.extend(_row_to_record(r, key) for r in rows)
        records.sort(key=lambda r: r["_created_at"], reverse=True)
        return records[:limit], total
    finally:
        if own:
            conn.close()


def delete_record(record_id: str, conn: sqlite3.Connection | None = None) -> bool:
    own = conn is None
    conn = conn or get_connection()
    try:
        for key in schema.PATHOLOGIES:
            cur = conn.execute(f"DELETE FROM {key} WHERE _id = ?", (record_id,))
            if cur.rowcount:
                conn.commit()
                return True
        return False
    finally:
        if own:
            conn.close()


def mark_synced(record_ids: list[str], conn: sqlite3.Connection | None = None) -> int:
    own = conn is None
    conn = conn or get_connection()
    try:
        count = 0
        for key in schema.PATHOLOGIES:
            cur = conn.execute(
                f"UPDATE {key} SET _sync_status = 'synced' WHERE _id IN "
                f"({','.join('?' for _ in record_ids)})",
                record_ids,
            )
            count += cur.rowcount
        conn.commit()
        return count
    finally:
        if own:
            conn.close()


def pending_count(conn: sqlite3.Connection | None = None) -> int:
    _, total = list_records(status="pending", limit=0, offset=0, conn=conn)
    return total


def counts_by_status() -> dict[str, Any]:
    conn = get_connection()
    try:
        pending = synced = 0
        last = None
        for key in schema.PATHOLOGIES:
            row = conn.execute(
                f"SELECT COUNT(*) c FROM {key} WHERE _sync_status='pending'"
            ).fetchone()
            pending += row["c"]
            row = conn.execute(
                f"SELECT COUNT(*) c FROM {key} WHERE _sync_status='synced'"
            ).fetchone()
            synced += row["c"]
            row = conn.execute(f"SELECT MAX(_updated_at) m FROM {key}").fetchone()
            m = row["m"]
            if m and (last is None or m > last):
                last = m
        return {"pending": pending, "synced": synced, "last_sync_at": last}
    finally:
        conn.close()
