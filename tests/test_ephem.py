"""G17-S1, шаг 2в: эфемеридный слой `lunora.calc._ephem` (Skyfield + DE440s, ADR-001).

Ожидаемые значения — примеры ENGINE-SPEC-РАСЧЕТ §2.2–§2.7 (карты A–D, §0.5) и снимок
JPL Horizons (tests/fixtures/horizons/control_dates.json, DE441). Примеры спеки — не внешний
эталон (§0.5), а проверка, что правило понято так же; внешний эталон — Horizons здесь
и astro.com в golden-кейсах. Дифф против Swiss Ephemeris — tests/diff/.
"""

import json
import pathlib
from datetime import UTC, datetime, timedelta, timezone

import pytest

from lunora.calc import _ephem as eph

ROOT = pathlib.Path(__file__).resolve().parents[1]
HORIZONS = json.loads(
    (ROOT / "tests" / "fixtures" / "horizons" / "control_dates.json").read_text(encoding="utf-8")
)
ARCSEC = 1 / 3600

# сквозные карты ENGINE-SPEC §0.5: момент UTC (гражданское минус пояс), широта, долгота
CARD = {
    "A": (datetime(1984, 2, 4, 11, 0, tzinfo=UTC), 48.7080, 44.5133),
    "B": (datetime(1987, 6, 15, 8, 0, tzinfo=UTC), 55.7558, 37.6173),
    "C": (datetime(1990, 12, 22, 20, 40, tzinfo=UTC), 68.9585, 33.0827),
    "D": (datetime(1962, 8, 9, 3, 15, tzinfo=UTC), 59.9386, 30.3141),
}


def dms(sign: int, d: int, m: int, s: float) -> float:
    """Долгота из «d°m′s″ знака» (0 = Овен … 11 = Рыбы)."""
    return sign * 30 + d + m / 60 + s / 3600


def adiff(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


def t_of(card: str):
    return eph.instant(CARD[card][0])


# --- §2.2 момент ---------------------------------------------------------------------


def test_instant_rejects_naive_datetime():
    with pytest.raises(ValueError):
        eph.instant(datetime(1984, 2, 4, 11, 0))


def test_instant_accepts_any_aware_offset():
    a = eph.instant(datetime(1984, 2, 4, 15, 0, tzinfo=timezone(timedelta(hours=4))))
    assert a.tt == pytest.approx(t_of("A").tt, abs=1e-12)


@pytest.mark.parametrize(
    ("moment", "scale"),
    [
        (datetime(1971, 12, 31, 23, 59, 59, tzinfo=UTC), "ut1"),
        (datetime(1972, 1, 1, 0, 0, tzinfo=UTC), "utc"),
        (datetime(1950, 6, 15, 6, 0, tzinfo=UTC), "ut1"),
        (datetime(2026, 2, 3, 20, 2, tzinfo=UTC), "utc"),
    ],
)
def test_instant_scale_rule_1972(moment, scale):
    assert eph.instant_scale(moment) == scale


@pytest.mark.parametrize(("year", "delta_s"), [(1930, 17.8), (1950, 13.1), (1960, 9.0)])
def test_instant_before_1972_is_ut1_not_utc(year, delta_s):
    # §2.2: Москва, 15 июня, 09:00 «UT» — разница трактовок utc и ut1
    moment = datetime(year, 6, 15, 9, 0, tzinfo=UTC)
    ts = eph.timescale()
    as_utc = ts.utc(year, 6, 15, 9, 0)
    assert abs(eph.instant(moment).tt - as_utc.tt) * 86400 == pytest.approx(delta_s, abs=0.1)


def test_timescale_is_builtin_no_network():
    # одна и та же закреплённая шкала (builtin), второй вызов — тот же объект
    assert eph.timescale() is eph.timescale()


# --- §2.3 положения тел ---------------------------------------------------------------

# карта A, тропические долготы и скорости (°/сут) — ENGINE-SPEC §2.3
CARD_A_BODIES = {
    "sun": (dms(10, 14, 49, 3.8), 1.0145),
    "moon": (dms(11, 11, 41, 20.1), 11.8559),
    "mercury": (dms(9, 23, 23, 56.7), 1.3907),
    "venus": (dms(9, 11, 51, 42.6), 1.2282),
    "mars": (dms(7, 11, 48, 25.7), 0.4488),
    "jupiter": (dms(9, 3, 15, 42.8), 0.1975),
    "saturn": (dms(7, 16, 2, 7.1), 0.0344),
    "uranus": (dms(8, 12, 45, 47.8), 0.0363),
    "neptune": (dms(9, 0, 31, 17.2), 0.0292),
    "pluto": (dms(7, 2, 8, 11.4), -0.0002),
}


def test_ten_bodies_always_present():
    # регрессия прототипа (04_product.md): пропало Солнце — тест падает
    assert tuple(CARD_A_BODIES) == eph.BODIES
    got = eph.bodies(t_of("A"))
    assert tuple(got) == eph.BODIES


@pytest.mark.parametrize("name", list(CARD_A_BODIES))
def test_card_a_longitude_and_speed(name):
    lon, speed = CARD_A_BODIES[name]
    p = eph.body(t_of("A"), name)
    assert abs(adiff(p.lon, lon)) <= 0.06 * ARCSEC
    assert p.speed == pytest.approx(speed, abs=6e-5)
    assert 0.0 <= p.lon < 360.0


def test_retrograde_is_negative_speed():
    bodies = eph.bodies(t_of("A"))
    assert bodies["pluto"].retrograde
    assert not bodies["sun"].retrograde


def test_unknown_body_is_error():
    with pytest.raises(KeyError):
        eph.body(t_of("A"), "chiron")  # Хирон — out_of_v1 (§2.10)


# --- JPL Horizons (DE441), 10 контрольных дат -------------------------------------------


def _horizons_times():
    ts = eph.timescale()
    return [ts.tt_jd(d["jd_tt"]) for d in HORIZONS["dates"]]


def test_horizons_fixture_shape():
    assert len(HORIZONS["dates"]) == 10
    assert set(HORIZONS["bodies"]) == set(eph.BODIES)
    assert {b["source"] for b in HORIZONS["bodies"].values()} == {"DE441"}


@pytest.mark.parametrize("name", list(CARD_A_BODIES))
def test_longitude_matches_horizons(name):
    # Horizons ObsEcLon — эклиптика даты по IAU76/80, у нас IAU2006/2000A: общий для всех тел
    # сдвиг рамки до ~0,25″ на краях 1901/2099. Допуск 0,3″.
    ref = HORIZONS["bodies"][name]["lon"]
    for t, lon in zip(_horizons_times(), ref, strict=True):
        assert abs(adiff(eph.body(t, name).lon, lon)) <= 0.3 * ARCSEC


@pytest.mark.parametrize("name", [b for b in CARD_A_BODIES if b != "sun"])
def test_elongation_from_sun_matches_horizons(name):
    # разность «тело − Солнце» снимает сдвиг рамки: остаётся эфемерида и редукция
    sun = HORIZONS["bodies"]["sun"]["lon"]
    ref = HORIZONS["bodies"][name]["lon"]
    for t, lon, s in zip(_horizons_times(), ref, sun, strict=True):
        ours = adiff(eph.body(t, name).lon, eph.body(t, "sun").lon)
        assert abs(adiff(ours, adiff(lon, s))) <= 0.03 * ARCSEC


def test_ramc_matches_horizons_1972_2026():
    # LAST Horizons на точке карты A. Вне 1972–2026 расходится ΔT/UT1 Horizons — не сверяем.
    site = HORIZONS["site_a"]
    checked = 0
    for d, t, last in zip(HORIZONS["dates"], _horizons_times(), site["last_hours"], strict=True):
        if not 1972 <= d["civil"][0] <= 2026:
            continue
        assert abs(adiff(eph.ramc(t, site["lon"]), last * 15)) <= 0.5 * ARCSEC
        checked += 1
    assert checked == 5


# --- §2.4 ASC, MC, RAMC ------------------------------------------------------------------

ANGLES = {
    # RAMC, ε, MC, ASC — ENGINE-SPEC §2.4
    "A": (343.31935, 23.442151, dms(11, 11, 54, 46.0), dms(3, 11, 11, 47.8)),
    "B": (60.68963, 23.443265, dms(2, 2, 44, 54.1), dms(5, 10, 31, 34.6)),
    "C": (74.22217, 23.441595, dms(2, 15, 28, 1.0), dms(5, 21, 55, 37.2)),
}


@pytest.mark.parametrize("card", list(ANGLES))
def test_angles_card(card):
    ramc, eps, mc, asc = ANGLES[card]
    _, lat, lon = CARD[card]
    a = eph.angles(t_of(card), lat, lon)
    assert a.ramc == pytest.approx(ramc, abs=1e-5)
    assert a.obliquity == pytest.approx(eps, abs=1e-6)
    assert abs(adiff(a.mc, mc)) <= 0.06 * ARCSEC
    assert abs(adiff(a.asc, asc)) <= 0.06 * ARCSEC
    assert a.dc == pytest.approx((a.asc + 180) % 360)
    assert a.ic == pytest.approx((a.mc + 180) % 360)


def test_true_obliquity_is_mean_plus_nutation():
    t = t_of("A")
    dpsi, deps = eph.nutation(t)
    assert eph.true_obliquity(t) == pytest.approx(eph.mean_obliquity(t) + deps, abs=1e-12)
    assert dpsi == pytest.approx(-0.004099, abs=1e-6)  # §2.7, пример A


@pytest.mark.parametrize("lat", [66.6, 70.0, 74.5, 78.0, 82.0, 86.0, 89.5, -70.0, -78.0])
def test_polar_rule_asc_in_eastern_half(lat):
    # §2.4: (ASC − MC) mod 360 < 180 — без переворота ASC на 180° (GE-04)
    for hour in range(0, 24, 2):
        t = eph.instant(datetime(1990, 12, 22, hour, 0, tzinfo=UTC))
        a = eph.angles(t, lat, 33.0)
        assert (a.asc - a.mc) % 360 < 180


# --- §2.5 дома ---------------------------------------------------------------------------


def test_whole_sign_card_a():
    t = t_of("A")
    _, lat, lon = CARD["A"]
    asc = eph.angles(t, lat, lon).asc
    b = eph.bodies(t)
    houses = {n: eph.whole_sign_house(p.lon, asc) for n, p in b.items()}
    assert houses["mars"] == houses["saturn"] == 5
    assert houses["sun"] == 8
    assert houses["moon"] == 9
    assert eph.whole_sign_house(eph.angles(t, lat, lon).mc, asc) == 9


def test_whole_sign_cards_b_c():
    tb, tc = t_of("B"), t_of("C")
    asc_b = eph.angles(tb, *CARD["B"][1:]).asc
    asc_c = eph.angles(tc, *CARD["C"][1:]).asc
    b = eph.bodies(tb)
    assert eph.whole_sign_house(b["sun"].lon, asc_b) == 10
    assert eph.whole_sign_house(b["venus"].lon, asc_b) == 10
    assert eph.whole_sign_house(b["moon"].lon, asc_b) == 6
    assert eph.whole_sign_house(eph.body(tc, "jupiter").lon, asc_c) == 12


def test_whole_sign_half_open_boundary():
    # GW-11: 30° ровно — уже Телец; 29,999…° — ещё Овен
    assert eph.whole_sign_house(30.0, 0.0) == 2
    assert eph.whole_sign_house(29.9999999, 0.0) == 1
    assert eph.whole_sign_house(359.9999999, 15.0) == 12
    assert eph.whole_sign_house(0.0, 359.0) == 2


PLACIDUS = {
    # куспиды XI, XII, II, III — ENGINE-SPEC §2.5 (округлены до 1″)
    "A": (dms(0, 17, 15, 44), dms(2, 2, 19, 2), dms(3, 28, 4, 3), dms(4, 17, 5, 47)),
    "D": (dms(2, 22, 49, 2), dms(4, 0, 11, 4), dms(5, 12, 45, 7), dms(6, 5, 24, 35)),
}


@pytest.mark.parametrize("card", list(PLACIDUS))
def test_placidus_cusps(card):
    _, lat, lon = CARD[card]
    t = t_of(card)
    a = eph.angles(t, lat, lon)
    cusps = eph.placidus(a.ramc, lat, a.obliquity)
    xi, xii, ii, iii = PLACIDUS[card]
    for got, want in zip((cusps[10], cusps[11], cusps[1], cusps[2]), (xi, xii, ii, iii),
                         strict=True):
        assert abs(adiff(got, want)) <= 0.6 * ARCSEC
    assert abs(adiff(cusps[0], a.asc)) <= 1e-9
    assert abs(adiff(cusps[9], a.mc)) <= 1e-9
    for k in range(6):
        assert abs(adiff(cusps[k + 6], cusps[k] + 180)) <= 1e-9


def test_placidus_not_applicable_above_66_56():
    _, lat, lon = CARD["C"]
    a = eph.angles(t_of("C"), lat, lon)
    res = eph.placidus(a.ramc, lat, a.obliquity)
    assert isinstance(res, eph.NotComputed)
    assert res.reason == "not_applicable_latitude"
    assert isinstance(eph.placidus(a.ramc, -66.57, a.obliquity), eph.NotComputed)
    assert not isinstance(eph.placidus(a.ramc, 66.56, a.obliquity), eph.NotComputed)


# --- §2.6 узлы ---------------------------------------------------------------------------


def test_nodes_card_a():
    t = t_of("A")
    assert abs(adiff(eph.true_node(t), dms(2, 13, 49, 37))) <= 0.6 * ARCSEC
    assert abs(adiff(eph.mean_node(t), dms(2, 12, 42, 15))) <= 0.6 * ARCSEC
    assert eph.south_node(eph.true_node(t)) == pytest.approx((eph.true_node(t) + 180) % 360)


# --- §2.7 айанамша Лахири ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("ymd", "value"),
    [
        ((1900, 1, 1), 22.4605306),
        ((1956, 3, 21), 23.2455610),
        ((2000, 1, 1), 23.8570732),
        ((2026, 1, 1), 24.2203039),
    ],
)
def test_lahiri_mean_anchors(ymd, value):
    t = eph.timescale().tt(*ymd)
    assert eph.ayanamsha_lahiri_mean(t) == pytest.approx(value, abs=2e-7)


def test_lahiri_card_a_moon_sidereal():
    t = t_of("A")
    assert eph.ayanamsha_lahiri_mean(t) == pytest.approx(23.634897, abs=1e-6)
    moon = eph.body(t, "moon").lon
    assert eph.sidereal(moon, t) == pytest.approx(318.05812, abs=1e-5)


# --- данные и версии --------------------------------------------------------------------


def test_versions_record_file_and_library():
    v = eph.versions()
    assert v["ephemeris"] == "DE440s"
    assert v["sha256"] == "c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2"
    assert v["skyfield"] == "1.55"


def test_missing_ephemeris_is_explicit_error(tmp_path, monkeypatch):
    monkeypatch.setenv("LUNORA_EPHEMERIS_DIR", str(tmp_path))
    eph.reset_cache()
    try:
        with pytest.raises(eph.EphemerisDataError, match="make setup"):
            eph.body(t_of("A"), "sun")
    finally:
        monkeypatch.delenv("LUNORA_EPHEMERIS_DIR")
        eph.reset_cache()


def test_tampered_ephemeris_is_rejected(tmp_path, monkeypatch):
    (tmp_path / "de440s.bsp").write_bytes(b"not an ephemeris")
    monkeypatch.setenv("LUNORA_EPHEMERIS_DIR", str(tmp_path))
    eph.reset_cache()
    try:
        with pytest.raises(eph.EphemerisDataError, match="SHA-256"):
            eph.body(t_of("A"), "sun")
    finally:
        monkeypatch.delenv("LUNORA_EPHEMERIS_DIR")
        eph.reset_cache()


def test_runtime_does_not_import_oracle():
    src = (ROOT / "src" / "lunora" / "calc" / "_ephem.py").read_text(encoding="utf-8")
    assert "swisseph" not in src
