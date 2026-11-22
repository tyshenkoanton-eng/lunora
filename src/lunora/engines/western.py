"""Западный движок (ENGINE-SPEC §2.4–2.6, §3.1, §3.7, G17-S2c).

Сборка карты поверх эфемеридного слоя (`_ephem`, доказан в S1): знаки и градусы тел, дома по
цельным знакам и по Плацидусу (на полярных широтах — `not_applicable_latitude`), лунные узлы,
аспекты пяти птолемеевых видов по орбисам §3.7 (меньший ряд Лилли).

Scope S2c — только расчёт и регрессия ошибок прототипа (пропуск Солнца; высшие планеты —
сигнал по дому и аспектам, не по знаку). Эссенциальные и акцидентальные достоинства, Жребий,
профекции, фирдария, диспозиторы, альмутен, секта, сожжение — S4 (`known_gap`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC

from lunora.calc import _ephem as eph
from lunora.engines.result import Result, Rule
from lunora.timeplace.resolve import ResolvedMoment

RULES_VERSION = "0.1.0"  # 0.x — до подписи практика (ENGINE-SPEC §1.3)

SIGNS = (
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы",
)
# порядок септенера + высшие; имена ядра (_ephem) → русские
_BODY_NAMES: tuple[tuple[str, str], ...] = (
    ("sun", "Солнце"), ("moon", "Луна"), ("mercury", "Меркурий"), ("venus", "Венера"),
    ("mars", "Марс"), ("jupiter", "Юпитер"), ("saturn", "Сатурн"),
    ("uranus", "Уран"), ("neptune", "Нептун"), ("pluto", "Плутон"),
)
SEPTENER = frozenset({"Солнце", "Луна", "Меркурий", "Венера", "Марс", "Юпитер", "Сатурн"})
OUTER = ("Уран", "Нептун", "Плутон")

# §3.7 полные орбисы (меньший ряд Лилли)
ORB = {
    "Солнце": 15.0, "Луна": 12.0, "Меркурий": 7.0, "Венера": 7.0, "Марс": 7.0,
    "Юпитер": 9.0, "Сатурн": 9.0, "Уран": 5.0, "Нептун": 5.0, "Плутон": 5.0,
}
ASPECTS: tuple[tuple[str, float, str], ...] = (
    ("соединение", 0.0, "нейтральный"),
    ("секстиль", 60.0, "гармоничный"),
    ("квадратура", 90.0, "напряжённый"),
    ("трин", 120.0, "гармоничный"),
    ("оппозиция", 180.0, "напряжённый"),
)
PARTILE_ORB = 1.0  # аспект партильный, если точен до 1° (§3.7, draft)


def _rule(name: str) -> Rule:
    return Rule(f"w.{name}", RULES_VERSION)


def sign_index(lon: float) -> int:
    """Индекс знака 0…11; интервалы полуоткрыты `[k·30, (k+1)·30)` (§1.4)."""
    return math.floor((lon % 360.0) / 30.0)


def sign_name(lon: float) -> str:
    return SIGNS[sign_index(lon)]


def separation(a: float, b: float) -> float:
    return abs(((a - b + 180.0) % 360.0) - 180.0)


@dataclass(frozen=True, slots=True)
class PlanetView:
    name: str
    longitude: float
    speed: float
    sign: str
    degree_in_sign: float
    retrograde: bool
    house_whole: int | None = None
    house_placidus: int | None = None


@dataclass(frozen=True, slots=True)
class AspectView:
    a: str
    b: str
    type: str
    nature: str
    angle: float
    orb: float
    applying: bool
    partile: bool
    out_of_sign: bool


@dataclass(frozen=True)
class WesternChart:
    planets: dict[str, PlanetView]
    aspects: tuple[AspectView, ...]
    asc: float | None
    mc: float | None
    placidus: tuple[float, ...] | None
    placidus_not_computed: str | None
    has_time: bool
    stability: str = "stable"


def _primary_instant(moment: ResolvedMoment):
    hyp = next((h for h in moment.hypotheses if h.weight == "primary"), moment.hypotheses[0])
    return eph.instant(hyp.utc_start.astimezone(UTC))


def _find_house(lon: float, cusps: tuple[float, ...]) -> int:
    for i in range(12):
        a, b = cusps[i], cusps[(i + 1) % 12]
        inside = (a <= lon < b) if a < b else (lon >= a or lon < b)
        if inside:
            return i + 1
    return 1


def _aspects(planets: dict[str, PlanetView]) -> tuple[AspectView, ...]:
    # порядок внутри пары — по порядку планет (септенер, затем высшие), как в golden-эталоне
    order = [ru for _, ru in _BODY_NAMES]
    names = [n for n in order if n in planets]
    out: list[AspectView] = []
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            px, py = planets[x], planets[y]
            sep = separation(px.longitude, py.longitude)
            limit = (ORB[x] + ORB[y]) / 2.0
            for name, angle, nature in ASPECTS:
                orb = abs(sep - angle)
                if orb <= limit:
                    sep_next = separation(px.longitude + px.speed * 0.5,
                                          py.longitude + py.speed * 0.5)
                    applying = bool(abs(sep_next - angle) < orb)
                    # «через знак» (§3.7): фактическое расстояние в знаках ≠ углу / 30 (α/30
                    # знаков — «в знаке»: трин = 4 знака, секстиль = 2 и т.д.; соединение = 0)
                    sign_sep = (sign_index(px.longitude) - sign_index(py.longitude)) % 12
                    sign_sep = min(sign_sep, 12 - sign_sep)
                    out.append(AspectView(
                        a=x, b=y, type=name, nature=nature, angle=angle, orb=round(orb, 4),
                        applying=applying, partile=orb <= PARTILE_ORB,
                        out_of_sign=sign_sep != round(angle / 30.0),
                    ))
                    break
    return tuple(out)


def chart(moment: ResolvedMoment, lat: float, lon: float) -> WesternChart:
    """Западная карта на момент рождения; `lat`, `lon` — геодезические градусы (WGS-84)."""
    t = _primary_instant(moment)
    has_time = moment.local_time is not None

    asc = mc = None
    placidus = None
    placidus_nc = None
    if has_time:
        ang = eph.angles(t, lat, lon)
        asc, mc = ang.asc, ang.mc
        pl = eph.placidus(ang.ramc, lat, ang.obliquity)
        if isinstance(pl, eph.NotComputed):
            placidus_nc = pl.reason
        else:
            placidus = pl

    planets: dict[str, PlanetView] = {}
    for key, ru in _BODY_NAMES:
        bp = eph.body(t, key)
        hw = eph.whole_sign_house(bp.lon, asc) if asc is not None else None
        hp = _find_house(bp.lon, placidus) if placidus is not None else None
        planets[ru] = PlanetView(
            name=ru, longitude=bp.lon, speed=bp.speed, sign=sign_name(bp.lon),
            degree_in_sign=round(bp.lon % 30.0, 4), retrograde=bp.retrograde,
            house_whole=hw, house_placidus=hp,
        )
    # §2.6/Р-9: в западной — истинные узлы
    node = eph.true_node(t)
    for nm, nlon in (("Раху", node), ("Кету", eph.south_node(node))):
        hw = eph.whole_sign_house(nlon, asc) if asc is not None else None
        hp = _find_house(nlon, placidus) if placidus is not None else None
        planets[nm] = PlanetView(
            name=nm, longitude=nlon, speed=0.0, sign=sign_name(nlon),
            degree_in_sign=round(nlon % 30.0, 4), retrograde=False,
            house_whole=hw, house_placidus=hp,
        )

    planet_only = {k: v for k, v in planets.items() if k not in ("Раху", "Кету")}
    return WesternChart(
        planets=planets, aspects=_aspects(planet_only), asc=asc, mc=mc,
        placidus=placidus, placidus_not_computed=placidus_nc, has_time=has_time,
    )


def has_sun(chart: WesternChart) -> bool:
    """Инвариант §04_product: Солнце присутствует во всех наборах с септенером."""
    return "Солнце" in chart.planets and set(chart.planets) >= SEPTENER


def outer_signal(chart: WesternChart, planet: str) -> dict:
    """Высшая планета: сигнал по дому и аспектам к личным планетам, НЕ по знаку (§04_product)."""
    pv = chart.planets[planet]
    aspects = [a for a in chart.aspects if planet in (a.a, a.b)]
    personal = {"Солнце", "Луна", "Меркурий", "Венера", "Марс"}
    to_personal = sorted(
        (a.b if a.a == planet else a.a, a.type)
        for a in aspects
        if (a.b if a.a == planet else a.a) in personal
    )
    return {"house": pv.house_whole, "aspects_to_personal": to_personal}


def snapshot(chart: WesternChart) -> dict:
    """Плоский снимок карты по путям golden-кейсов."""
    out: dict = {}
    for name, pv in chart.planets.items():
        out[f"planets.{name}.sign"] = pv.sign
        out[f"planets.{name}.house_whole"] = pv.house_whole
        out[f"planets.{name}.house_placidus"] = pv.house_placidus
    out["aspects.count"] = len(chart.aspects)
    for a in chart.aspects:
        out[f"aspects.{a.a}|{a.b}.type"] = a.type
        out[f"aspects.{a.a}|{a.b}.orb"] = a.orb
    if chart.placidus_not_computed:
        out["placidus.not_computed"] = chart.placidus_not_computed
    out["houses_whole.count"] = sum(
        1 for pv in chart.planets.values() if pv.house_whole is not None
    ) and 12 if chart.has_time else 0
    return out


@dataclass(frozen=True)
class _Signals:
    chart: WesternChart
    rows: list[Result] = field(default_factory=list)


def signals(chart: WesternChart) -> list[Result]:
    """Контракт продукта (data-model §1, решение №5): знак и дом тел, углы ASC/MC, куспиды
    домов (цельнознаковые — в `house_whole` тел; Плацидус — отдельные сигналы), аспекты.

    Без времени ASC/MC/куспиды — `not_computed: no_birth_time`; на полярной широте куспиды
    Плацидуса — `not_applicable_latitude` (G17-S2f: не подменяются Порфирием)."""
    rows: list[Result] = []
    for name, pv in chart.planets.items():
        rows.append(Result.computed(
            _rule("position"), pv.sign, stability=chart.stability,
            body=name, longitude=pv.longitude, house_whole=pv.house_whole,
            house_placidus=pv.house_placidus, retrograde=pv.retrograde,
        ))
    for a in chart.aspects:
        rows.append(Result.computed(
            _rule("aspect"), a.type, stability=chart.stability,
            bodies=(a.a, a.b), orb=a.orb, applying=a.applying, partile=a.partile,
        ))
    # углы ASC/MC (§2.4) — опоры домов и всей время-зависимой части
    for key, value in (("asc", chart.asc), ("mc", chart.mc)):
        if value is None:
            rows.append(Result.missing(_rule(f"angle.{key}"), "no_birth_time"))
        else:
            rows.append(Result.computed(
                _rule(f"angle.{key}"), sign_name(value), stability=chart.stability,
                longitude=round(value, 4),
            ))
    # куспиды домов Плацидуса (§2.5)
    if chart.placidus is not None:
        for i, cusp in enumerate(chart.placidus):
            rows.append(Result.computed(
                _rule("house.cusp"), sign_name(cusp), stability=chart.stability,
                number=i + 1, longitude=round(cusp, 4),
            ))
    else:
        reason = "no_birth_time" if not chart.has_time else (
            chart.placidus_not_computed or "not_applicable_latitude")
        rows.append(Result.missing(_rule("house.cusp"), reason))
    return rows
