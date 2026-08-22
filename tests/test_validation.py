"""Validation tests: records must conform to the data dictionary."""

from __future__ import annotations

import pytest

from src.validation import ValidationFailure, validate_fields

PROSTATE_OK = {
    "historia_clinica": "HC-001",
    "edad": 68,
    "sexo": "MASCULINO",
    "psa_diagnostico": 12.4,
    "gleason": "7_4+3",
    "isup": "3",
}


def test_valid_prostate_record_passes():
    cleaned = validate_fields("prostata", PROSTATE_OK)
    assert cleaned["gleason"] == "7_4+3"
    assert cleaned["psa_diagnostico"] == 12.4
    assert cleaned["histologia"] is None  # unstated -> None


def test_string_number_coerced():
    cleaned = validate_fields("prostata", {"psa_diagnostico": "12,5"})
    assert cleaned["psa_diagnostico"] == 12.5


def test_bad_option_code_rejected():
    # Spanish display string, not code — must fail (language-neutral storage).
    with pytest.raises(ValidationFailure) as exc:
        validate_fields("vejiga", {"grado_who": "Alto grado"})
    assert "grado_who" in exc.value.errors


def test_unknown_field_rejected():
    with pytest.raises(ValidationFailure):
        validate_fields("prostata", {"tamaño_tumor": 5})


def test_boolean_coercion():
    assert validate_fields("vejiga", {"invasion_muscular": True})["invasion_muscular"] == 1
    assert validate_fields("vejiga", {"invasion_muscular": "no"})["invasion_muscular"] == 0
    assert validate_fields("vejiga", {"invasion_muscular": "sí"})["invasion_muscular"] == 1
    with pytest.raises(ValidationFailure):
        validate_fields("vejiga", {"invasion_muscular": "tal vez"})


def test_date_validation():
    ok = validate_fields("pene", {"fecha_diagnostico": "2026-08-21"})
    assert ok["fecha_diagnostico"] == "2026-08-21"
    with pytest.raises(ValidationFailure):
        validate_fields("pene", {"fecha_diagnostico": "21/08/2026"})


def test_empty_means_not_stated():
    cleaned = validate_fields("rinon", {"tamano": "", "lateralidad": None})
    assert cleaned["tamano"] is None and cleaned["lateralidad"] is None


def test_multiple_errors_reported_together():
    with pytest.raises(ValidationFailure) as exc:
        validate_fields("testiculo", {"afp": "abc", "tnm_s": "S9"})
    assert set(exc.value.errors) == {"afp", "tnm_s"}


def test_all_pathologies_accept_minimal_record():
    from src import schema

    for key, spec in schema.PATHOLOGIES.items():
        first_id = spec["fields"][0]["id"]
        cleaned = validate_fields(key, {first_id: "x"} if spec["fields"][0][
            "type"
        ] == "text" else {})
        assert isinstance(cleaned, dict)
