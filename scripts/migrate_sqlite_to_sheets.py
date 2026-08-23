"""One-time migration: push every local SQLite record into Google Sheets.

Usage:
    .venv/bin/python scripts/migrate_sqlite_to_sheets.py

Requires APPS_SCRIPT_URL (and SCRIPT_SECRET matching the deployed Code.gs)
in .env. Safe to re-run: rows are upserted by _id.
"""

from __future__ import annotations

import sys

from src import records
from src.sync import build_sync_payload, post_script


def main() -> None:
    all_records, total = records.list_records(limit=100_000)
    if not all_records:
        print("no local records to migrate")
        return

    result = post_script(build_sync_payload(all_records))
    synced = result.get("synced", 0)
    print(f"migrated {synced}/{total} records to Google Sheets")
    if synced == total:
        records.mark_synced([r["_id"] for r in all_records])
        print("all local records marked as synced")
    else:
        print("count mismatch — review the spreadsheet", file=sys.stderr)


if __name__ == "__main__":
    main()
