"""Record validation against specs/data_dictionary.yaml (via generated schema).

Rules (specs/api_contract.md):
- Unknown field ids are rejected.
- Select values must be exact dictionary CODES (language-neutral).
- Numbers accept int/float or strings like "12" / "12,5".
- Booleans accept true/false (bool, 0/1, "si"/"sí"/"yes"/"no"/"true"/"false").
- Dates must be ISO YYYY-MM-DD.
- null / missing means "not stated" and is always allowed.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from src import schema

TRUTHY = {"true", "1", "si", "sí", "yes"}
FALSY = {"false", "0", "no"}


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", "", str(text).lower())


def resolve_select(field: dict, value: Any) -> str:
    """Map a select value to its canonical code.

    Accepts exact codes and near-misses (case/spacing variants, or the es/en
    display labels) so LLM output that drifts from code format still lands on
    the language-neutral code. Raises ValueError when nothing matches.
    """
    options = field.get("options", [])
    raw = str(value)
    for o in options:
        if o["code"] == raw:
            return o["code"]
    target = _norm(raw)
    for o in options:  # normalized code match
        if _norm(o["code"]) == target:
            return o["code"]
    for o in options:  # display-label match
        if target and (
            _norm(o.get("es", "")) == target or _norm(o.get("en", "")) == target
        ):
            return o["code"]
    raise ValueError(
        f"'{value}' is not an allowed code "
        f"({'|'.join(sorted(o['code'] for o in options))})"
    )


class ValidationFailure(Exception):
    """Raised when record fields violate the data dictionary."""

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__(f"{len(errors)} invalid field(s)")


def field_map(pathology_key: str) -> dict[str, dict]:
    try:
        fields = schema.PATHOLOGIES[pathology_key]["fields"]
    except KeyError:
        raise KeyError(f"unknown pathology '{pathology_key}'") from None
    return {f["id"]: f for f in fields}


def coerce_value(field: dict, value: Any) -> Any:
    ftype = field["type"]
    if value is None or value == "":
        return None
    if ftype == "number":
        if isinstance(value, bool):
            raise ValueError("expected a number")
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip().replace(",", "."))
            except ValueError:
                raise ValueError(f"'{value}' is not a number") from None
        raise ValueError("expected a number")
    if ftype == "boolean":
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)) and value in (0, 1):
            return int(value)
        if isinstance(value, str) and value.strip().lower() in TRUTHY | FALSY:
            return int(value.strip().lower() in TRUTHY)
        raise ValueError("expected yes/no")
    if ftype == "date":
        text = str(value).strip()
        try:
            dt.date.fromisoformat(text)
        except ValueError:
            raise ValueError(f"'{text}' is not a YYYY-MM-DD date") from None
        return text
    if ftype == "select":
        return resolve_select(field, value)
    # text / textarea
    return str(value)


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


_MODELS: dict[str, type[BaseModel]] = {}


def record_model(pathology_key: str) -> type[BaseModel]:
    """Build (and cache) a Pydantic model whose fields mirror the dictionary."""
    if pathology_key in _MODELS:
        return _MODELS[pathology_key]
    fmap = field_map(pathology_key)

    ns: dict[str, Any] = {
        "__module__": __name__,
        "__qualname__": f"{pathology_key.capitalize()}Record",
        "_fmap": fmap,
        "_key": pathology_key,
        "model_config": ConfigDict(extra="forbid"),
    }

    def checker(_cls: Any, values: dict[str, Any]) -> dict[str, Any]:
        errors: dict[str, str] = {}
        for fid, field in fmap.items():
            raw = values.get(fid)
            try:
                values[fid] = coerce_value(field, raw)
            except ValueError as exc:
                errors[fid] = str(exc)
        if errors:
            raise ValueError(errors)
        return values

    ns["_check"] = model_validator(mode="before")(classmethod(checker))
    ns["__annotations__"] = {fid: Any for fid in fmap}

    model = type(f"{pathology_key.capitalize()}Record", (BaseModel,), ns)
    _MODELS[pathology_key] = model
    return model


def validate_fields(pathology_key: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Validate + normalize a fields dict; returns cleaned dict keyed by field id."""
    fmap = field_map(pathology_key)
    unknown = set(fields) - set(fmap)
    if unknown:
        raise ValidationFailure(
            {u: "unknown field for this pathology" for u in unknown}
        )
    model = record_model(pathology_key)
    try:
        validated = model(**fields)
    except ValidationError as exc:
        errors: dict[str, str] = {}
        for err in exc.errors():
            ctx = err.get("ctx", {}).get("error")
            if (
                isinstance(ctx, ValueError)
                and ctx.args
                and isinstance(ctx.args[0], dict)
            ):
                errors.update(ctx.args[0])
                continue
            loc = err["loc"][0] if err["loc"] else "_"
            errors.setdefault(str(loc), str(ctx) if ctx else err["msg"])
        raise ValidationFailure(errors) from None
    return {fid: getattr(validated, fid) for fid in fmap}
