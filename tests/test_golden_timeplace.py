"""G17-S1: golden-кейсы слоя `timeplace` — смещение UTC на дату рождения против astro.com.

Кейсы — tests/golden/timeplace/*.yaml (формат ARCHITECTURE §6.2). Конвейер как в продукте:
place_id GeoNames → зона из вендоренного снимка (справочника мест в рантайме ещё нет) →
`timeplace.resolve` по IANA 2026f → смещение. Эталон — Univ.Time с бланка astro.com
(смещение = местное время − Univ.Time). 152-ФЗ: во входе только место и время.
"""

import importlib.util
import pathlib
import sys
from datetime import date, datetime, time, timedelta

import pytest
import yaml

from lunora.timeplace import NonexistentLocalTime, resolve
from lunora.timeplace.places import lookup
from lunora.timeplace.resolve import _zone

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
ALLOWED_INPUT = {"place_id", "local_date", "local_time", "univ_time"}

_spec = importlib.util.spec_from_file_location(
    "geonames_vendor", ROOT / "scripts" / "spike" / "geonames_vendor.py"
)
gv = importlib.util.module_from_spec(_spec)
sys.modules["geonames_vendor"] = gv
_spec.loader.exec_module(gv)


def _cases():
    out = []
    for path in sorted(GOLDEN.rglob("*.y*ml")):
        if "evidence" in path.parts:
            continue
        for case in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if case and case.get("layer") == "timeplace":
                out.append(case)
    return out


CASES = _cases()
ACTIVE = [c for c in CASES if c["status"] == "active"]


@pytest.fixture(scope="module")
def cities():
    return gv.load_cities()


def _fmt(off: timedelta) -> str:
    minutes = int(off.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def _snapshot(inp: dict, cities: dict) -> dict:
    # конвейер как в продукте: place_id → минимальный справочник мест S1 → зона и регион
    place = lookup(inp["place_id"])
    zone = place.timezone
    d, t = date.fromisoformat(inp["local_date"]), time.fromisoformat(inp["local_time"])
    try:
        m = resolve(d, t, zone, place_id=inp["place_id"], region=place.region)
    except NonexistentLocalTime:
        # часы перевели вперёд: наше правило — ошибка «уточните время» (план S1, «Перевод часов»).
        # Для сверки с атласом фиксируем смещение, которое действовало до скачка (fold=0).
        before = datetime.combine(d, t).replace(tzinfo=_zone(zone), fold=0).utcoffset()
        return {
            "timeplace.zone": zone,
            "timeplace.status": "nonexistent_local_time",
            "timeplace.offset_before_gap": _fmt(before),
        }
    return {
        "timeplace.zone": zone,
        "timeplace.status": "resolved",
        "timeplace.utc_offset": _fmt(m.hypotheses[0].utc_offset),
        "timeplace.offsets": [_fmt(h.utc_offset) for h in m.hypotheses],
        "timeplace.hypotheses": len(m.hypotheses),
    }


def test_timeplace_has_active_cases():
    assert len(ACTIVE) >= 5


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_input_has_no_personal_data(case):
    assert set(case["input"]) <= ALLOWED_INPUT


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_expected_offset_is_local_minus_univ_time(case):
    # эталон выводится из бланка: смещение = местное время − Univ.Time (через сутки — по модулю)
    inp = case["input"]
    loc = time.fromisoformat(inp["local_time"])
    ut = time.fromisoformat(inp["univ_time"])
    minutes = (loc.hour * 60 + loc.minute - ut.hour * 60 - ut.minute) % (24 * 60)
    if minutes > 14 * 60:
        minutes -= 24 * 60
    expected = {e["path"]: e["value"] for e in case["expected"]}
    # для несуществующего часа атлас берёт смещение до скачка («unchanged clock assumed»)
    key = (
        "timeplace.utc_offset"
        if "timeplace.utc_offset" in expected
        else "timeplace.offset_before_gap"
    )
    assert expected[key] == _fmt(timedelta(minutes=minutes))


@pytest.mark.parametrize("case", ACTIVE, ids=[c["id"] for c in ACTIVE])
def test_active_case_matches_reference(case, cities):
    snap = _snapshot(case["input"], cities)
    misses = [
        (e["path"], e["value"], snap[e["path"]])
        for e in case["expected"]
        if snap[e["path"]] != e["value"]
    ]
    assert not misses, misses


def test_clock_change_cases_cover_gap_and_repeated_hour():
    # план S1, «Перевод часов»: несуществующий час — ошибка, повторённый — две гипотезы
    statuses = {
        e["value"] for c in ACTIVE for e in c["expected"] if e["path"] == "timeplace.status"
    }
    assert "nonexistent_local_time" in statuses
    assert any(
        e["path"] == "timeplace.hypotheses" and e["value"] == 2
        for c in ACTIVE
        for e in c["expected"]
    )
