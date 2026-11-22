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
    Angle,
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
    """Продукт собирается из `western.signals()` (сигнальный слой), не ручной проекцией:
    знак/дом тел, углы ASC/MC, куспиды Плацидуса, аспекты; непосчитанное — в `not_computed`."""
    lat, lon = data.lat, data.lon
    ch = western_engine.chart(moment, lat, lon)
    rows = western_engine.signals(ch)
    arate = _asc_rate(lat, lon)
    nc: dict[str, str] = {}

    planets: list[PlanetPosition] = []
    for r in (x for x in rows if x.rule.id == "w.position"):
        d = r.detail
        name = d["body"]
        if name in ("Раху", "Кету"):
            sig = lambda dt, _n=name: western_engine.sign_name(_node_lon(dt, _n))  # noqa: E731
        else:
            sig = lambda dt, _n=name: western_engine.sign_name(  # noqa: E731
                eph.body(_instant(dt), _body_key(_n)).lon)
        tag, values = _stab(moment, sig)
        planets.append(PlanetPosition(
            name=name, longitude=d["longitude"], sign=r.value,
            degree_in_sign=round(d["longitude"] % 30.0, 4), house=d["house_placidus"],
            house_whole=d["house_whole"], stability=tag, values=values,
            retrograde=bool(d["retrograde"]),
        ))

    asc = mc = None
    for rid, is_asc in (("w.angle.asc", True), ("w.angle.mc", False)):
        rr = next(x for x in rows if x.rule.id == rid)
        if not rr.is_computed:
            nc[rid[2:]] = rr.not_computed
            continue
        sig = (lambda dt: western_engine.sign_name(eph.angles(_instant(dt), lat, lon).asc)) \
            if is_asc else \
            (lambda dt: western_engine.sign_name(eph.angles(_instant(dt), lat, lon).mc))
        tag, values = _stab(moment, sig, rate=arate)
        ang = Angle(sign=rr.value, longitude=rr.detail["longitude"], stability=tag, values=values)
        if is_asc:
            asc = ang
        else:
            mc = ang

    houses: list[HousePosition] = []
    houses_nc = None
    cusp_rows = [x for x in rows if x.rule.id == "w.house.cusp"]
    if cusp_rows and cusp_rows[0].is_computed:
        for r in cusp_rows:
            i = r.detail["number"] - 1
            sig = lambda dt, _i=i: _cusp_sign(dt, lat, lon, _i)  # noqa: E731
            tag, values = _stab(moment, sig, rate=arate)
            houses.append(HousePosition(number=r.detail["number"], longitude=r.detail["longitude"],
                                        sign=r.value, stability=tag, values=values))
    else:
        houses_nc = cusp_rows[0].not_computed if cusp_rows else "no_birth_time"
        nc["house.cusp"] = houses_nc

    aspects = [
        Aspect(planet1=a.a, planet2=a.b, aspect_type=a.type, angle=a.angle, orb=a.orb)
        for a in ch.aspects
    ]
    return WesternChart(
        planets=planets, houses=houses, aspects=aspects, asc=asc, mc=mc,
        houses_not_computed=houses_nc, not_computed=nc,
    )


def _cusp_sign(dt: datetime, lat: float, lon: float, i: int) -> str:
    ang = eph.angles(_instant(dt), lat, lon)
    pl = eph.placidus(ang.ramc, lat, ang.obliquity)
    c = pl[i] if not isinstance(pl, eph.NotComputed) else ang.asc
    return western_engine.sign_name(c)


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
    """Продукт из `vedic.signals()`: раши/накшатра/пада грах, бхава, D9/D10, лагна, активная
    даша; непосчитанное (нет времени) — явный `not_computed`."""
    lat, lon = data.lat, data.lon
    ch = vedic_engine.chart(moment, lat, lon)
    rows = vedic_engine.signals(ch)
    nc: dict[str, str] = {}

    rashi_rows = [x for x in rows if x.rule.id == "v.rashi"]
    planets: list[PlanetPosition] = []
    nakshatra = None
    lagna_sign = lagna_stab = None
    lagna_vals = None
    lagna_stab = "stable"
    for r in rashi_rows:
        d = r.detail
        body = d["body"]
        if body == "Лагна":
            lagna_sign = r.value
            sig = lambda dt: vedic_engine.RASHIS[  # noqa: E731
                vedic_engine.rashi_index(eph.sidereal(eph.angles(_instant(dt), lat, lon).asc,
                                                       _instant(dt)))]
            lagna_stab, lagna_vals = _stab(moment, sig, rate=_asc_rate(lat, lon))
            continue
        sig = lambda dt, _n=body: vedic_engine.RASHIS[  # noqa: E731
            vedic_engine.rashi_index(_vedic_lon(dt, _n))]
        tag, values = _stab(moment, sig)
        planets.append(PlanetPosition(
            name=body, longitude=d["longitude"], sign=r.value,
            degree_in_sign=round(d["longitude"] % 30.0, 4), house=d["bhava"],
            stability=tag, values=values, near_boundary=(r.stability == "range"),
            navamsa=d["navamsa"], dashamsa=d["dashamsa"], retrograde=bool(d["retrograde"]),
        ))
        if body == "Чандра":
            nsig = lambda dt: vedic_engine.NAKSHATRAS[  # noqa: E731
                vedic_engine.nakshatra_index(_vedic_lon(dt, "Чандра"))]
            ntag, _ = _stab(moment, nsig)
            lord = vedic_engine.nakshatra_lord(vedic_engine.nakshatra_index(d["longitude"]))
            nakshatra = Nakshatra(name=d["nakshatra"], pada=d["pada"], lord=lord,
                                  stability=ntag, near_boundary=(r.stability == "range"))

    active_maha = active_antara = None
    dasha_nc = None
    dasha_row = next((x for x in rows if x.rule.id == "v.dasha.vimshottari"), None)
    if dasha_row is not None and dasha_row.is_computed:
        active_maha = dasha_row.value
        active_antara = dasha_row.detail.get("antara")
    elif dasha_row is not None:
        dasha_nc = dasha_row.not_computed
        nc["dasha.vimshottari"] = dasha_nc

    dasha_periods = [
        DashaPeriod(planet=p.lord, start_year=round(_year_frac(p.start), 2),
                    end_year=round(_year_frac(p.end), 2),
                    years=round((p.end - p.start).days / 365.25, 1))
        for p in ch.mahadashas
    ]
    dasha_stab = nakshatra.stability if nakshatra is not None else "stable"

    return VedicChart(
        planets=planets, ayanamsha=round(ch.ayanamsha, 4), moon_nakshatra=nakshatra,
        dasha_periods=dasha_periods, dasha_stability=dasha_stab,
        active_maha=active_maha, active_antara=active_antara,
        lagna_sign=lagna_sign, lagna_stability=lagna_stab, lagna_values=lagna_vals,
        dasha_not_computed=dasha_nc, not_computed=nc,
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

    # явный манифест непосчитанного из сигнального слоя (день/час — no_birth_time; да-юнь —
    # no_sex/no_birth_time), чтобы ничего не терялось молча (анти-F04)
    nc = {r.rule.id[3:]: r.not_computed for r in bazi_engine.signals(ch) if not r.is_computed}

    return ChineseChart(
        year_pillar=year, month_pillar=month, day_pillar=day, hour_pillar=hour,
        day_master=day_master, day_master_element=day_master_element,
        day_master_yin_yang=day_master_yin_yang, year_animal=_ANIMALS[ch.year.branch],
        visible_stem_counts=counts, dayun=dayun,
        dayun_not_computed=ch.dayun_not_computed, pillars_not_computed=pillars_nc,
        not_computed=nc,
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

    # явный манифест непосчитанного (квадрат после 2000; числа имени без значения) — анти-F04
    nc: dict[str, str] = {}
    if square_nc is not None:
        nc["square"] = square_nc
    for store, cell in name_numbers.items():
        if cell.not_computed is not None:
            nc[f"name.{store}"] = cell.not_computed

    return NumerologyChart(
        life_path=life_path or 0, birthday_number=birthday or 0,
        pythagoras=square, square_not_computed=square_nc,
        name_numbers=name_numbers, name_change=name_change, not_computed=nc,
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
