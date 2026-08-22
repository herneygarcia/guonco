"""SQLite persistence layer. Uses GENERATED DDL from src/schema.py."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from src import schema

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "guonco.sqlite"


def db_path() -> Path:
    return Path(os.environ.get("GUONCO_DB_PATH", DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or get_connection()
    try:
        for ddl in schema.SQL_DDL.values():
            conn.execute(ddl)
        conn.commit()
    finally:
        if own:
            conn.close()
