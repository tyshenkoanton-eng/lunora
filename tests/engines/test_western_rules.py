"""G17-S2c: правила западного движка — аспекты §3.7, границы знаков §1.4, инварианты прототипа.

Golden (A/D/C) — в test_golden_western.py. Здесь синтетика правил и регрессия ошибок прототипа
(04_product.md): Солнце не теряется; высшие планеты дают сигнал по дому и аспектам, не по знаку.
"""

from datetime import date, time

import pytest

from lunora.engines import western
from lunora.engines.result import Result
from lunora.timeplace import resolve

# карта A — Волгоград 04.02.1984 15:00
A_IN = dict(place_id="geonames:472757", lat=48.71378, lon=44.4976, zone="Europe/Volgograd")


def _chart_a():
    m = resolve(date(1984, 2, 4), time(15, 0), A_IN["zone"], place_id=A_IN["place_id"])
    return western.chart(m, A_IN["lat"], A_IN["lon"])


@pytest.mark.parametrize(
    "lon,sign",
    [(0.0, "Овен"), (6.0, "Овен"), (29.999722, "Овен"), (30.0, "Телец"),
     (359.9999, "Рыбы"), (360.0, "Овен")],
)
def test_sign_half_open_intervals_gw11(lon, sign):
    assert western.sign_name(lon) == sign


def test_separation_wraps():
    assert western.separation(350.0, 10.0) == pytest.approx(20.0)
    assert western.separation(10.0, 350.0) == pytest.approx(20.0)


def test_aspect_at_orbis_boundary_included():
    # D Солнце–Меркурий: соединение orb 10.843° при пределе 11.0° — аспект есть (§3.7)
    m = resolve(date(1962, 8, 9), time(6, 15), "Europe/Moscow", place_id="geonames:498817")
    ch = western.chart(m, 59.93863, 30.31413)
    key = [a for a in ch.aspects if {a.a, a.b} == {"Солнце", "Меркурий"}]
    assert key and key[0].type == "соединение"
    assert key[0].orb < 11.0


def test_partile_flag_on_tight_aspect():
    ch = _chart_a()
    vm = next(a for a in ch.aspects if {a.a, a.b} == {"Венера", "Марс"})
    assert vm.type == "секстиль" and vm.orb < 0.1 and vm.partile
    ms = next(a for a in ch.aspects if {a.a, a.b} == {"Марс", "Сатурн"})
    assert ms.orb > 1.0 and not ms.partile


def test_applying_vs_separating_is_boolean():
    ch = _chart_a()
    assert all(isinstance(a.applying, bool) for a in ch.aspects)


def test_invariant_sun_present_with_septener():
    ch = _chart_a()
    assert western.has_sun(ch)
    assert "Солнце" in ch.planets and ch.planets["Солнце"].sign == "Водолей"


def test_polar_placidus_not_computed_whole_sign_works():
    m = resolve(date(1990, 12, 22), time(23, 40), "Europe/Moscow", place_id="geonames:524305")
    ch = western.chart(m, 68.96778, 33.09922)
    assert ch.placidus_not_computed == "not_applicable_latitude"
    assert all(pv.house_whole is not None for pv in ch.planets.values())
    assert all(pv.house_placidus is None for pv in ch.planets.values())


def test_no_time_no_houses_no_asc():
    m = resolve(date(1984, 2, 4), None, "Europe/Volgograd", place_id="geonames:472757")
    ch = western.chart(m, A_IN["lat"], A_IN["lon"])
    assert ch.asc is None and not ch.has_time
    assert all(pv.house_whole is None for pv in ch.planets.values())
    # знаки планет считаются и без времени
    assert ch.planets["Солнце"].sign == "Водолей"


def test_outer_signal_by_house_and_aspects_not_sign():
    # 04_product: высшая планета — сигнал по дому и аспектам к личным планетам, не по знаку
    ch = _chart_a()
    sig = western.outer_signal(ch, "Плутон")
    assert set(sig) == {"house", "aspects_to_personal"}
    assert sig["house"] == ch.planets["Плутон"].house_whole
    # знак Плутона в сигнал не входит
    assert "sign" not in sig


def test_signals_are_results_with_western_rules():
    rows = western.signals(_chart_a())
    assert rows and all(isinstance(r, Result) for r in rows)
    assert all(r.rule.id.startswith("w.") for r in rows)
    positions = [r for r in rows if r.rule.id == "w.position"]
    assert len(positions) == 12  # 10 планет + 2 узла
    assert {r.detail["body"] for r in positions} >= western.SEPTENER


def test_out_of_sign_flag():
    ch = _chart_a()
    # A: Марс(Скорпион)–Сатурн(Скорпион) соединение — в знаке
    ms = next(a for a in ch.aspects if {a.a, a.b} == {"Марс", "Сатурн"})
    assert not ms.out_of_sign
    # A: Луна(Рыбы, 11)–Марс(Скорпион, 7) трин: 4 знака — в знаке
    lm = next(a for a in ch.aspects if {a.a, a.b} == {"Луна", "Марс"})
    assert lm.type == "трин" and not lm.out_of_sign
