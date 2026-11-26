"""Тесты аудитора golden-кейсов (G17-S1, каркас).

Формат — 11_architecture.md §6.2 + versions (B12).
"""

import importlib.util
import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "golden_audit", ROOT / "scripts" / "spike" / "golden_audit.py"
)
golden_audit = importlib.util.module_from_spec(_spec)
sys.modules["golden_audit"] = golden_audit
_spec.loader.exec_module(golden_audit)


def active_case(**over):
    case = {
        "id": "timeplace-volgograd-1984-02-04",
        "layer": "timeplace",
        "input": {
            "place_id": "geonames:472757",
            "local_date": "1984-02-04",
            "local_time": "15:00",
        },
        "reference": {
            "source": "astro.com",
            "settings": {"atlas": "astro.com"},
            "captured_at": "2026-11-21",
            "captured_by": "Антон",
            "evidence_file": "evidence/volgograd-1984.png",
        },
        "versions": {
            "tz": "2026f",
            "ephemeris": "de440s",
            "reference_service": "astro.com 2026-11",
        },
        "expected": [{"path": "timeplace.utc_offset", "value": "+04:00", "exact": True}],
        "status": "active",
    }
    case.update(over)
    return case


def write(tmp_path, cases, evidence=("evidence/volgograd-1984.png",)):
    for rel in evidence:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"png")
    for i, c in enumerate(cases):
        (tmp_path / f"case{i}.yaml").write_text(yaml.safe_dump(c, allow_unicode=True), "utf-8")
    return tmp_path


def errors(tmp_path, require_active=False):
    return golden_audit.audit(tmp_path, require_active=require_active).errors


def test_valid_active_case_passes(tmp_path):
    assert errors(write(tmp_path, [active_case()])) == []


@pytest.mark.parametrize("field", ["source", "settings", "evidence_file", "captured_at"])
def test_active_case_requires_reference_field(tmp_path, field):
    case = active_case()
    del case["reference"][field]
    assert any(field in e for e in errors(write(tmp_path, [case])))


def test_active_case_evidence_file_must_exist(tmp_path):
    write(tmp_path, [active_case()], evidence=())
    assert any("evidence" in e for e in errors(tmp_path))


@pytest.mark.parametrize("key", ["tz", "ephemeris", "reference_service"])
def test_active_case_requires_versions(tmp_path, key):
    case = active_case()
    del case["versions"][key]
    assert any(key in e for e in errors(write(tmp_path, [case])))


def test_expected_needs_tolerance_or_exact(tmp_path):
    case = active_case(expected=[{"path": "western.asc.longitude", "value": 123.4}])
    assert any("tolerance" in e for e in errors(write(tmp_path, [case])))


def test_expected_must_not_be_empty(tmp_path):
    assert any("expected" in e for e in errors(write(tmp_path, [active_case(expected=[])])))


def test_unknown_layer_and_status_rejected(tmp_path):
    errs = errors(write(tmp_path, [active_case(layer="tarot", status="maybe")]))
    assert any("layer" in e for e in errs) and any("status" in e for e in errs)


def test_duplicate_ids_rejected(tmp_path):
    assert any("дубл" in e for e in errors(write(tmp_path, [active_case(), active_case()])))


@pytest.mark.parametrize("status", ["disputed", "known_gap"])
def test_non_active_needs_notes_but_not_reference(tmp_path, status):
    case = active_case(status=status)
    del case["reference"]
    assert any("notes" in e for e in errors(write(tmp_path, [case])))
    case["notes"] = "ждёт сверки со стр. 51 (П-5)"
    assert errors(write(tmp_path, [case])) == []


def test_require_active_fails_without_active_cases(tmp_path):
    assert any("active" in e for e in errors(tmp_path, require_active=True))


def test_require_active_passes_with_active_case(tmp_path):
    assert errors(write(tmp_path, [active_case()]), require_active=True) == []


def test_broken_yaml_reported(tmp_path):
    (tmp_path / "bad.yaml").write_text("id: [unclosed", "utf-8")
    assert any("bad.yaml" in e for e in errors(tmp_path))
