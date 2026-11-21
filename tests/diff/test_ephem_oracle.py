"""G17-S1, шаг 2д: дифф `_ephem` против Swiss Ephemeris по допускам ENGINE-SPEC §2.11.

Случайные моменты с фиксированным seed. Быстрая выборка идёт в make verify и slice-check;
`-m full` — длинный прогон (make spike-full) на той же логике и тех же допусках.
Скорости в §2.11 не нормированы: допуск 2·10⁻⁴ °/сут — свой, см. WORKLOG шаг 2д.
"""

import random

import pytest

from lunora.calc import _ephem as eph

SEED = 20261121
FAST, FULL = 120, 3000

TOL_PLANET = 0.05  # ″, Солнце–Плутон
TOL_MOON = 0.1
TOL_ANGLES_PAST = 0.05  # ASC, MC до 2026 при одинаковых координатах и UT1
TOL_ANGLES_FUTURE = 5.0  # 2027–2100: разные прогнозы ΔT
TOL_POLAR = 0.05
TOL_PLACIDUS = 0.05
TOL_AYANAMSHA = 0.001
TOL_MEAN_NODE = 0.5
TOL_TRUE_NODE = 0.1
TOL_SPEED = 2e-4  # °/сут
TOL_NEAR_SUN = 0.5  # ″, тело ближе 1° к Солнцу (отклонение света у лимба)
TOL_SPEED_NEAR_SUN = 3e-3  # °/сут, там же

SWE_ID = {
    "sun": "SUN",
    "moon": "MOON",
    "mercury": "MERCURY",
    "venus": "VENUS",
    "mars": "MARS",
    "jupiter": "JUPITER",
    "saturn": "SATURN",
    "uranus": "URANUS",
    "neptune": "NEPTUNE",
    "pluto": "PLUTO",
}


def arcsec(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0) * 3600.0


def moments(n: int, y0: int, y1: int, salt: int):
    """n моментов TT, равномерно в [y0-01-01, y1-12-31] UTC; seed фиксирован."""
    ts = eph.timescale()
    rnd = random.Random(SEED + salt)
    a, b = ts.utc(y0, 1, 1).tt, ts.utc(y1, 12, 31).tt
    return [ts.tt_jd(rnd.uniform(a, b)) for _ in range(n)], rnd


def _calc(swe, t, ipl):
    flags = swe.FLG_JPLEPH | swe.FLG_SPEED
    r, ret = swe.calc(t.tt, ipl, flags)
    assert ret & swe.FLG_JPLEPH, "SE откатился с JPL-файла — оракул недействителен"
    return r


def _elongation(t, name: str) -> float:
    k = eph._kernel()
    e = k["earth"].at(t)
    sun = e.observe(k[eph._TARGETS["sun"]]).apparent()
    return sun.separation_from(e.observe(k[eph._TARGETS[name]]).apparent()).degrees


def _sizes():
    return [pytest.param(FAST, id="fast"), pytest.param(FULL, id="full", marks=pytest.mark.full)]


@pytest.mark.parametrize("n", _sizes())
def test_bodies_longitude_and_speed(swe, n):
    ts, _ = moments(n, 1900, 2100, salt=1)
    worst = {}
    for t in ts:
        for name in eph.BODIES:
            r = _calc(swe, t, getattr(swe, SWE_ID[name]))
            p = eph.body(t, name)
            d = arcsec(p.lon, r[0])
            tol = TOL_MOON if name == "moon" else TOL_PLANET
            tol_speed = TOL_SPEED
            if name not in ("sun", "moon") and _elongation(t, name) < 1.0:
                # за диском Солнца / у лимба модели отклонения света у SE и Skyfield
                # расходятся (Нептун в 0,16° от центра: 0,07″) — тело невидимо, допуск шире
                tol, tol_speed = TOL_NEAR_SUN, TOL_SPEED_NEAR_SUN
            assert d <= tol, (name, t.utc_iso(), d)
            assert abs(p.speed - r[3]) <= tol_speed, (name, t.utc_iso(), p.speed, r[3])
            worst[name] = max(worst.get(name, 0.0), d)
    assert set(worst) == set(eph.BODIES)


@pytest.mark.parametrize("n", _sizes())
def test_asc_mc_past(swe, n):
    ts, rnd = moments(n, 1900, 2026, salt=2)
    for t in ts:
        lat, lon = rnd.uniform(-66.0, 66.0), rnd.uniform(-180.0, 180.0)
        a = eph.angles(t, lat, lon)
        _, ascmc = swe.houses_ex(t.ut1, lat, lon, b"W")
        assert arcsec(a.ramc, ascmc[2]) <= TOL_ANGLES_PAST, (t.utc_iso(), lat, lon)
        assert arcsec(a.asc, ascmc[0]) <= TOL_ANGLES_PAST, (t.utc_iso(), lat, lon)
        assert arcsec(a.mc, ascmc[1]) <= TOL_ANGLES_PAST, (t.utc_iso(), lat, lon)


@pytest.mark.parametrize("n", _sizes())
def test_asc_mc_future(swe, n):
    # 2027–2100. После 2050 SE берёт долгосрочную формулу звёздного времени: при том же UT1
    # RAMC расходится до ~1,9″ (измерено, WORKLOG шаг 2д). ASC усиливает это с широтой,
    # поэтому допуск §2.11 (5″) держим на |φ| ≤ 50°, а саму формулу углов на |φ| ≤ 66°
    # проверяет оракул при одинаковых θ и ε (test_angles_same_ramc_and_obliquity).
    ts, rnd = moments(n, 2027, 2100, salt=7)
    for t in ts:
        lat, lon = rnd.uniform(-50.0, 50.0), rnd.uniform(-180.0, 180.0)
        a = eph.angles(t, lat, lon)
        _, ascmc = swe.houses_ex(t.ut1, lat, lon, b"W")
        assert arcsec(a.ramc, ascmc[2]) <= 2.5, (t.utc_iso(), lat, lon)
        assert arcsec(a.asc, ascmc[0]) <= TOL_ANGLES_FUTURE, (t.utc_iso(), lat, lon)
        assert arcsec(a.mc, ascmc[1]) <= TOL_ANGLES_FUTURE, (t.utc_iso(), lat, lon)


@pytest.mark.parametrize("n", _sizes())
def test_angles_same_ramc_and_obliquity(swe, n):
    ts, rnd = moments(n, 1900, 2100, salt=8)
    for t in ts:
        lat, lon = rnd.uniform(-66.0, 66.0), rnd.uniform(-180.0, 180.0)
        a = eph.angles(t, lat, lon)
        _, ascmc = swe.houses_armc(a.ramc, lat, a.obliquity, b"W")
        assert arcsec(a.asc, ascmc[0]) <= TOL_ANGLES_PAST, (t.utc_iso(), lat, lon)
        assert arcsec(a.mc, ascmc[1]) <= TOL_ANGLES_PAST, (t.utc_iso(), lat, lon)


@pytest.mark.parametrize("n", _sizes())
def test_polar_asc_no_flips(swe, n):
    # GE-04: |φ| 66,6–89,5°, 1950–2024. Переворотов на 180° — ноль на полном конвейере
    # (houses_ex от UT1). Допуск 0,05″ — при одинаковых θ и ε: у полярного круга dASC/dθ
    # доходит до ×40, и расхождение RAMC в 0,001″ само по себе даёт 0,05–0,08″ (WORKLOG 2д).
    ts, rnd = moments(n, 1950, 2024, salt=3)
    flips = 0
    for t in ts:
        lat = rnd.choice((1, -1)) * rnd.uniform(66.6, 89.5)
        lon = rnd.uniform(-180.0, 180.0)
        a = eph.angles(t, lat, lon)
        _, full = swe.houses_ex(t.ut1, lat, lon, b"W")
        if arcsec(a.asc, full[0]) > 90 * 3600:
            flips += 1
        _, same = swe.houses_armc(a.ramc, lat, a.obliquity, b"W")
        assert arcsec(a.asc, same[0]) <= TOL_POLAR, (t.utc_iso(), lat, lon)
    assert flips == 0


@pytest.mark.parametrize("n", _sizes())
def test_placidus_same_ramc_and_obliquity(swe, n):
    ts, rnd = moments(n, 1900, 2100, salt=4)
    for t in ts:
        lat, lon = rnd.uniform(-66.0, 66.0), rnd.uniform(-180.0, 180.0)
        a = eph.angles(t, lat, lon)
        ours = eph.placidus(a.ramc, lat, a.obliquity)
        cusps, _ = swe.houses_armc(a.ramc, lat, a.obliquity, b"P")
        for k in range(12):
            assert arcsec(ours[k], cusps[k]) <= TOL_PLACIDUS, (t.utc_iso(), lat, k + 1)


@pytest.mark.parametrize("n", _sizes())
def test_lahiri_mean_ayanamsha(swe, n):
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    ts, _ = moments(n, 1900, 2100, salt=5)
    for t in ts:
        _, value = swe.get_ayanamsa_ex(t.tt, swe.FLG_JPLEPH | swe.FLG_NONUT)
        assert arcsec(eph.ayanamsha_lahiri_mean(t), value) <= TOL_AYANAMSHA, t.utc_iso()


@pytest.mark.parametrize("n", _sizes())
def test_nodes(swe, n):
    ts, _ = moments(n, 1900, 2100, salt=6)
    for t in ts:
        mean = _calc(swe, t, swe.MEAN_NODE)
        true = _calc(swe, t, swe.TRUE_NODE)
        assert arcsec(eph.mean_node(t), mean[0]) <= TOL_MEAN_NODE, t.utc_iso()
        assert arcsec(eph.true_node(t), true[0]) <= TOL_TRUE_NODE, t.utc_iso()
