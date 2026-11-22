"""Движок Ба-Цзы (ENGINE-SPEC-РАСЧЕТ §5.1–5.5, §5.10; D-106, G17-S2b).

Сборка четырёх столпов поверх эфемеридного слоя (`_ephem`, доказан в S1):
- год и месяц — по абсолютному моменту относительно 12 цзе (§5.2/§5.3), «пять тигров» (五虎遁);
- день и час — по истинному солнечному времени места (§2.8), смена дня в 23:00 (§5.4),
  «пять крыс» (五鼠遁, §5.5);
- да-юнь — направление по секте и полу, Δ до/от цзе, возраст входа «три дня — год» (§5.10).

Scope S2b — только столпы и да-юнь. Скрытые стволы (§5.6), баланс стихий (§5.7), десять богов
(§5.8), сила господина дня (§5.11), юншэнь (§5.12) — S4 (`known_gap`): в каноне порогов нет,
правила авторские. Движок НЕ импортирует оракулы (cnlunar, lunar-python) — ADR-001.
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from lunora.calc import _ephem as eph
from lunora.engines.result import Result, Rule
from lunora.timeplace.resolve import ResolvedMoment

RULES_VERSION = "0.1.0"  # 0.x — до подписи практика (D-106)

# §5.1 кодировка
STEMS = ("甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸")
BRANCHES = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")
ELEMENTS = ("Дерево", "Огонь", "Земля", "Металл", "Вода")

LICHUN_LON = 315.0  # 立春 ли-чунь — долгота Солнца, начало солнечного года (месяц 寅)
# 12 цзе — долготы Солнца ≡ 15° (mod 30°): 315,345,15,…,285 (§5.3)
JIE_STEP = 30.0


def _rule(name: str) -> Rule:
    return Rule(f"bz.{name}", RULES_VERSION)


def stem_element(stem: int) -> str:
    return ELEMENTS[stem // 2]


def stem_is_yang(stem: int) -> bool:
    return stem % 2 == 0


def sexagenary_index(stem: int, branch: int) -> int:
    """Номер столпа 0…59 в 60-ричном цикле (0 = 甲子) по стволу и ветви (КТО)."""
    return (stem * 6 - branch * 5) % 60  # обращение (n%10, n%12) → n


def pillar_name(stem: int, branch: int) -> str:
    return STEMS[stem % 10] + BRANCHES[branch % 12]


def jdn(y: int, m: int, d: int) -> int:
    """Юлианский день григорианской даты (Флигель — Ван Фландерн, §5.4)."""
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


@dataclass(frozen=True, slots=True)
class Pillar:
    stem: int
    branch: int
    name: str
    element: str  # стихия ствола
    yang: bool


@dataclass(frozen=True, slots=True)
class DaYun:
    forward: bool  # прямое (順) / обратное (逆)
    delta_days: float  # Δ по TT: до следующего (прямое) или от предыдущего (обратное) цзе
    years: int
    months: int
    days: int
    entry_date: date
    decades: tuple[str, ...]  # столпы десятилетий 1…9


@dataclass(frozen=True)
class BaziChart:
    year: Pillar
    month: Pillar
    day: Pillar | None
    hour: Pillar | None
    dayun: DaYun | None
    sun_longitude: float
    tst: datetime | None  # истинное солнечное время места (без пояса)
    solar_year: int  # календарный год ли-чунь, предшествующего рождению
    month_index: int  # 0 = 寅 … 11 = 丑
    day_shifted: bool  # сработало правило 23:00 (столп дня = дата_TST + 1)
    has_time: bool
    dayun_not_computed: str | None  # no_sex / no_birth_time
    stability: str = "stable"


def _primary(moment: ResolvedMoment):
    hyp = next((h for h in moment.hypotheses if h.weight == "primary"), moment.hypotheses[0])
    return hyp.utc_start.astimezone(UTC)


def _month_index(sun_lon: float) -> int:
    return int(((sun_lon - LICHUN_LON) % 360.0) // 30.0)


def _solar_year(birth_utc: datetime) -> int:
    """§5.3: календарный год ли-чунь, предшествующего рождению (или совпадающего)."""
    near = eph.instant(datetime(birth_utc.year, 2, 4, tzinfo=UTC))
    lichun = eph.sun_longitude_instant(LICHUN_LON, near, window_days=5.0)
    if lichun.utc_datetime() > birth_utc:
        return birth_utc.year - 1
    return birth_utc.year


def _year_month_pillars(sun_lon: float, solar_year: int, m: int) -> tuple[Pillar, Pillar]:
    y_stem = (solar_year - 4) % 10
    y_branch = (solar_year - 4) % 12
    m_branch = (2 + m) % 12
    m_stem = (2 * y_stem + 2 + m) % 10  # 五虎遁
    return (
        Pillar(y_stem, y_branch, pillar_name(y_stem, y_branch), stem_element(y_stem),
               stem_is_yang(y_stem)),
        Pillar(m_stem, m_branch, pillar_name(m_stem, m_branch), stem_element(m_stem),
               stem_is_yang(m_stem)),
    )


def _day_hour_pillars(tst: datetime) -> tuple[Pillar, Pillar, bool]:
    day_date = tst.date()
    shifted = tst.time() >= time(23, 0, 0)
    if shifted:  # поздний час Крысы — следующему дню (§5.4, без деления 早/晚子时)
        day_date = day_date + timedelta(days=1)
    j = jdn(day_date.year, day_date.month, day_date.day)
    d_stem = (j + 9) % 10
    d_branch = (j + 1) % 12
    h_branch = ((tst.hour + 1) // 2) % 12  # 五鼠遁: 23–00:59 → 子
    h_stem = (2 * d_stem + h_branch) % 10
    return (
        Pillar(d_stem, d_branch, pillar_name(d_stem, d_branch), stem_element(d_stem),
               stem_is_yang(d_stem)),
        Pillar(h_stem, h_branch, pillar_name(h_stem, h_branch), stem_element(h_stem),
               stem_is_yang(h_stem)),
        shifted,
    )


def _jie_instant(birth, sun_lon: float, forward: bool):
    """Момент ближайшего цзе: следующего (прямое) или предыдущего (обратное)."""
    k = (sun_lon - 15.0) / JIE_STEP
    target = 15.0 + JIE_STEP * (math.floor(k) + 1) if forward else 15.0 + JIE_STEP * math.ceil(
        k) - JIE_STEP
    return eph.sun_longitude_instant(target % 360.0, birth, window_days=20.0)


def _dayun(birth, sun_lon: float, year_stem: int, month: Pillar,
           local_date: date, sex: str | None) -> DaYun | None:
    if sex not in ("m", "f"):
        return None
    yang = stem_is_yang(year_stem)
    forward = (yang and sex == "m") or (not yang and sex == "f")
    jie = _jie_instant(birth, sun_lon, forward)
    delta = abs(float(jie.tt) - float(birth.tt))  # сутки по TT
    years = int(delta // 3)
    r = delta - 3 * years
    months = int(4 * r)
    days = int((4 * r - months) * 30)
    y = local_date.year + years
    mo = local_date.month + months
    while mo > 12:
        mo -= 12
        y += 1
    day = min(local_date.day, calendar.monthrange(y, mo)[1])
    entry = date(y, mo, day) + timedelta(days=days)
    base = sexagenary_index(month.stem, month.branch)
    step = 1 if forward else -1
    decades = tuple(pillar_name((base + step * k) % 60, (base + step * k) % 60)
                    for k in range(1, 10))
    return DaYun(forward, round(delta, 3), years, months, days, entry, decades)


def chart(moment: ResolvedMoment, lat: float, lon: float, sex: str | None = None) -> BaziChart:
    """Карта Ба-Цзы на момент рождения; `lon` — геодезическая долгота (для TST, §2.8)."""
    birth_utc = _primary(moment)
    t = eph.instant(birth_utc)
    sun_lon = eph.body(t, "sun").lon
    m = _month_index(sun_lon)
    solar_year = _solar_year(birth_utc)
    year_p, month_p = _year_month_pillars(sun_lon, solar_year, m)

    has_time = moment.local_time is not None
    day_p = hour_p = None
    tst = None
    shifted = False
    dayun = None
    dayun_nc = None
    if has_time:
        tst = eph.true_solar_time(t, lon).tst
        day_p, hour_p, shifted = _day_hour_pillars(tst)
        dayun = _dayun(t, sun_lon, year_p.stem, month_p, moment.local_date, sex)
        if dayun is None:
            dayun_nc = "no_sex"
    else:
        dayun_nc = "no_birth_time"

    return BaziChart(
        year=year_p, month=month_p, day=day_p, hour=hour_p, dayun=dayun,
        sun_longitude=sun_lon, tst=tst, solar_year=solar_year, month_index=m,
        day_shifted=shifted, has_time=has_time, dayun_not_computed=dayun_nc,
    )


def snapshot(chart: BaziChart) -> dict:
    """Плоский снимок карты по путям golden-кейсов."""
    out: dict = {
        "pillars.year": chart.year.name,
        "pillars.month": chart.month.name,
        "solar_year": chart.solar_year,
        "month_index": chart.month_index,
    }
    if chart.day is not None:
        out["pillars.day"] = chart.day.name
        out["pillars.hour"] = chart.hour.name
        out["day_shifted"] = chart.day_shifted
    if chart.dayun is not None:
        d = chart.dayun
        out["dayun.direction"] = "順" if d.forward else "逆"
        out["dayun.entry_date"] = d.entry_date.isoformat()
        out["dayun.entry_years"] = d.years
        out["dayun.decade_1"] = d.decades[0]
        out["dayun.decade_2"] = d.decades[1]
    elif chart.dayun_not_computed:
        out["dayun.not_computed"] = chart.dayun_not_computed
    return out


def signals(chart: BaziChart) -> list[Result]:
    """Минимальный контракт (решение Антона №5): каждый столп; да-юнь или not_computed."""
    rows: list[Result] = []
    rows.append(Result.computed(
        _rule("pillar.year"), chart.year.name, stability=chart.stability,
        stem=STEMS[chart.year.stem], branch=BRANCHES[chart.year.branch],
        element=chart.year.element, solar_year=chart.solar_year,
    ))
    rows.append(Result.computed(
        _rule("pillar.month"), chart.month.name, stability=chart.stability,
        stem=STEMS[chart.month.stem], branch=BRANCHES[chart.month.branch],
        element=chart.month.element, month_index=chart.month_index,
    ))
    for key, pv in (("pillar.day", chart.day), ("pillar.hour", chart.hour)):
        if pv is None:
            rows.append(Result.missing(_rule(key), "no_birth_time", stability=chart.stability))
        else:
            rows.append(Result.computed(
                _rule(key), pv.name, stability=chart.stability,
                stem=STEMS[pv.stem], branch=BRANCHES[pv.branch], element=pv.element,
            ))
    if chart.dayun is not None:
        d = chart.dayun
        rows.append(Result.computed(
            _rule("dayun"), "順" if d.forward else "逆", stability=chart.stability,
            delta_days=d.delta_days, entry_date=d.entry_date.isoformat(),
            age_years=d.years, age_months=d.months, age_days=d.days, decades=d.decades,
        ))
    else:
        rows.append(Result.missing(
            _rule("dayun"), chart.dayun_not_computed or "no_birth_time",
            stability=chart.stability,
        ))
    return rows
