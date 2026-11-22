"""Ведический движок (Джйотиш) — ENGINE-SPEC §4.1–4.4, §2.6–2.7, G17-S2d.

Сборка сидерической карты поверх эфемеридного слоя (`_ephem`, доказан в S1). Кадр совпадает
с эталонным сервисом Jagannatha Hora (JH, П-2): **истинные геометрические геоцентрические
положения** (без аберрации), **средние узлы** Раху/Кету, сидерические долготы по айанамше
Лахири (§2.7). Айанамша JH — True Chitrapaksha, у нас Лахири №1: систематическая разница
≈ 56″ (постоянная по всем телам) относится к «настройкам эталона» (§2.7), НЕ подгоняется.

Scope S2d — раши, лагна, бхавы (§4.1); накшатры и пады (§4.2); Вимшоттари-даша (§4.3, длина
года Y=365,25 сут — рабочее значение, даты `can_vote: false`, продукт до года); варги D1/D9/D10
(§4.4). Достоинства, Жребий/каракамша, сад-сати, шад-бала, остальные варги — S4 (`out_of_v1`).
AGPL-оракулы (PyJHora) НИКОГДА в рантайм — только внешний эталон (ADR-001).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from lunora.calc import _ephem as eph
from lunora.engines.result import Result, Rule
from lunora.timeplace.resolve import ResolvedMoment

RULES_VERSION = "1.0.0"  # раши/накшатра устойчивы; даша 0.x — длина года развилка (§4.3)
DASHA_VERSION = "0.1.0"

RASHIS = (
    "Меша", "Вришабха", "Митхуна", "Карка", "Симха", "Канья",
    "Тула", "Вришчика", "Дхану", "Макара", "Кумбха", "Мина",
)
# семь управителей раши (§3.1); Раху/Кету знаками не управляют
RASHI_LORDS = (
    "Мангала", "Шукра", "Будха", "Чандра", "Сурья", "Будха",
    "Шукра", "Мангала", "Гуру", "Шани", "Шани", "Гуру",
)
# ядро (_ephem) → санскрит; затем узлы
_GRAHA_NAMES: tuple[tuple[str, str], ...] = (
    ("sun", "Сурья"), ("moon", "Чандра"), ("mars", "Мангала"), ("mercury", "Будха"),
    ("jupiter", "Гуру"), ("venus", "Шукра"), ("saturn", "Шани"),
)
NAKSHATRAS = (
    "Ашвини", "Бхарани", "Криттика", "Рохини", "Мригашира", "Ардра", "Пунарвасу",
    "Пушья", "Ашлеша", "Магха", "Пурва-Пхалгуни", "Уттара-Пхалгуни", "Хаста", "Читра",
    "Свати", "Вишакха", "Анурадха", "Джьештха", "Мула", "Пурва-Ашадха", "Уттара-Ашадха",
    "Шравана", "Дхаништха", "Шатабхиша", "Пурва-Бхадрапада", "Уттара-Бхадрапада", "Ревати",
)
# Вимшоттари: порядок управителей и длительности (§4.3); накшатра N → лорд = ORDER[N mod 9]
VIMSHOTTARI: tuple[tuple[str, int], ...] = (
    ("Кету", 7), ("Шукра", 20), ("Сурья", 6), ("Чандра", 10), ("Мангала", 7),
    ("Раху", 18), ("Гуру", 16), ("Шани", 19), ("Будха", 17),
)
DASHA_TOTAL = 120  # сумма лет
DASHA_YEAR_DAYS = 365.25  # Y, рабочее (§4.3); JH — true sidereal solar year, разница < года

NAK_ARC = 360.0 / 27.0  # 13°20′
PADA_ARC = NAK_ARC / 4.0  # 3°20′
BOUNDARY_RANGE_DEG = 0.05  # у границы раши/накшатры (< 3′) — stability `range` (чувств. §4.3)


def _rule(name: str, version: str = RULES_VERSION) -> Rule:
    return Rule(f"v.{name}", version)


def rashi_index(lon: float) -> int:
    return int((lon % 360.0) // 30.0)


def nakshatra_index(lon: float) -> int:
    return int((lon % 360.0) // NAK_ARC)


def pada(lon: float) -> int:
    return int((lon % NAK_ARC) // PADA_ARC) + 1


def nakshatra_lord(n: int) -> str:
    return VIMSHOTTARI[n % 9][0]


def navamsa_sign(lon: float) -> int:
    """D9 (§4.4): знак = floor(λ_sid / 3°20′) mod 12."""
    return int((lon % 360.0) // PADA_ARC) % 12


def dashamsa_sign(lon: float) -> int:
    """D10 (§4.4): нечётный знак (индекс чётный) — с себя; чётный — с 9-го."""
    s = rashi_index(lon)
    k = int((lon % 30.0) // 3.0)
    return (s + k) % 12 if s % 2 == 0 else (s + 8 + k) % 12


def _boundary_distance(lon: float) -> float:
    """Угловое расстояние (°) до ближайшей границы раши ИЛИ накшатры."""
    to_rashi = min(lon % 30.0, 30.0 - (lon % 30.0))
    to_nak = min(lon % NAK_ARC, NAK_ARC - (lon % NAK_ARC))
    return min(to_rashi, to_nak)


@dataclass(frozen=True, slots=True)
class GrahaView:
    name: str
    longitude: float  # сидерическая (Лахири, §2.7)
    retrograde: bool
    rashi: str
    degree_in_rashi: float
    nakshatra: str
    pada: int
    bhava: int | None
    navamsa: str
    dashamsa: str
    stability: str  # stable | range (у границы)


@dataclass(frozen=True, slots=True)
class DashaPeriod:
    lord: str
    start: date
    end: date


@dataclass(frozen=True)
class VedicChart:
    grahas: dict[str, GrahaView]
    lagna: float | None  # сидерическая долгота ASC
    lagna_rashi: str | None
    mahadashas: tuple[DashaPeriod, ...]
    dasha_balance_years: float | None  # остаток первой МД при рождении
    active_maha: str | None
    active_antara: str | None
    active_on: date | None
    has_time: bool
    ayanamsha: float
    stability: str = "stable"


def _primary(moment: ResolvedMoment) -> datetime:
    hyp = next((h for h in moment.hypotheses if h.weight == "primary"), moment.hypotheses[0])
    return hyp.utc_start.astimezone(UTC)


def _sidereal_geometric(t, name: str) -> tuple[float, bool]:
    bp = eph.body_geometric(t, name)
    return eph.sidereal(bp.lon, t), bp.retrograde


def _bhava(lon: float, lagna: float | None) -> int | None:
    if lagna is None:
        return None
    return (rashi_index(lon) - rashi_index(lagna)) % 12 + 1


def _graha_view(name: str, lon: float, retro: bool, lagna: float | None) -> GrahaView:
    ri = rashi_index(lon)
    ni = nakshatra_index(lon)
    stab = "range" if _boundary_distance(lon) < BOUNDARY_RANGE_DEG else "stable"
    return GrahaView(
        name=name, longitude=lon, retrograde=retro, rashi=RASHIS[ri],
        degree_in_rashi=round(lon % 30.0, 4), nakshatra=NAKSHATRAS[ni], pada=pada(lon),
        bhava=_bhava(lon, lagna), navamsa=RASHIS[navamsa_sign(lon)],
        dashamsa=RASHIS[dashamsa_sign(lon)], stability=stab,
    )


def _vimshottari(moon_lon: float, birth: date, now: date) -> tuple[
    tuple[DashaPeriod, ...], float, str | None, str | None
]:
    """Махадаши (9, от накшатры Чандры), остаток первой МД, активные МД/АД на `now` (§4.3)."""
    n = nakshatra_index(moon_lon)
    f = (moon_lon % NAK_ARC) / NAK_ARC  # пройденная доля накшатры
    start_idx = n % 9
    lord0, yrs0 = VIMSHOTTARI[start_idx]
    balance = yrs0 * (1.0 - f)  # остаток первой МД, лет
    first_start = birth - timedelta(days=f * yrs0 * DASHA_YEAR_DAYS)

    periods: list[DashaPeriod] = []
    cur = first_start
    for j in range(9):
        lord, yrs = VIMSHOTTARI[(start_idx + j) % 9]
        end = cur + timedelta(days=yrs * DASHA_YEAR_DAYS)
        periods.append(DashaPeriod(lord, cur, end))
        cur = end

    active_maha = active_antara = None
    for p in periods:
        if p.start <= now < p.end:
            active_maha = p.lord
            active_antara = _antardasha(p, now)
            break
    return tuple(periods), balance, active_maha, active_antara


def _antardasha(maha: DashaPeriod, now: date) -> str | None:
    """Активная антардаша внутри МД на `now`: порядок с управителя МД по кругу (§4.3)."""
    maha_idx = next(i for i, (lord, _) in enumerate(VIMSHOTTARI) if lord == maha.lord)
    maha_years = VIMSHOTTARI[maha_idx][1]
    cur = maha.start
    for j in range(9):
        lord, yrs = VIMSHOTTARI[(maha_idx + j) % 9]
        dur = maha_years * yrs / DASHA_TOTAL  # лет
        end = cur + timedelta(days=dur * DASHA_YEAR_DAYS)
        if cur <= now < end:
            return lord
        cur = end
    return None


def chart(moment: ResolvedMoment, lat: float, lon: float,
          now: date | None = None) -> VedicChart:
    """Ведическая карта на момент рождения; `now` — дата для активной даши (умолч. сегодня)."""
    birth_utc = _primary(moment)
    t = eph.instant(birth_utc)
    ayan = eph.ayanamsha_lahiri_mean(t)
    has_time = moment.local_time is not None

    lagna = lagna_rashi = None
    if has_time:
        lagna = eph.sidereal(eph.angles(t, lat, lon).asc, t)
        lagna_rashi = RASHIS[rashi_index(lagna)]

    grahas: dict[str, GrahaView] = {}
    for key, ru in _GRAHA_NAMES:
        slon, retro = _sidereal_geometric(t, key)
        grahas[ru] = _graha_view(ru, slon, retro, lagna)
    # §2.6/Р-9: в ведической — средние узлы
    rahu = eph.sidereal(eph.mean_node(t), t)
    for nm, nlon in (("Раху", rahu), ("Кету", (rahu + 180.0) % 360.0)):
        grahas[nm] = _graha_view(nm, nlon, False, lagna)

    mahadashas: tuple[DashaPeriod, ...] = ()
    balance = active_maha = active_antara = None
    active_on = None
    if has_time:
        active_on = now or datetime.now(UTC).date()
        mahadashas, balance, active_maha, active_antara = _vimshottari(
            grahas["Чандра"].longitude, moment.local_date, active_on
        )

    return VedicChart(
        grahas=grahas, lagna=lagna, lagna_rashi=lagna_rashi, mahadashas=mahadashas,
        dasha_balance_years=balance, active_maha=active_maha, active_antara=active_antara,
        active_on=active_on, has_time=has_time, ayanamsha=ayan,
    )


def snapshot(chart: VedicChart) -> dict:
    """Плоский снимок карты по путям golden-кейсов."""
    out: dict = {"ayanamsha": round(chart.ayanamsha, 6)}
    if chart.lagna is not None:
        out["lagna.rashi"] = chart.lagna_rashi
        out["lagna.nakshatra"] = NAKSHATRAS[nakshatra_index(chart.lagna)]
        out["lagna.pada"] = pada(chart.lagna)
    for name, g in chart.grahas.items():
        out[f"grahas.{name}.rashi"] = g.rashi
        out[f"grahas.{name}.nakshatra"] = g.nakshatra
        out[f"grahas.{name}.pada"] = g.pada
        out[f"grahas.{name}.bhava"] = g.bhava
        out[f"grahas.{name}.navamsa"] = g.navamsa
        out[f"grahas.{name}.dashamsa"] = g.dashamsa
        out[f"grahas.{name}.retrograde"] = g.retrograde
        out[f"grahas.{name}.stability"] = g.stability
    if chart.mahadashas:
        out["dasha.sequence"] = [p.lord for p in chart.mahadashas]
        out["dasha.active_maha"] = chart.active_maha
        out["dasha.active_antara"] = chart.active_antara
        for p in chart.mahadashas:
            out[f"dasha.start_year.{p.lord}"] = p.start.year
    return out


def signals(chart: VedicChart) -> list[Result]:
    """Минимальный контракт (решение №5): раши/накшатра грах, лагна, активная даша."""
    rows: list[Result] = []
    if chart.lagna is not None:
        rows.append(Result.computed(
            _rule("rashi"), chart.lagna_rashi, stability=chart.stability, body="Лагна",
            longitude=round(chart.lagna, 4), nakshatra=NAKSHATRAS[nakshatra_index(chart.lagna)],
            pada=pada(chart.lagna),
        ))
    for name, g in chart.grahas.items():
        rows.append(Result.computed(
            _rule("rashi"), g.rashi, stability=g.stability, body=name,
            longitude=round(g.longitude, 4), nakshatra=g.nakshatra, pada=g.pada,
            bhava=g.bhava, navamsa=g.navamsa, dashamsa=g.dashamsa, retrograde=g.retrograde,
        ))
    if chart.active_maha is not None:
        rows.append(Result.computed(
            _rule("dasha.vimshottari", DASHA_VERSION), chart.active_maha,
            stability="range", antara=chart.active_antara, on=chart.active_on.isoformat(),
            sequence=[p.lord for p in chart.mahadashas],
            note="can_vote:false, даты до года (§4.3)",
        ))
    elif not chart.has_time:
        rows.append(Result.missing(_rule("dasha.vimshottari", DASHA_VERSION), "no_birth_time"))
    return rows
