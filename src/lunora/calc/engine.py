"""Рантайм-сборка полной карты из доказанных движков `lunora.engines.*` (G17-S2e).

Адаптер: `BirthData` → `ResolvedMoment` (timeplace.resolve) → четыре движка (западный,
ведический, Ба-Цзы, нумерология) → контракт `calc.types` (форма хранимого чарта, API).

Рантайм НЕ импортирует оракулы (pyswisseph / cnlunar / timezonefinder) — ADR-001: движки
работают поверх эфемеридного слоя Skyfield (`_ephem`, доказан в G17-S1). Прежние прототипные
модули `calc/{western,vedic,chinese,numerology}.py` (на swisseph/cnlunar) сняты в S2e.
"""

from __future__ import annotations

from datetime import date as _date

from lunora.calc.types import (
    Aspect,
    BaziPillar,
    BirthData,
    ChineseChart,
    DashaPeriod,
    FullChart,
    HousePosition,
    Nakshatra,
    NumerologyChart,
    PlanetPosition,
    PythagorasSquare,
    VedicChart,
    WesternChart,
)
from lunora.engines import bazi as bazi_engine
from lunora.engines import numerology as num_engine
from lunora.engines import vedic as vedic_engine
from lunora.engines import western as western_engine
from lunora.timeplace.resolve import ResolvedMoment, resolve

# ветвь земная (0=子 … 11=亥) → животное года
_ANIMALS = (
    "Крыса", "Бык", "Тигр", "Кролик", "Дракон", "Змея",
    "Лошадь", "Коза", "Обезьяна", "Петух", "Собака", "Свинья",
)
_YIN_YANG = {True: "Ян", False: "Инь"}
_ELEMENTS = ("Дерево", "Огонь", "Земля", "Металл", "Вода")


def _moment(data: BirthData) -> ResolvedMoment:
    """Местные дата/время + зона → момент UTC (гипотезы смещения). Без времени — без домов."""
    return resolve(data.birth_date, data.birth_time, data.timezone)


def _year_frac(d: _date) -> float:
    """Год с дробной частью (для контракта дат даши, который хранит годы как float)."""
    return d.year + (d - _date(d.year, 1, 1)).days / 365.25


def _western(moment: ResolvedMoment, data: BirthData) -> WesternChart:
    ch = western_engine.chart(moment, data.lat, data.lon)
    planets = [
        PlanetPosition(
            name=pv.name,
            longitude=pv.longitude,
            sign=pv.sign,
            degree_in_sign=pv.degree_in_sign,
            house=pv.house_placidus,
        )
        for pv in ch.planets.values()
    ]
    houses: list[HousePosition] = []
    if ch.placidus is not None:
        for i, cusp in enumerate(ch.placidus):
            houses.append(
                HousePosition(
                    number=i + 1,
                    longitude=round(cusp, 4),
                    sign=western_engine.sign_name(cusp),
                )
            )
    aspects = [
        Aspect(
            planet1=a.a,
            planet2=a.b,
            aspect_type=a.type,
            angle=a.angle,
            orb=a.orb,
        )
        for a in ch.aspects
    ]
    return WesternChart(planets=planets, houses=houses, aspects=aspects)


def _vedic(moment: ResolvedMoment, data: BirthData) -> VedicChart:
    ch = vedic_engine.chart(moment, data.lat, data.lon)
    planets = [
        PlanetPosition(
            name=g.name,
            longitude=g.longitude,
            sign=g.rashi,
            degree_in_sign=g.degree_in_rashi,
            house=g.bhava,
        )
        for g in ch.grahas.values()
    ]
    moon = ch.grahas.get("Чандра")
    nakshatra = None
    if moon is not None:
        lord = vedic_engine.nakshatra_lord(vedic_engine.nakshatra_index(moon.longitude))
        nakshatra = Nakshatra(name=moon.nakshatra, pada=moon.pada, lord=lord)
    dasha_periods = [
        DashaPeriod(
            planet=p.lord,
            start_year=round(_year_frac(p.start), 2),
            end_year=round(_year_frac(p.end), 2),
            years=round((p.end - p.start).days / 365.25, 1),
        )
        for p in ch.mahadashas
    ]
    return VedicChart(
        planets=planets,
        ayanamsha=round(ch.ayanamsha, 4),
        moon_nakshatra=nakshatra,
        dasha_periods=dasha_periods,
    )


def _pillar(p) -> BaziPillar | None:
    if p is None:
        return None
    return BaziPillar(
        stem=bazi_engine.STEMS[p.stem],
        branch=bazi_engine.BRANCHES[p.branch],
        element=p.element,
        yin_yang=_YIN_YANG[p.yang],
        animal=_ANIMALS[p.branch],
    )


def _chinese(moment: ResolvedMoment, data: BirthData) -> ChineseChart:
    ch = bazi_engine.chart(moment, data.lat, data.lon)  # пол неизвестен → да-юнь не считается
    year = _pillar(ch.year)
    month = _pillar(ch.month)
    day = _pillar(ch.day)
    hour = _pillar(ch.hour)

    # баланс видимых стволов (§5.7 с учётом скрытых — S4; здесь только явные стволы столпов)
    balance = {e: 0 for e in _ELEMENTS}
    for p in (ch.year, ch.month, ch.day, ch.hour):
        if p is not None:
            balance[p.element] += 1

    day_master = day_master_element = day_master_yin_yang = ""
    if ch.day is not None:
        day_master = bazi_engine.STEMS[ch.day.stem]
        day_master_element = ch.day.element
        day_master_yin_yang = _YIN_YANG[ch.day.yang]

    return ChineseChart(
        year_pillar=year,
        month_pillar=month,
        day_pillar=day,
        hour_pillar=hour,
        day_master=day_master,
        day_master_element=day_master_element,
        day_master_yin_yang=day_master_yin_yang,
        year_animal=_ANIMALS[ch.year.branch],
        element_balance=balance,
    )


def _numerology(data: BirthData) -> NumerologyChart:
    res = num_engine.calculate(birth_date=data.birth_date)
    life_path = res["LIFE_PATH"].value if "LIFE_PATH" in res else 0
    birthday = res["BIRTHDAY"].value if "BIRTHDAY" in res else 0

    square = None
    cells_res = res.values.get("CELLS")
    if cells_res is not None and cells_res.is_computed:
        cells_list = cells_res.value
        cells = {k: cells_list[k - 1] for k in range(1, 10)}
        work = res["WORK"].value if "WORK" in res else (0, 0, 0, 0)
        square = PythagorasSquare(cells=cells, working_numbers=tuple(work))

    return NumerologyChart(
        life_path=life_path or 0,
        birthday_number=birthday or 0,
        pythagoras=square,
    )


def calculate(data: BirthData) -> FullChart:
    """Полная карта по всем четырём системам из доказанных движков `lunora.engines.*`."""
    moment = _moment(data)
    return FullChart(
        western=_western(moment, data),
        vedic=_vedic(moment, data),
        chinese=_chinese(moment, data),
        numerology=_numerology(data),
    )
