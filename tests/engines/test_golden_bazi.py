"""G17-S2b: golden движка Ба-Цзы (столпы A–E, да-юнь A/B/D, день-граница E, час по TST).

Кейсы — tests/golden/bazi/*.yaml. Эталон — bazi.biz (ручной, карты A–E) + правила §5.3–5.5/§5.10,
сверено с двумя оракулами (test_bazi_oracle_diff). Столпы и да-юнь — арифметика поверх `_ephem`
(солнечные термины доказаны в S1). 152-ФЗ: во входе только место, дата, время, координаты, пол.
"""

import pathlib
from datetime import date, time

import pytest
import yaml

from lunora.engines import bazi
from lunora.timeplace import resolve

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden" / "bazi"
ALLOWED = {"place_id", "local_date", "local_time", "lat", "lon", "zone", "sex"}


def _cases():
    out = []
    for path in sorted(GOLDEN.rglob("*.y*ml")):
        for case in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if case and case.get("layer") == "bazi":
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
    chart = bazi.chart(m, inp["lat"], inp["lon"], sex=inp.get("sex"))
    return bazi.snapshot(chart)


def test_golden_set_complete():
    ids = {c["id"] for c in CASES}
    assert {"GB-01", "GB-02", "GB-03", "GB-05-C", "GB-05-D", "GB-06", "GB-07", "GB-12"} <= ids


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_input_has_no_personal_data(case):
    assert set(case["input"]) <= ALLOWED


@pytest.mark.parametrize("case", ACTIVE, ids=[c["id"] for c in ACTIVE])
def test_bazi_matches_reference(case):
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
