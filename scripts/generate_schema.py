"""Generate src/schema.py from specs/data_dictionary.yaml.

Usage: .venv/bin/python scripts/generate_schema.py

src/schema.py is a GENERATED artifact (see AGENTS.md). Never hand-edit it.
"""

from __future__ import annotations

import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DICT_PATH = ROOT / "specs" / "data_dictionary.yaml"
OUT_PATH = ROOT / "src" / "schema.py"

SQL_TYPES = {
    "text": "TEXT",
    "textarea": "TEXT",
    "date": "TEXT",
    "select": "TEXT",
    "number": "REAL",
    "boolean": "INTEGER",
}


def build_ddl(key: str, fields: list[dict]) -> str:
    cols = [
        "_id TEXT PRIMARY KEY",
        "_created_at TEXT NOT NULL",
        "_updated_at TEXT NOT NULL",
        "_sync_status TEXT NOT NULL DEFAULT 'pending'",
        "_creado_por TEXT",
        "_actualizado_por TEXT",
    ]
    for f in fields:
        cols.append(f"{f['id']} {SQL_TYPES[f['type']]}")
    body = ",\n  ".join(cols)
    return f"CREATE TABLE IF NOT EXISTS {key} (\n  {body}\n)"


def render() -> str:
    data = yaml.safe_load(DICT_PATH.read_text(encoding="utf-8"))

    meta = data["meta"]
    common = data["common_fields"]
    pathologies = data["pathologies"]

    # Merge common fields ahead of each pathology's own fields.
    merged = {}
    for key, spec in pathologies.items():
        ids = [f["id"] for f in common] + [f["id"] for f in spec["fields"]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate field id in pathology '{key}'")
        merged[key] = {
            "nombre_es": spec["nombre_es"],
            "nombre_en": spec["nombre_en"],
            "cie10": spec["cie10"],
            "color": spec["color"],
            "fields": [*common, *spec["fields"]],
        }

    ddl = {key: build_ddl(key, spec["fields"]) for key, spec in merged.items()}

    lines = [
        '"""GENERATED from specs/data_dictionary.yaml by scripts/generate_schema.py.',
        "",
        "Do NOT hand-edit this file. Change the YAML and regenerate.",
        '"""',
        "",
        "META = " + repr(meta),
        "",
        "# key -> {nombre_es, nombre_en, cie10, color, fields}",
        "# field: {id, code, type, required, label_es, label_en[, unit][, options]}",
        "PATHOLOGIES = " + repr(merged),
        "",
        "# key -> CREATE TABLE statement",
        "SQL_DDL = " + repr(ddl),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    src = render()
    OUT_PATH.write_text(src, encoding="utf-8")
    raw = yaml.safe_load(DICT_PATH.read_text())
    n = sum(len(p["fields"]) for p in raw["pathologies"].values())
    print(
        f"wrote {OUT_PATH.relative_to(ROOT)} ({n} pathology-specific + "
        f"{len(raw['common_fields'])} common fields)"
    )


if __name__ == "__main__":
    main()
