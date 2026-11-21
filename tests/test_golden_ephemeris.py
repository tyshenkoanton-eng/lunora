"""G17-S1: golden-кейсы слоя `ephemeris` (GE-01 … GE-10) против `lunora.calc._ephem`.

Кейсы — tests/golden/**/*.yaml (формат ARCHITECTURE §6.2, проверяет golden_audit). Раннер
берёт каждый active-кейс слоя ephemeris, считает карту по его входу и сверяет каждое
ожидание `path` с допуском. 152-ФЗ: во входе кейса — только место, время и координаты.

Входы без карты (GE-07, GE-08, якоря GE-10): `tt` — момент в шкале TT; `target_lon` +
`hint_utc` — искать момент долготы Солнца (§2.9) рядом с подсказкой. Единица `s` —
секунды (для ISO-моментов — разность моментов), `arcsec` — угловые секунды.
"""

import importlib.util
import math
import pathlib
import sys
from datetime import UTC, datetime, timedelta

import pytest
import yaml

from lunora.calc import _ephem as eph

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
ALLOWED_INPUT = {
    "place_id",
    "local_date",
    "local_time",
    "utc_offset",
    "utc",
    "lat",
    "lon",
    "tt",
    "target_lon",
    "hint_utc",
}
J2000 = datetime(2000, 1, 1, 12, 0)
HKT = timedelta(hours=8)

_spec = importlib.util.spec_from_file_location(
    "hko_vendor", ROOT / "scripts" / "spike" / "hko_vendor.py"
)
hko = importlib.util.module_from_spec(_spec)
sys.modules["hko_vendor"] = hko
_spec.loader.exec_module(hko)


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


def _tt_iso(jd_tt: float) -> str:
    return (J2000 + timedelta(days=jd_tt - 2451545.0)).isoformat(timespec="milliseconds")


def _term(inp: dict) -> dict:
    hint = datetime.fromisoformat(inp["hint_utc"].replace("Z", "+00:00"))
    t = eph.sun_longitude_instant(inp["target_lon"], eph.timescale().from_datetime(hint))
    utc = t.utc_datetime().astimezone(UTC).replace(tzinfo=None)
    return {
        "sun_term.tt": _tt_iso(t.tt),
        "sun_term.utc": utc.isoformat(timespec="milliseconds"),
        "sun_term.date_hkt": (utc + HKT).date().isoformat(),
    }


def _chart(inp: dict, t=None) -> dict:
    """Плоский снимок карты: путь → значение (пути как в expected)."""
    if "target_lon" in inp:
        return _term(inp)
    if t is None and "tt" in inp:
        d = datetime.fromisoformat(inp["tt"])
        t = eph.timescale().tt(d.year, d.month, d.day, d.hour, d.minute, d.second)
    t = t if t is not None else eph.instant(_moment(inp))
    snap: dict = {
        "ayanamsha.lahiri_mean": eph.ayanamsha_lahiri_mean(t),
        "ayanamsha.lahiri_true": eph.ayanamsha_lahiri_true(t),
    }
    if "lat" not in inp:
        return snap
    st = eph.true_solar_time(t, inp["lon"])
    snap.update(
        {
            "solar_time.lmt": st.lmt.isoformat(timespec="milliseconds"),
            "solar_time.tst": st.tst.isoformat(timespec="milliseconds"),
            "solar_time.tst_date": st.tst.date().isoformat(),
            "solar_time.eot": st.eot_minutes * 60.0,
        }
    )
    for name, p in eph.bodies(t).items():
        snap[f"bodies.{name}.lon"] = p.lon
        snap[f"bodies.{name}.speed"] = p.speed
        snap[f"bodies.{name}.retrograde"] = p.retrograde
        snap[f"bodies.{name}.sidereal"] = eph.sidereal(p.lon, t)
    a = eph.angles(t, inp["lat"], inp["lon"])
    snap.update({"angles.asc": a.asc, "angles.mc": a.mc, "angles.ramc": a.ramc})
    snap.update({"nodes.true": eph.true_node(t), "nodes.mean": eph.mean_node(t)})
    first = math.floor(a.asc / 30.0)
    snap.update({f"houses.whole_sign.{k}": float((first + k - 1) % 12 * 30) for k in range(1, 13)})
    cusps = eph.placidus(a.ramc, inp["lat"], a.obliquity)
    if isinstance(cusps, eph.NotComputed):
        snap["houses.placidus.status"] = cusps.reason
    else:
        snap["houses.placidus.status"] = "computed"
        snap.update({f"houses.placidus.{k + 1}": c for k, c in enumerate(cusps)})
    return snap


def _misses(case: dict, snap: dict) -> list:
    misses = []
    for exp in case["expected"]:
        got = snap[exp["path"]]
        if exp.get("exact"):
            ok = got == exp["value"]
            diff = None
        elif exp.get("unit") == "s":
            if isinstance(exp["value"], str):
                a, b = datetime.fromisoformat(got), datetime.fromisoformat(exp["value"])
                diff = abs((a - b).total_seconds())
            else:
                diff = abs(got - exp["value"])
            ok = diff <= exp["tolerance"]
        else:
            assert exp.get("unit") == "arcsec", exp["path"]
            diff = abs((got - exp["value"] + 180.0) % 360.0 - 180.0) * 3600.0
            ok = diff <= exp["tolerance"]
        if not ok:
            misses.append((exp["path"], exp.get("shown"), got, diff))
    return misses


def test_ephemeris_has_active_cases():
    ids = {c["id"][:5] for c in ACTIVE}
    assert {f"GE-{k:02d}" for k in range(1, 11)} <= ids


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_input_has_no_personal_data(case):
    # 152-ФЗ: имя, пол и прочее о человеке в кейс не кладём — только место и момент
    assert set(case["input"]) <= ALLOWED_INPUT


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_input_local_time_matches_utc(case):
    inp = case["input"]
    if "local_date" not in inp:
        pytest.skip("вход без местного времени (момент TT или поиск термина)")
    local = datetime.fromisoformat(f"{inp['local_date']}T{inp['local_time']}{inp['utc_offset']}")
    utc = datetime.fromisoformat(inp["utc"].replace("Z", "+00:00"))
    assert local == utc


@pytest.mark.parametrize("case", ACTIVE, ids=[c["id"] for c in ACTIVE])
def test_active_case_matches_reference(case):
    assert not _misses(case, _chart(case["input"]))


PRE_1972 = [
    c for c in ACTIVE if c["id"].startswith("GE-03") and _moment(c["input"]).year < 1972
]


def test_ge03_cases_exist():
    assert PRE_1972, "нет active GE-03 — шкала UT1 до 1972 не проверена эталоном"


@pytest.mark.parametrize("case", PRE_1972, ids=[c["id"] for c in PRE_1972])
def test_pre1972_case_rejects_utc_reading(case):
    # GE-03: тот же вход, прочитанный как UTC, а не UT1 (§2.2), эталон должен отвергнуть
    m = _moment(case["input"])
    as_utc = eph.timescale().utc(m.year, m.month, m.day, m.hour, m.minute, m.second)
    paths = {p for p, *_ in _misses(case, _chart(case["input"], as_utc))}
    assert {"angles.asc", "angles.mc"} <= paths


HKO_CHECKS = [(c, e) for c in ACTIVE for e in c["expected"] if e.get("against") == "hko"]


def test_ge07_08_cover_lichun_1984_and_twelve_jie_2026():
    terms = {(c["id"][:5], c["input"]["target_lon"]) for c in ACTIVE if "target_lon" in c["input"]}
    assert ("GE-07", 315.0) in terms
    jie = {hko.term_longitude(i) for i in hko.JIE_INDEXES}
    assert {lon for k, lon in terms if k == "GE-08"} == jie


@pytest.mark.parametrize(
    ("case", "exp"), HKO_CHECKS, ids=[f"{c['id']}:{e['path']}" for c, e in HKO_CHECKS]
)
def test_hko_expectation_equals_vendored_table(case, exp):
    # эталон обсерватории в кейсе не вписан руками: он равен вендоренному файлу (SHA-256)
    lon = case["input"]["target_lon"]
    year = int(case["input"]["hint_utc"][:4])
    index = next(i for i in range(24) if hko.term_longitude(i) == lon)
    if exp["path"] == "sun_term.date_hkt":
        assert list(hko.load_term_dates(year).values())[index].isoformat() == exp["value"]
    else:
        hkt = hko.load_term_times(year)[index][1]
        assert (hkt - HKT).isoformat(timespec="milliseconds") == exp["value"]


def test_ge09_card_e_true_solar_date_differs_from_clock():
    # §2.8: у карты E на часах 15 июня, а по истинному солнечному времени — 14 июня
    case = next(c for c in ACTIVE if c["id"] == "GE-09-tst-card-E")
    tst_date = next(e["value"] for e in case["expected"] if e["path"] == "solar_time.tst_date")
    assert case["input"]["local_date"] == "1987-06-15" and tst_date == "1987-06-14"
