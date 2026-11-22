"""G17-S2c: golden западного движка (сборка, аспекты GW-05, граница знака GW-11).

Кейсы — tests/golden/western/*.yaml. Эталон — бланки astro.com карт A/D/C (S1) + правила
§3.7/§2.5/§1.4. Долготы считает `_ephem` (GE-01, ≤1″); аспекты и дома — движок `western`.
Орб аспекта с допуском 0.02° (расхождение долгот astro.com и _ephem — секунды).
152-ФЗ: во входе только место, дата, время, координаты.
"""

import pathlib
from datetime import date, time

import pytest
import yaml

from lunora.engines import western
from lunora.timeplace import resolve

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden" / "western"
ALLOWED = {"place_id", "local_date", "local_time", "lat", "lon", "zone", "synthetic_longitudes"}


def _cases():
    out = []
    for path in sorted(GOLDEN.rglob("*.y*ml")):
        for case in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if case and case.get("layer") == "western":
                out.append(case)
    return out


CASES = _cases()
ACTIVE = [c for c in CASES if c["status"] == "active"]


def _snapshot(inp: dict) -> dict:
    if "synthetic_longitudes" in inp:
        return {
            f"sign_of.{k}": western.sign_name(v)
            for k, v in inp["synthetic_longitudes"].items()
        }
    m = resolve(
        date.fromisoformat(inp["local_date"]),
        time.fromisoformat(inp["local_time"]),
        inp["zone"],
        place_id=inp["place_id"],
    )
    chart = western.chart(m, inp["lat"], inp["lon"])
    return western.snapshot(chart)


def test_golden_set_complete():
    ids = {c["id"] for c in CASES}
    assert {"GW-A-assembly", "GW-D-assembly", "GW-05-A", "GW-05-D", "GW-C-polar", "GW-11"} <= ids


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_input_has_no_personal_data(case):
    assert set(case["input"]) <= ALLOWED


@pytest.mark.parametrize("case", ACTIVE, ids=[c["id"] for c in ACTIVE])
def test_western_matches_reference(case):
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
