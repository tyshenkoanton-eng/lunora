"""G17-S1: golden «Допуск времени» (ARCHITECTURE §4.5) против нашего кода, без оракула.

Кейсы — tests/golden/time_tolerance/*.yaml (генератор scripts/spike/time_tolerance_oracle.py
снимает эталон знаков ASC с SE). Здесь рантайм: `timeplace.resolve` даёт интервал(ы), а
`calc.stability.stability` на сигнале «знак асцендента» (`_ephem`) выдаёт тег и множество
значений. 152-ФЗ: во входе только место, дата, время и координаты.
"""

import pathlib
from datetime import date, time

import pytest
import yaml

from lunora.calc import _ephem as eph
from lunora.calc.stability import stability
from lunora.timeplace import resolve

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "time_tolerance"
ALLOWED_INPUT = {"place_id", "local_date", "local_time", "tolerance_minutes", "lat", "lon"}


def _cases():
    out = []
    for path in sorted(GOLDEN.rglob("*.y*ml")):
        for case in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if case and case.get("layer") == "time_tolerance":
                out.append(case)
    return out


CASES = _cases()
ACTIVE = [c for c in CASES if c["status"] == "active"]
ZONE = "Europe/Volgograd"


def _asc_sign_signal(lat: float, lon: float):
    def signal(moment):
        return int(eph.angles(eph.instant(moment), lat, lon).asc // 30.0)

    return signal


def _snapshot(inp: dict) -> dict:
    lt = time.fromisoformat(inp["local_time"]) if inp["local_time"] else None
    m = resolve(
        date.fromisoformat(inp["local_date"]),
        lt,
        ZONE,
        tolerance_minutes=inp.get("tolerance_minutes"),
        place_id=inp["place_id"],
    )
    tag, signs = stability(m, _asc_sign_signal(inp["lat"], inp["lon"]))
    return {"stability.tag": tag, "stability.asc_signs": sorted(signs)}


def test_has_all_three_stability_values():
    tags = {e["value"] for c in ACTIVE for e in c["expected"] if e["path"] == "stability.tag"}
    assert {"stable", "range", "undetermined"} <= tags


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_input_has_no_personal_data(case):
    assert set(case["input"]) <= ALLOWED_INPUT


@pytest.mark.parametrize("case", ACTIVE, ids=[c["id"] for c in ACTIVE])
def test_stability_matches_reference(case):
    snap = _snapshot(case["input"])
    misses = [
        (e["path"], e["value"], snap[e["path"]])
        for e in case["expected"]
        if snap[e["path"]] != e["value"]
    ]
    assert not misses, misses
