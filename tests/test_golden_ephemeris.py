"""G17-S1: golden-кейсы слоя `ephemeris` (GE-01, GE-02, GE-06 …) против `lunora.calc._ephem`.

Кейсы — tests/golden/**/*.yaml (формат ARCHITECTURE §6.2, проверяет golden_audit). Раннер
берёт каждый active-кейс слоя ephemeris, считает карту по его входу и сверяет каждое
ожидание `path` с допуском. 152-ФЗ: во входе кейса — только место, время и координаты.
"""

import math
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


def _moment(inp: dict) -> datetime:
    return datetime.fromisoformat(inp["utc"].replace("Z", "+00:00"))


def _chart(inp: dict, t=None) -> dict:
    """Плоский снимок карты: путь → значение (пути как в expected)."""
    t = t if t is not None else eph.instant(_moment(inp))
    snap: dict = {}
    for name, p in eph.bodies(t).items():
        snap[f"bodies.{name}.lon"] = p.lon
        snap[f"bodies.{name}.speed"] = p.speed
        snap[f"bodies.{name}.retrograde"] = p.retrograde
    a = eph.angles(t, inp["lat"], inp["lon"])
    snap.update({"angles.asc": a.asc, "angles.mc": a.mc, "angles.ramc": a.ramc})
    snap.update({"nodes.true": eph.true_node(t), "nodes.mean": eph.mean_node(t)})
    first = math.floor(a.asc / 30.0)
    snap.update({f"houses.whole_sign.{k}": float((first + k - 1) % 12 * 30) for k in range(1, 13)})
    cusps = eph.placidus(a.ramc, inp["lat"], a.obliquity)
    if not isinstance(cusps, eph.NotComputed):
        snap.update({f"houses.placidus.{k + 1}": c for k, c in enumerate(cusps)})
    return snap


def _misses(case: dict, snap: dict) -> list:
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
    return misses


def test_ephemeris_has_active_cases():
    ids = {c["id"][:5] for c in ACTIVE}
    assert {"GE-01", "GE-02", "GE-03", "GE-04", "GE-05", "GE-06"} <= ids


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
    assert not _misses(case, _chart(case["input"]))


PRE_1972 = [c for c in ACTIVE if _moment(c["input"]).year < 1972 and c["id"].startswith("GE-03")]


def test_ge03_cases_exist():
    assert PRE_1972, "нет active GE-03 — шкала UT1 до 1972 не проверена эталоном"


@pytest.mark.parametrize("case", PRE_1972, ids=[c["id"] for c in PRE_1972])
def test_pre1972_case_rejects_utc_reading(case):
    # GE-03: тот же вход, прочитанный как UTC, а не UT1 (§2.2), эталон должен отвергнуть
    m = _moment(case["input"])
    as_utc = eph.timescale().utc(m.year, m.month, m.day, m.hour, m.minute, m.second)
    paths = {p for p, *_ in _misses(case, _chart(case["input"], as_utc))}
    assert {"angles.asc", "angles.mc"} <= paths
