"""Extraction evaluation harness.

Runs every golden case through src.extract and scores per-field accuracy
against expected dictionary codes. Gate (AGENTS.md): >= 90% per-field accuracy.

Usage: .venv/bin/python harness/run_eval.py [--pathology prostata] [--verbose]
Exit code: 0 if gate passed, 1 otherwise, 2 on config errors.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from collections import defaultdict
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import groq_api_key, load_env
from src.extract import extract_fields

GATE = 0.90


def load_cases(path: pathlib.Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["cases"]


def numbers_match(expected: Any, actual: Any) -> bool:
    try:
        e, a = float(expected), float(actual)
    except (TypeError, ValueError):
        return False
    return abs(e - a) <= max(0.1, abs(e) * 0.02)


def score_case(case: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
    """Score one case. Returns per-field results {field: (expected, actual, ok)}."""
    results: dict[str, tuple[Any, Any, bool]] = {}
    for fid, exp in case.get("expected", {}).items():
        act = extracted.get(fid)
        if isinstance(exp, (int, float)) and not isinstance(exp, bool):
            ok = numbers_match(exp, act)
        elif isinstance(exp, bool):
            ok = act is not None and int(act) == int(exp)
        else:
            ok = act == exp
        results[fid] = (exp, act, ok)

    # Hallucination check: fields that must stay null but were populated.
    hallucinations = []
    for fid in case.get("must_be_null", []):
        act = extracted.get(fid)
        if act is not None:
            results[f"HALLUCINATED:{fid}"] = ("null", act, False)
            hallucinations.append(fid)
    return {
        "results": results,
        "hallucinations": hallucinations,
        "unmapped": case.get("_unmapped_notes", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pathology", help="only run cases of this pathology")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    load_env()
    if not groq_api_key():
        print(
            "ERROR: GROQ_API_KEY not set. "
            "Copy .env.example to .env and add your key."
        )
        return 2

    cases = load_cases(ROOT / "harness" / "golden_cases.yaml")
    if args.pathology:
        cases = [c for c in cases if c["pathology"] == args.pathology]

    correct = wrong = 0
    by_pathology: dict[str, list[bool]] = defaultdict(list)
    failures: list[tuple[str, dict]] = []

    for case in cases:
        out = extract_fields(case["pathology"], case["transcript"])
        fields = out["fields"]
        scored = score_case({**case, "_unmapped_notes": out["unmapped_notes"]}, fields)
        case_oks = []
        for label, (exp, act, ok) in scored["results"].items():
            by_pathology[case["pathology"]].append(ok)
            correct += ok
            wrong += not ok
            case_oks.append(ok)
            if not ok:
                detail = {"expected": exp, "got": act}
                failures.append((f"{case['id']}:{label}", detail))
                if args.verbose:
                    print(f"  MISS {case['id']}:{label} expected={exp!r} got={act!r}")
        status = "OK " if all(case_oks) else "FAIL"
        print(f"[{status}] {case['id']} ({len(scored['results'])} fields)")

    total = correct + wrong
    accuracy = correct / total if total else 0.0
    print("\n=== Extraction eval report ===")
    print(f"cases: {len(cases)}   field comparisons: {total}")
    for key, oks in sorted(by_pathology.items()):
        pct = sum(oks) / len(oks)
        flag = "" if pct >= GATE else f"  <-- below gate ({pct:.1%})"
        print(f"  {key:10s} {sum(oks):3d}/{len(oks):3d} = {pct:.1%}{flag}")
    gate_color = "PASS" if accuracy >= GATE else "FAIL"
    print(f"\nTOTAL per-field accuracy: {correct}/{total} = {accuracy:.1%} "
          f"[gate {GATE:.0%}: {gate_color}]")
    if failures:
        print("\nFailed comparisons:")
        for name, detail in failures:
            print(f"  - {name}: expected={detail['expected']!r} got={detail['got']!r}")
    return 0 if accuracy >= GATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
