"""G17-S2d: дифф ведического движка против Swiss Ephemeris (независимый код, группа [oracle]).

Эталон слайса — Jagannatha Hora (ручной, карты A/B/D). Независимую перекрёстную проверку даёт
Swiss Ephemeris (другая реализация эфемерид и редукции, не Skyfield). Две сверки:

1. **Наш движок ↔ SE под той же айанамшей (Лахири).** SE в режиме TRUEPOS (истинные
   геометрические, без аберрации) + средний узел. Долготы совпадают ≤ 2″, раши/накшатры — точно:
   подтверждает, что наша реализация (Skyfield + §2.7) эквивалентна SE при одной настройке.
2. **SE под True Chitrapaksha ↔ JH.** SE воспроизводит снятые долготы JH ≤ 1″: подтверждает, что
   JH = SE True Chitrapaksha + средние узлы + истинные положения (настройки П-2), а наш
   постоянный сдвиг ≈56″ — чистая разница айанамши (Лахири №1 vs True Chitrapaksha), §2.7.

Swiss Ephemeris (AGPL) — только внешний эталон, рантайм от него не зависит (ADR-001,
test_no_oracle_imports: движок `vedic` не импортирует swisseph). Режим Moshier — без файла данных.
"""

from datetime import date, time

import pytest

from lunora.engines import vedic
from lunora.timeplace import resolve

# карта: place_id, дата, время, зона, lat, lon, (UTC y,m,d,hour), JH-долготы (True Chitrapaksha)
CARDS = [
    ("A", "geonames:472757", "1984-02-04", "15:00", "Europe/Volgograd", 48.71378, 44.4976,
     (1984, 2, 4, 11.0),
     {"sun": 291.2082, "moon": 318.0738, "mars": 198.1952, "mercury": 269.7935,
      "jupiter": 249.6534, "venus": 258.2559, "saturn": 202.4220, "rahu": 49.0888}),
    ("B", "geonames:524901", "1987-06-15", "12:00", "Europe/Moscow", 55.75204, 37.61781,
     (1987, 6, 15, 8.0),
     {"sun": 60.0486, "moon": 288.8683, "mars": 82.6519, "mercury": 81.8651,
      "jupiter": 359.7896, "venus": 41.3503, "saturn": 233.7499, "rahu": 344.0743}),
    ("D", "geonames:498817", "1962-08-09", "06:15", "Europe/Moscow", 59.93863, 30.31413,
     (1962, 8, 9, 3.25),
     {"sun": 112.7558, "moon": 208.1004, "mars": 57.9505, "mercury": 123.6075,
      "jupiter": 317.1816, "venus": 157.1431, "saturn": 284.1294, "rahu": 105.0402}),
]
_RU = {"sun": "Сурья", "moon": "Чандра", "mars": "Мангала", "mercury": "Будха",
       "jupiter": "Гуру", "venus": "Шукра", "saturn": "Шани", "rahu": "Раху"}


def _sep(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0) * 3600.0  # угловых секунд


def _se_lon(swe, jd, body, flags):
    return swe.calc_ut(jd, body, flags)[0][0]


@pytest.fixture(scope="module")
def swe():
    s = pytest.importorskip("swisseph")
    s.set_ephe_path(None)  # Moshier: без файла, точность ≤ ~0,001° на 1900–2100
    return s


def _our(card):
    _, pid, d, tt, z, lat, lon, _utc, _jh = card
    m = resolve(date.fromisoformat(d), time.fromisoformat(tt), z, place_id=pid)
    return vedic.chart(m, lat, lon, now=date(2026, 11, 16))


@pytest.mark.parametrize("card", CARDS, ids=[c[0] for c in CARDS])
def test_engine_matches_swiss_ephemeris_lahiri(card, swe):
    """Наш движок ↔ SE под Лахири: долготы ≤ 2″, раши/накшатры точно."""
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    flags = swe.FLG_MOSEPH | swe.FLG_SIDEREAL | swe.FLG_TRUEPOS
    jd = swe.julday(*card[7])
    ch = _our(card)
    planets = {"sun": swe.SUN, "moon": swe.MOON, "mars": swe.MARS, "mercury": swe.MERCURY,
               "jupiter": swe.JUPITER, "venus": swe.VENUS, "saturn": swe.SATURN}
    bad = []
    for key, bid in planets.items():
        se = _se_lon(swe, jd, bid, flags)
        g = ch.grahas[_RU[key]]
        if _sep(g.longitude, se) > 2.0:
            bad.append((key, "Δ″", round(_sep(g.longitude, se), 2)))
        if vedic.RASHIS.index(g.rashi) != int(se // 30):
            bad.append((key, "rashi", g.rashi, int(se // 30)))
        if vedic.nakshatra_index(g.longitude) != vedic.nakshatra_index(se):
            bad.append((key, "nak", g.longitude, se))
    se_node = _se_lon(swe, jd, swe.MEAN_NODE, flags)
    if _sep(ch.grahas["Раху"].longitude, se_node) > 2.0:
        bad.append(("rahu", "Δ″", round(_sep(ch.grahas["Раху"].longitude, se_node), 2)))
    assert not bad, bad


@pytest.mark.parametrize("card", CARDS, ids=[c[0] for c in CARDS])
def test_swiss_true_chitrapaksha_reproduces_jh(card, swe):
    """SE под True Chitrapaksha ↔ снятые долготы JH (≤ 1″): подтверждает настройки П-2."""
    swe.set_sid_mode(swe.SIDM_TRUE_CITRA, 0, 0)
    flags = swe.FLG_MOSEPH | swe.FLG_SIDEREAL | swe.FLG_TRUEPOS
    jd = swe.julday(*card[7])
    jh = card[8]
    planets = {"sun": swe.SUN, "moon": swe.MOON, "mars": swe.MARS, "mercury": swe.MERCURY,
               "jupiter": swe.JUPITER, "venus": swe.VENUS, "saturn": swe.SATURN}
    bad = []
    for key, bid in planets.items():
        if _sep(_se_lon(swe, jd, bid, flags), jh[key]) > 1.0:
            bad.append((key, round(_sep(_se_lon(swe, jd, bid, flags), jh[key]), 2)))
    if _sep(_se_lon(swe, jd, swe.MEAN_NODE, flags), jh["rahu"]) > 1.0:
        bad.append(("rahu", round(_sep(_se_lon(swe, jd, swe.MEAN_NODE, flags), jh["rahu"]), 2)))
    assert not bad, bad


def test_ayanamsha_offset_is_constant(swe):
    """Сдвиг Лахири→True Chitrapaksha постоянен по телам (≈56″) — класс «настройки эталона»."""
    jd = swe.julday(1984, 2, 4, 11.0)
    flags = swe.FLG_MOSEPH | swe.FLG_SIDEREAL | swe.FLG_TRUEPOS
    deltas = []
    for bid in (swe.SUN, swe.MOON, swe.MARS, swe.MERCURY, swe.JUPITER, swe.VENUS, swe.SATURN):
        swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
        lahiri = _se_lon(swe, jd, bid, flags)
        swe.set_sid_mode(swe.SIDM_TRUE_CITRA, 0, 0)
        citra = _se_lon(swe, jd, bid, flags)
        deltas.append(_sep(lahiri, citra))
    assert max(deltas) - min(deltas) < 1.0, deltas  # постоянство ≤ 1″
    assert 40.0 < sum(deltas) / len(deltas) < 70.0, deltas  # ≈56″
