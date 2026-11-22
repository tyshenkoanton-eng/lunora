"""Рантайм-сборка полной карты из доказанных движков `lunora.engines.*` (G17-S2e, G17-S2f).

Адаптер: `BirthData` → `ResolvedMoment` (timeplace.resolve с допуском и спорными поясами) →
четыре движка → контракт `calc.types` (форма хранимой карты, API). Каждая время-зависимая
дискретная величина несёт тег `stability` (§4.5), вычисленный на интервале(ах) `ResolvedMoment`
(F01/F03/F05/F11); пол и ФИО проведены в Ба-Цзы (да-юнь) и нумерологию (числа имени, F04).

Рантайм НЕ импортирует оракулы (ADR-001): движки работают поверх `_ephem` (Skyfield, доказан).
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from datetime import UTC, datetime, timedelta
from datetime import date as _date

from lunora.calc import _ephem as eph
from lunora.calc.stability import stability as _stability
from lunora.calc.types import (
    Aspect,
    BaziPillar,
    BirthData,
    ChineseChart,
    DashaPeriod,
    DaYun,
    FullChart,
    HousePosition,
    Nakshatra,
    NameNumber,
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

_ANIMALS = (
    "Крыса", "Бык", "Тигр", "Кролик", "Дракон", "Змея",
    "Лошадь", "Коза", "Обезьяна", "Петух", "Собака", "Свинья",
)
_YIN_YANG = {True: "Ян", False: "Инь"}
_ELEMENTS = ("Дерево", "Огонь", "Земля", "Металл", "Вода")

Signal = Callable[[datetime], Hashable]


def _moment(data: BirthData) -> ResolvedMoment:
    """Местные дата/время + зона → момент(ы) UTC: допуск по точности, спорные пояса (F01/F02)."""
    return resolve(
        data.birth_date,
        data.birth_time,
        data.timezone,
        tolerance_minutes=data.tolerance_minutes,
        place_id=data.place_id,
        region=data.region,
    )


def _stab(moment: ResolvedMoment, signal: Signal, rate=None) -> tuple[str, list | None]:
    """Тег §4.5 и варианты (только при range/undetermined) для дискретного сигнала."""
    tag, values = _stability(moment, signal, rate)
    return tag, (list(values) if tag != "stable" else None)


def _instant(dt: datetime):
    return eph.instant(dt if dt.tzinfo else dt.replace(tzinfo=UTC))


# ─────────────────────────────── западная ───────────────────────────────


def _western(moment: ResolvedMoment, data: BirthData) -> WesternChart:
    ch = western_engine.chart(moment, data.lat, data.lon)
    lat, lon = data.lat, data.lon

    planets: list[PlanetPosition] = []
    for pv in ch.planets.values():
        def sign_signal(dt: datetime, _k=pv.name) -> str:
            return western_engine.sign_name(eph.body(_instant(dt), _body_key(_k)).lon) \
                if _k not in ("Раху", "Кету") else western_engine.sign_name(_node_lon(dt, _k))
        tag, values = _stab(moment, sign_signal)
        planets.append(
            PlanetPosition(
                name=pv.name, longitude=pv.longitude, sign=pv.sign,
                degree_in_sign=pv.degree_in_sign, house=pv.house_placidus,
                stability=tag, values=values,
            )
        )

    houses: list[HousePosition] = []
    houses_nc = None
    if not ch.has_time:
        houses_nc = "no_birth_time"
    elif ch.placidus is None:
        houses_nc = ch.placidus_not_computed or "not_applicable_latitude"
    else:
        for i, cusp in enumerate(ch.placidus):
            def cusp_signal(dt: datetime, _i=i) -> str:
                ang = eph.angles(_instant(dt), lat, lon)
                pl = eph.placidus(ang.ramc, lat, ang.obliquity)
                c = pl[_i] if not isinstance(pl, eph.NotComputed) else ang.asc
                return western_engine.sign_name(c)
            tag, values = _stab(moment, cusp_signal, rate=_asc_rate(lat, lon))
            houses.append(
                HousePosition(number=i + 1, longitude=round(cusp, 4),
                              sign=western_engine.sign_name(cusp),
                              stability=tag, values=values)
            )

    aspects = [
        Aspect(planet1=a.a, planet2=a.b, aspect_type=a.type, angle=a.angle, orb=a.orb)
        for a in ch.aspects
    ]
    return WesternChart(
        planets=planets, houses=houses, aspects=aspects, houses_not_computed=houses_nc
    )


def _body_key(ru: str) -> str:
    for key, name in western_engine._BODY_NAMES:
        if name == ru:
            return key
    return "sun"


def _node_lon(dt: datetime, which: str) -> float:
    node = eph.true_node(_instant(dt))
    return node if which == "Раху" else eph.south_node(node)


def _asc_rate(lat: float, lon: float):
    def rate(dt: datetime) -> float:
        a0 = eph.angles(_instant(dt), lat, lon).asc
        a1 = eph.angles(_instant(dt + timedelta(seconds=5)), lat, lon).asc
        return abs(((a1 - a0 + 180.0) % 360.0) - 180.0) / 5.0  # °/сек
    return rate


# ─────────────────────────────── ведическая ───────────────────────────────


def _vedic(moment: ResolvedMoment, data: BirthData) -> VedicChart:
    lat, lon = data.lat, data.lon
    ch = vedic_engine.chart(moment, lat, lon)

    planets: list[PlanetPosition] = []
    for g in ch.grahas.values():
        def rashi_signal(dt: datetime, _n=g.name) -> str:
            return vedic_engine.RASHIS[vedic_engine.rashi_index(_vedic_lon(dt, _n))]
        tag, values = _stab(moment, rashi_signal)
        planets.append(
            PlanetPosition(
                name=g.name, longitude=g.longitude, sign=g.rashi,
                degree_in_sign=g.degree_in_rashi, house=g.bhava,
                stability=tag, values=values, near_boundary=(g.stability == "range"),
            )
        )

    moon = ch.grahas.get("Чандра")
    nakshatra = None
    if moon is not None:
        def nak_signal(dt: datetime) -> str:
            return vedic_engine.NAKSHATRAS[vedic_engine.nakshatra_index(_vedic_lon(dt, "Чандра"))]
        tag, values = _stab(moment, nak_signal)
        lord = vedic_engine.nakshatra_lord(vedic_engine.nakshatra_index(moon.longitude))
        nakshatra = Nakshatra(name=moon.nakshatra, pada=moon.pada, lord=lord,
                              stability=tag, near_boundary=(moon.stability == "range"))

    lagna_sign = ch.lagna_rashi
    lagna_stab, lagna_vals = "stable", None
    if ch.lagna is not None:
        def lagna_signal(dt: datetime) -> str:
            t = _instant(dt)
            sid = eph.sidereal(eph.angles(t, lat, lon).asc, t)
            return vedic_engine.RASHIS[vedic_engine.rashi_index(sid)]
        lagna_stab, lagna_vals = _stab(moment, lagna_signal, rate=_asc_rate(lat, lon))

    dasha_periods = [
        DashaPeriod(planet=p.lord, start_year=round(_year_frac(p.start), 2),
                    end_year=round(_year_frac(p.end), 2),
                    years=round((p.end - p.start).days / 365.25, 1))
        for p in ch.mahadashas
    ]
    dasha_nc = None if ch.has_time else "no_birth_time"
    # активная даша зависит от накшатры Чандры: её устойчивость — устойчивость активной МД
    dasha_stab = nakshatra.stability if nakshatra is not None else "stable"

    return VedicChart(
        planets=planets, ayanamsha=round(ch.ayanamsha, 4), moon_nakshatra=nakshatra,
        dasha_periods=dasha_periods, dasha_stability=dasha_stab,
        lagna_sign=lagna_sign, lagna_stability=lagna_stab, lagna_values=lagna_vals,
        dasha_not_computed=dasha_nc,
    )


def _vedic_lon(dt: datetime, graha: str) -> float:
    t = _instant(dt)
    if graha == "Раху":
        return eph.sidereal(eph.mean_node(t), t)
    if graha == "Кету":
        return (eph.sidereal(eph.mean_node(t), t) + 180.0) % 360.0
    key = next((k for k, ru in vedic_engine._GRAHA_NAMES if ru == graha), "sun")
    return eph.sidereal(eph.body_geometric(t, key).lon, t)


def _year_frac(d: _date) -> float:
    return d.year + (d - _date(d.year, 1, 1)).days / 365.25


# ─────────────────────────────── Ба-Цзы ───────────────────────────────


def _bazi_year_month(dt: datetime) -> tuple[str, str]:
    t = _instant(dt)
    sun_lon = eph.body(t, "sun").lon
    m = bazi_engine._month_index(sun_lon)
    solar_year = bazi_engine._solar_year(dt if dt.tzinfo else dt.replace(tzinfo=UTC))
    y, mo = bazi_engine._year_month_pillars(sun_lon, solar_year, m)
    return y.name, mo.name


def _bazi_day_hour(dt: datetime, lon: float) -> tuple[str, str]:
    t = _instant(dt)
    tst = eph.true_solar_time(t, lon).tst
    d, h, _ = bazi_engine._day_hour_pillars(tst)
    return d.name, h.name


def _pillar(p, moment: ResolvedMoment, signal: Signal) -> BaziPillar | None:
    if p is None:
        return None
    tag, values = _stab(moment, signal)
    return BaziPillar(
        stem=bazi_engine.STEMS[p.stem], branch=bazi_engine.BRANCHES[p.branch],
        element=p.element, yin_yang=_YIN_YANG[p.yang], animal=_ANIMALS[p.branch],
        stability=tag, values=values,
    )


def _chinese(moment: ResolvedMoment, data: BirthData) -> ChineseChart:
    lon = data.lon
    ch = bazi_engine.chart(moment, data.lat, lon, sex=data.sex)

    year = _pillar(ch.year, moment, lambda dt: _bazi_year_month(dt)[0])
    month = _pillar(ch.month, moment, lambda dt: _bazi_year_month(dt)[1])
    day = _pillar(ch.day, moment, lambda dt: _bazi_day_hour(dt, lon)[0])
    hour = _pillar(ch.hour, moment, lambda dt: _bazi_day_hour(dt, lon)[1])
    pillars_nc = None if ch.has_time else "no_birth_time"

    counts = {e: 0 for e in _ELEMENTS}
    for p in (ch.year, ch.month, ch.day, ch.hour):
        if p is not None:
            counts[p.element] += 1

    day_master = day_master_element = day_master_yin_yang = ""
    if ch.day is not None:
        day_master = bazi_engine.STEMS[ch.day.stem]
        day_master_element = ch.day.element
        day_master_yin_yang = _YIN_YANG[ch.day.yang]

    dayun = None
    if ch.dayun is not None:
        d = ch.dayun
        dayun = DaYun(direction="順" if d.forward else "逆", entry_date=d.entry_date.isoformat(),
                      entry_years=d.years, decades=list(d.decades))

    return ChineseChart(
        year_pillar=year, month_pillar=month, day_pillar=day, hour_pillar=hour,
        day_master=day_master, day_master_element=day_master_element,
        day_master_yin_yang=day_master_yin_yang, year_animal=_ANIMALS[ch.year.branch],
        visible_stem_counts=counts, dayun=dayun,
        dayun_not_computed=ch.dayun_not_computed, pillars_not_computed=pillars_nc,
    )


# ─────────────────────────────── нумерология ───────────────────────────────


def _num_cell(res) -> NameNumber:
    if res is None:
        return NameNumber(not_computed="no_name")
    if res.is_computed:
        return NameNumber(value=res.value)
    return NameNumber(not_computed=res.not_computed)


def _numerology(data: BirthData) -> NumerologyChart:
    try:
        res = num_engine.calculate(
            birth_date=data.birth_date, name_birth=data.full_name,
            name_current=data.name_current,
        )
        name_supported = True
    except num_engine.NumerologyInputError as exc:
        # F04/F09: латиница или смешанный алфавит ФИО — контур имени не считается (В-1)
        if exc.code not in ("latin_not_supported", "mixed_script", "unsupported_letter",
                            "invalid_character", "empty_name_part"):
            raise
        res = num_engine.calculate(birth_date=data.birth_date)
        name_supported = False

    life_path = res["LIFE_PATH"].value if "LIFE_PATH" in res else 0
    birthday = res["BIRTHDAY"].value if "BIRTHDAY" in res else 0

    square = None
    square_nc = None
    cells_res = res.values.get("CELLS")
    if cells_res is not None and cells_res.is_computed:
        cells_list = cells_res.value
        cells = {k: cells_list[k - 1] for k in range(1, 10)}
        work = res["WORK"].value if "WORK" in res else (0, 0, 0, 0)
        square = PythagorasSquare(cells=cells, working_numbers=tuple(work))
    elif cells_res is not None:
        square_nc = cells_res.not_computed

    name_numbers: dict[str, NameNumber] = {}
    for store, key in (("expression", "EXPRESSION"), ("heart", "HEART"),
                       ("persona", "PERSONA"), ("maturity", "MATURITY")):
        if not name_supported and key != "MATURITY":
            name_numbers[store] = NameNumber(not_computed="name_not_supported")
        else:
            name_numbers[store] = _num_cell(res.values.get(key))

    name_change = None
    nc_res = res.values.get("NAME_CHANGE")
    if nc_res is not None and nc_res.is_computed:
        name_change = {"delta": nc_res.value, "changed": nc_res.detail.get("changed", False)}

    return NumerologyChart(
        life_path=life_path or 0, birthday_number=birthday or 0,
        pythagoras=square, square_not_computed=square_nc,
        name_numbers=name_numbers, name_change=name_change,
    )


def resolve_moment(data: BirthData) -> ResolvedMoment:
    """Публичный доступ к разрешённому моменту (для провенанса CalculationRun, F07)."""
    return _moment(data)


def provenance(data: BirthData, moment: ResolvedMoment) -> dict:
    """Полное происхождение входа карты (F07): пояс, точность, место, UTC-гипотезы, версии."""
    return {
        "zone_id": data.timezone,
        "precision": data.precision.value,
        "tolerance_minutes": data.tolerance_minutes,
        "place_id": data.place_id,
        "region": data.region,
        "dispute_id": moment.provenance.get("dispute_id"),
        "tz_build": moment.provenance.get("tz_build"),
        "utc_hypotheses": [
            {
                "utc_start": h.utc_start.isoformat(),
                "utc_end": h.utc_end.isoformat(),
                "offset_minutes": int(h.utc_offset.total_seconds() // 60),
                "weight": h.weight,
                "reason": h.reason,
            }
            for h in moment.hypotheses
        ],
        "ephemeris": eph.versions(),
        "engine_versions": {
            "western": western_engine.RULES_VERSION,
            "vedic": vedic_engine.RULES_VERSION,
            "bazi": bazi_engine.RULES_VERSION,
            "numerology": num_engine.RULES_VERSION,
        },
    }


def calculate(data: BirthData, moment: ResolvedMoment | None = None) -> FullChart:
    """Полная карта по всем четырём системам из доказанных движков `lunora.engines.*`."""
    moment = moment or _moment(data)
    return FullChart(
        western=_western(moment, data),
        vedic=_vedic(moment, data),
        chinese=_chinese(moment, data),
        numerology=_numerology(data),
    )
