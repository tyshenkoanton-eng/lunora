"""Сквозные тесты доводки интеграции P3 (G17-S2f, F01–F11) через `calculate(BirthData)`.

Каждый фикс проверяется СКВОЗЬ рантайм-сборку карты (не только `resolve()`/`engine.chart()`):
точность → интервал допуска, ли-чунь на суточном интервале, v1-контракт (пол, ФИО, да-юнь,
числа имени), `visible_stem_counts`, запрет `computed(None)`, раздельные `near_boundary`/`range`,
LLM-пакет без ПДн. Онбординг с БД и провенанс — в test_onboard_p3.py.
"""

from datetime import date, time

import pytest

from lunora.calc.engine import calculate, provenance, resolve_moment
from lunora.calc.types import BirthData
from lunora.calc.types import BirthTimePrecision as P
from lunora.engines.numerology import FullName
from lunora.engines.result import Result, Rule
from lunora.llm.prompts import format_chart_data

FN = FullName("Петров", "Иван", "Сергеевич")


def _birth(**kw) -> BirthData:
    base = dict(
        birth_date=date(1990, 3, 15), birth_time=time(14, 30), precision=P.EXACT,
        lat=55.7558, lon=37.6173, timezone="Europe/Moscow", sex="m", full_name=FN,
    )
    base.update(kw)
    return BirthData(**base)


# ─────────────────────────── F01 точность → интервал ───────────────────────────


def test_f01_exact_time_gives_stable_signals():
    c = calculate(_birth(precision=P.EXACT))
    assert c.western.houses[0].stability == "stable"
    assert c.western.houses[0].values is None
    assert c.vedic.lagna_stability == "stable"


def test_f01_wide_tolerance_makes_ascendant_nonstable_with_variants():
    # ± 3 часа: асцендент пробегает несколько знаков — вывод не опирается на одно значение
    c = calculate(_birth(precision=P.APPROXIMATE))
    assert c.western.houses[0].stability in ("range", "undetermined")
    assert c.western.houses[0].values and len(c.western.houses[0].values) >= 2
    assert c.vedic.lagna_stability in ("range", "undetermined")


def test_f01_repeated_hour_reaches_chart_as_two_hypotheses():
    # осенний перевод 1988-09-25 02:30 МСК — час повторился (fold): две гипотезы смещения
    b = _birth(birth_date=date(1988, 9, 25), birth_time=time(2, 30), precision=P.EXACT)
    m = resolve_moment(b)
    assert len(m.hypotheses) == 2
    assert any(h.reason == "repeated_hour" for h in m.hypotheses if h.weight != "primary")
    calculate(b, m)  # обе гипотезы доходят до сборки карты без ошибки


def test_f01_tolerance_from_precision():
    assert _birth(precision=P.EXACT).tolerance_minutes == 0
    assert _birth(precision=P.APPROXIMATE_30).tolerance_minutes == 30
    assert _birth(precision=P.APPROXIMATE_60).tolerance_minutes == 60
    assert _birth(precision=P.APPROXIMATE).tolerance_minutes == 180
    assert _birth(precision=P.UNKNOWN, birth_time=None).tolerance_minutes is None


# ─────────────────────────── F03 ли-чунь на суточном интервале ───────────────────────────


def test_f03_lichun_unknown_hour_makes_year_pillar_range():
    # 04.02.1984 Волгоград: ли-чунь внутри суток → без часа столп года неопределён между
    # 癸亥 (1983) и 甲子 (1984), а не фиксируется по опорной точке (регрессия: было stable)
    b = _birth(birth_date=date(1984, 2, 4), birth_time=None, precision=P.UNKNOWN,
               lat=48.7, lon=44.5, timezone="Europe/Volgograd")
    c = calculate(b)
    yp = c.chinese.year_pillar
    assert yp.stability == "range"
    assert set(yp.values) == {"癸亥", "甲子"}
    # без времени столпы дня/часа и да-юнь — явный not_computed
    assert c.chinese.pillars_not_computed == "no_birth_time"
    assert c.chinese.dayun_not_computed == "no_birth_time"


# ───────────── F04 v1-контракт: пол, ФИО, да-юнь, числа имени ─────────────


def test_f04_dayun_present_with_sex():
    c = calculate(_birth(sex="m"))
    assert c.chinese.dayun is not None
    assert c.chinese.dayun.direction in ("順", "逆")
    assert len(c.chinese.dayun.decades) == 9
    assert c.chinese.dayun_not_computed is None


def test_f04_name_contour_reaches_chart():
    c = calculate(_birth(full_name=FullName("Куликов", "Роман", "Николаевич")))
    nn = c.numerology.name_numbers
    for key in ("expression", "heart", "persona", "maturity"):
        assert nn[key].value is not None and nn[key].not_computed is None


def test_f04_name_change_delta_when_current_differs():
    c = calculate(_birth(
        full_name=FullName("Соколова", "Марина", "Антоновна"),
        name_current=FullName("Иванова", "Марина", "Антоновна"),
    ))
    assert c.numerology.name_change is not None
    assert c.numerology.name_change["changed"] is True
    assert "EXPRESSION" in c.numerology.name_change["delta"]


def test_f04_no_name_change_when_current_absent():
    c = calculate(_birth())
    assert c.numerology.name_change is None


def test_f04_polar_latitude_houses_not_applicable():
    # Мурманск 68.97°N > 66.56° — дома Плацидуса не считаются (не подменяются Порфирием)
    c = calculate(_birth(lat=68.97, lon=33.08, timezone="Europe/Moscow"))
    assert c.western.houses == []
    assert c.western.houses_not_computed == "not_applicable_latitude"


# ─────────────────────────── F09 запрет computed(None) ───────────────────────────


def test_f09_computed_none_forbidden():
    with pytest.raises(ValueError, match="None"):
        Result.computed(Rule("num.x", "0.1.0"), None)


def test_f09_latin_name_is_explicit_not_computed():
    # вне API (пересчёты): латиница в ФИО — контур имени not_computed, не computed(None)
    c = calculate(_birth(full_name=FullName("Smith", "John", "Michael")))
    nn = c.numerology.name_numbers
    assert nn["expression"].not_computed == "name_not_supported"
    assert nn["maturity"].not_computed == "no_name"
    # контур даты при этом считается
    assert c.numerology.life_path != 0


# ─────────────────────────── F10 element_balance → visible_stem_counts ───────────────────────────


def test_f10_visible_stem_counts_replaces_element_balance():
    c = calculate(_birth())
    assert not hasattr(c.chinese, "element_balance")
    counts = c.chinese.visible_stem_counts
    assert sum(counts.values()) == 4  # четыре видимых ствола столпов
    assert set(counts) == {"Дерево", "Огонь", "Земля", "Металл", "Вода"}


# ─────────────────────────── F11 near_boundary ≠ range ───────────────────────────


def test_f11_near_boundary_at_exact_time_is_stable_not_range():
    # 1990-03-03 09:55 UTC: Чандра в 0,005° от границы накшатры — при точном времени значение
    # одно (stable), но помечено near_boundary; это НЕ «две величины на интервале» (range)
    b = _birth(birth_date=date(1990, 3, 3), birth_time=time(9, 55), precision=P.EXACT,
               lat=55.75, lon=37.6, timezone="UTC")
    nak = calculate(b).vedic.moon_nakshatra
    assert nak.stability == "stable"
    assert nak.near_boundary is True


def test_f11_boundary_within_tolerance_becomes_range():
    b = _birth(birth_date=date(1990, 3, 3), birth_time=time(9, 55), precision=P.APPROXIMATE_60,
               lat=55.75, lon=37.6, timezone="UTC")
    assert calculate(b).vedic.moon_nakshatra.stability == "range"


# ─────────────────────────── F06 / 152-ФЗ: LLM-пакет без ПДн ───────────────────────────


def _chart_dict(c) -> dict:
    from lunora.calc.serialize import chart_to_dict
    return {
        "western": chart_to_dict(c.western), "vedic": chart_to_dict(c.vedic),
        "chinese": chart_to_dict(c.chinese), "numerology": chart_to_dict(c.numerology),
    }


def test_f06_undetermined_signal_not_in_llm_package():
    c = calculate(_birth(precision=P.APPROXIMATE))
    pkg = format_chart_data(_chart_dict(c))
    # у undetermined-планеты знак в пакет не попадает (вывод не опирается на непосчитанное)
    for p in c.western.planets:
        if p.stability == "undetermined":
            assert f"{p.name}:" not in pkg


def test_f06_range_signal_shown_as_either_or():
    c = calculate(_birth(birth_date=date(1988, 9, 25), birth_time=time(2, 30)))
    # найдём планету с range и проверим формулировку «A или B»
    ranged = [p for p in c.vedic.planets if p.stability == "range"]
    pkg = format_chart_data(_chart_dict(c))
    for p in ranged:
        assert " или ".join(str(v) for v in p.values) in pkg


def test_pii_name_and_sex_never_in_llm_package():
    c = calculate(_birth(full_name=FullName("Достоевский", "Фёдор", "Михайлович"), name="Фёдор"))
    pkg = format_chart_data(_chart_dict(c))
    for forbidden in ("Достоевский", "Фёдор", "Михайлович", "1990", "03-15", "Москва", "55.75"):
        assert forbidden not in pkg


def test_pii_provenance_has_no_name_or_sex():
    b = _birth(full_name=FullName("Достоевский", "Фёдор", "Михайлович"))
    prov = provenance(b, resolve_moment(b))
    blob = repr(prov)
    for forbidden in ("Достоевский", "Фёдор", "Михайлович"):
        assert forbidden not in blob
