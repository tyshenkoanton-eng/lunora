"""G17-S1: golden-кейсы слоя `ephemeris` (GE-01, GE-02, GE-06 …) против `lunora.calc._ephem`.

Кейсы — tests/golden/**/*.yaml (формат ARCHITECTURE §6.2, проверяет golden_audit). Раннер
берёт каждый active-кейс слоя ephemeris, считает карту по его входу и сверяет каждое
ожидание `path` с допуском. 152-ФЗ: во входе кейса — только место, время и координаты.
"""

import pathlib
from datetime import datetime

import pytest
import yaml

from lunora.calc import _ephem as eph

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
ALLOWED_INPUT = {"place_id", "local_date", "local_time", "utc_offset", "utc", "lat", "lon"}


def _cases():
    out = []
    for path in sorted(GOLDEN.rglob("*.y*ml")):
        if "evidence" in path.parts:
            continue
        for case in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if case and case.get("layer") == "ephemeris":
                out.append(case)
    return out


CASES = _cases()
ACTIVE = [c for c in CASES if c["status"] == "active"]


def _chart(inp: dict) -> dict:
    """Плоский снимок карты: путь → значение (пути как в expected)."""
    t = eph.instant(datetime.fromisoformat(inp["utc"].replace("Z", "+00:00")))
    snap: dict = {}
    for name, p in eph.bodies(t).items():
        snap[f"bodies.{name}.lon"] = p.lon
        snap[f"bodies.{name}.speed"] = p.speed
        snap[f"bodies.{name}.retrograde"] = p.retrograde
    a = eph.angles(t, inp["lat"], inp["lon"])
    snap.update({"angles.asc": a.asc, "angles.mc": a.mc, "angles.ramc": a.ramc})
    snap.update({"nodes.true": eph.true_node(t), "nodes.mean": eph.mean_node(t)})
    return snap


def test_ephemeris_has_active_cases():
    ids = {c["id"].split("-card")[0] for c in ACTIVE}
    assert {"GE-01", "GE-02", "GE-06"} <= ids


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_input_has_no_personal_data(case):
    # 152-ФЗ: имя, пол и прочее о человеке в кейс не кладём — только место и момент
    assert set(case["input"]) <= ALLOWED_INPUT


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_input_local_time_matches_utc(case):
    inp = case["input"]
    local = datetime.fromisoformat(f"{inp['local_date']}T{inp['local_time']}{inp['utc_offset']}")
    utc = datetime.fromisoformat(inp["utc"].replace("Z", "+00:00"))
    assert local == utc


@pytest.mark.parametrize("case", ACTIVE, ids=[c["id"] for c in ACTIVE])
def test_active_case_matches_reference(case):
    snap = _chart(case["input"])
    misses = []
    for exp in case["expected"]:
        got = snap[exp["path"]]
        if exp.get("exact"):
            ok = got == exp["value"]
            diff = None
        else:
            assert exp.get("unit") == "arcsec", exp["path"]
            diff = abs((got - exp["value"] + 180.0) % 360.0 - 180.0) * 3600.0
            ok = diff <= exp["tolerance"]
        if not ok:
            misses.append((exp["path"], exp.get("shown"), got, diff))
    assert not misses, misses
