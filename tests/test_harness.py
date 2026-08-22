"""Tests for the evaluation harness scoring logic (no network calls)."""

from __future__ import annotations

from harness.run_eval import numbers_match, score_case


def test_numbers_match_with_tolerance():
    assert numbers_match(12, 12)
    assert numbers_match(12, 11.9)          # within 2%
    assert not numbers_match(12, 13)
    assert not numbers_match(12, None)
    assert not numbers_match("abc", 12)


def test_exact_codes_required():
    case = {"expected": {"grado_who": "ALTO_GRADO"}}
    out = score_case(case, {"grado_who": "ALTO_GRADO"})
    assert out["results"]["grado_who"] == ("ALTO_GRADO", "ALTO_GRADO", True)

    # Display string instead of code must fail (language-neutral storage rule).
    out = score_case(case, {"grado_who": "Alto grado"})
    assert out["results"]["grado_who"][2] is False


def test_boolean_scoring():
    case = {"expected": {"invasion_muscular": True}}
    assert score_case(case, {"invasion_muscular": 1})["results"]["invasion_muscular"][2]
    assert not score_case(case, {"invasion_muscular": 0})["results"]["invasion_muscular"][2]


def test_hallucination_detection():
    case = {"expected": {}, "must_be_null": ["tnm_t"]}
    out = score_case(case, {"tnm_t": "T2b"})
    assert "HALLUCINATED:tnm_t" in out["results"]
    assert out["hallucinations"] == ["tnm_t"]

    clean = score_case(case, {})
    assert clean["hallucinations"] == []


def test_all_golden_cases_are_wellformed():
    import pathlib

    import yaml

    from src import schema

    path = pathlib.Path(__file__).resolve().parent.parent / "harness" / "golden_cases.yaml"
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 30
    seen = set()
    for case in cases:
        assert case["pathology"] in schema.PATHOLOGIES, case["id"]
        seen.add(case["pathology"])
        fmap = {f["id"]: f for f in schema.PATHOLOGIES[case["pathology"]]["fields"]}
        for fid, value in case.get("expected", {}).items():
            assert fid in fmap, f"{case['id']}: unknown field {fid}"
            field = fmap[fid]
            if field["type"] == "select" and isinstance(value, str):
                codes = {o["code"] for o in field.get("options", [])}
                assert value in codes, f"{case['id']}.{fid}: bad code {value}"
            if field["type"] == "boolean":
                assert isinstance(value, bool), f"{case['id']}.{fid}: bool required"
        for fid in case.get("must_be_null", []):
            assert fid in fmap, f"{case['id']}: must_be_null unknown field {fid}"
    assert seen == set(schema.PATHOLOGIES), "every pathology must have golden cases"
