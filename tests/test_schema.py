"""Schema tests: generated src/schema.py must match the YAML source of truth."""

from __future__ import annotations

import re
import sqlite3

import pytest
import yaml

from src import schema
from src.db import init_db

DICT_PATH = "specs/data_dictionary.yaml"


def _dict() -> dict:
    with open(DICT_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


DICT = _dict()


def test_all_yaml_pathologies_present():
    assert set(schema.PATHOLOGIES) == set(DICT["pathologies"])


def test_field_counts_match_yaml():
    for key, spec in DICT["pathologies"].items():
        expected = len(DICT["common_fields"]) + len(spec["fields"])
        assert len(schema.PATHOLOGIES[key]["fields"]) == expected, key


def test_common_fields_in_every_pathology():
    common_ids = [f["id"] for f in DICT["common_fields"]]
    for key, spec in schema.PATHOLOGIES.items():
        ids = [f["id"] for f in spec["fields"]]
        assert ids[: len(common_ids)] == common_ids, key


def test_no_duplicate_field_ids_within_pathology():
    for key, spec in schema.PATHOLOGIES.items():
        ids = [f["id"] for f in spec["fields"]]
        assert len(ids) == len(set(ids)), key


def test_select_options_have_codes_and_bilingual_labels():
    for key, spec in schema.PATHOLOGIES.items():
        for f in spec["fields"]:
            if f["type"] != "select":
                continue
            codes = set()
            for o in f.get("options", []):
                assert "code" in o, (key, f["id"], o)
                # TNM-style options may omit labels when code is language-neutral
                if "es" in o or "en" in o:
                    assert "es" in o and "en" in o, (key, f["id"], o)
                codes.add(o["code"])
            assert len(codes) == len(f.get("options", [])), (
                f"duplicate option code in {key}.{f['id']}"
            )


def test_labels_are_bilingual_everywhere():
    for key, spec in schema.PATHOLOGIES.items():
        for f in spec["fields"]:
            assert f.get("label_es") and f.get("label_en"), (key, f["id"])


@pytest.mark.parametrize("key", list(schema.SQL_DDL))
def test_ddl_executes(key):
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(schema.SQL_DDL[key])
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({key})")]
        field_ids = [f["id"] for f in schema.PATHOLOGIES[key]["fields"]]
        assert cols[4:] == field_ids  # first four are _meta columns
    finally:
        conn.close()


def test_init_db_creates_all_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("GUONCO_DB_PATH", str(tmp_path / "t.sqlite"))
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    init_db(conn)
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert tables == set(schema.SQL_DDL)


def test_generated_file_has_do_not_edit_banner():
    with open("src/schema.py", encoding="utf-8") as fh:
        src = fh.read()
    assert "GENERATED" in src and "Do NOT hand-edit" in src
    assert re.search(r"META\s*=", src)
