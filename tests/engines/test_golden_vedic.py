"""G17-S2d: golden ведического движка (раши/лагна/бхавы, накшатры, Вимшоттари, варги).

Кейсы — tests/golden/vedic/*.yaml. Эталон — Jagannatha Hora 8.0 (карты A, B, D) + §4.1–4.4.
Положения — истинные геометрические (без аберрации), узлы средние, айанамша Лахири (§2.7):
разница с JH True Chitrapaksha (≈56″) дискретные значения не меняет. Активная даша — на
фиксированную дату 2026-11-16 (детерминизм). 152-ФЗ: во входе только место, дата, время, коорд.
"""

import pathlib
from datetime import date, time

import pytest
import yaml

from lunora.engines import vedic
from lunora.timeplace import resolve

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden" / "vedic"
ALLOWED = {"place_id", "local_date", "local_time", "lat", "lon", "zone"}
NOW = date(2026, 11, 16)  # опорная дата активной даши (§4.3)


def _cases():
    out = []
    for path in sorted(GOLDEN.rglob("*.y*ml")):
        for case in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if case and case.get("layer") == "vedic":
                out.append(case)
    return out


CASES = _cases()
ACTIVE = [c for c in CASES if c["status"] == "active"]


def _snapshot(inp: dict) -> dict:
    m = resolve(
        date.fromisoformat(inp["local_date"]),
        time.fromisoformat(inp["local_time"]),
        inp["zone"],
        place_id=inp["place_id"],
    )
    return vedic.snapshot(vedic.chart(m, inp["lat"], inp["lon"], now=NOW))


def test_golden_set_complete():
    ids = {c["id"] for c in CASES}
    assert {f"GV-0{i}" for i in range(1, 7)} <= ids


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_input_has_no_personal_data(case):
    assert set(case["input"]) <= ALLOWED


@pytest.mark.parametrize("case", ACTIVE, ids=[c["id"] for c in ACTIVE])
def test_vedic_matches_reference(case):
    snap = _snapshot(case["input"])
    misses = []
    for e in case["expected"]:
        got = snap.get(e["path"], "<нет>")
        if "tolerance" in e:
            if not isinstance(got, (int, float)) or abs(got - e["value"]) > e["tolerance"]:
                misses.append((e["path"], e["value"], got))
        elif got != e["value"]:
            misses.append((e["path"], e["value"], got))
    assert not misses, misses
