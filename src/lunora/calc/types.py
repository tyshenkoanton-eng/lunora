"""Контракт входа и хранимой карты (G17-S2f, v1-контракт P3).

`BirthData` несёт пол и ФИО при рождении — ПДн, которые входят в детерминированные движки и
в хранимую карту, но НЕ уходят в LLM-пакет и аналитику (152-ФЗ, ARCHITECTURE §5.6). Каждая
время-зависимая дискретная величина несёт тег `stability` (ARCHITECTURE §4.5); непосчитанные
величины — явный `not_computed` с причиной (ENGINE-SPEC §1.2), не молчаливый пропуск и не
`computed(None)` (F09).
"""

from dataclasses import dataclass, field
from datetime import date, time
from enum import StrEnum
from typing import Any

from lunora.engines.numerology import FullName


class BirthTimePrecision(StrEnum):
    EXACT = "exact"
    APPROXIMATE_30 = "approximate_30"
    APPROXIMATE_60 = "approximate_60"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


# допуск местного времени в минутах по точности (ARCHITECTURE §4.5)
PRECISION_TOLERANCE: dict[BirthTimePrecision, int | None] = {
    BirthTimePrecision.EXACT: 0,
    BirthTimePrecision.APPROXIMATE_30: 30,
    BirthTimePrecision.APPROXIMATE_60: 60,
    BirthTimePrecision.APPROXIMATE: 180,  # «± 3 часа» (§4.5)
    BirthTimePrecision.UNKNOWN: None,  # время не задано — сутки целиком
}


@dataclass(frozen=True)
class BirthData:
    """Вход расчёта. `sex` и `full_name` обязательны (решения Антона по F04, 2026-11-22).

    `name` — форма обращения (салютация) для показа; `full_name` — ФИО при рождении для
    контура имени; `name_current` — текущее ФИО для дельты «при рождении → сейчас» (§3.5).
    `place_id`/`region` ведут к реестру спорных поясов (tz_disputes, F02).
    """

    birth_date: date
    birth_time: time | None
    precision: BirthTimePrecision
    lat: float
    lon: float
    timezone: str
    sex: str  # 'm' | 'f'
    full_name: FullName
    name: str = ""
    name_current: FullName | None = None
    place_id: str | None = None
    region: str | None = None

    @property
    def tolerance_minutes(self) -> int | None:
        return PRECISION_TOLERANCE.get(self.precision, 0)


@dataclass
class PlanetPosition:
    name: str
    longitude: float
    sign: str
    degree_in_sign: float
    house: int | None = None
    stability: str = "stable"
    values: list[Any] | None = None  # при range — варианты знака на интервале
    near_boundary: bool = False  # F11: близко к границе раши/накшатры (ведич.), отдельно от range


@dataclass
class HousePosition:
    number: int
    longitude: float
    sign: str
    stability: str = "stable"
    values: list[Any] | None = None


@dataclass
class Aspect:
    planet1: str
    planet2: str
    aspect_type: str
    angle: float
    orb: float


@dataclass
class WesternChart:
    planets: list[PlanetPosition] = field(default_factory=list)
    houses: list[HousePosition] = field(default_factory=list)
    aspects: list[Aspect] = field(default_factory=list)
    houses_not_computed: str | None = None  # no_birth_time | not_applicable_latitude


@dataclass
class Nakshatra:
    name: str
    pada: int
    lord: str
    stability: str = "stable"
    near_boundary: bool = False


@dataclass
class DashaPeriod:
    planet: str
    start_year: float
    end_year: float
    years: float


@dataclass
class VedicChart:
    planets: list[PlanetPosition] = field(default_factory=list)
    ayanamsha: float = 0.0
    moon_nakshatra: Nakshatra | None = None
    dasha_periods: list[DashaPeriod] = field(default_factory=list)
    dasha_stability: str = "stable"
    lagna_sign: str | None = None
    lagna_stability: str = "stable"
    lagna_values: list[Any] | None = None
    dasha_not_computed: str | None = None  # no_birth_time


@dataclass
class BaziPillar:
    stem: str
    branch: str
    element: str
    yin_yang: str
    animal: str = ""
    stability: str = "stable"
    values: list[Any] | None = None


@dataclass
class DaYun:
    direction: str  # 順 | 逆
    entry_date: str  # ISO
    entry_years: int
    decades: list[str] = field(default_factory=list)


@dataclass
class ChineseChart:
    year_pillar: BaziPillar | None = None
    month_pillar: BaziPillar | None = None
    day_pillar: BaziPillar | None = None
    hour_pillar: BaziPillar | None = None
    day_master: str = ""
    day_master_element: str = ""
    day_master_yin_yang: str = ""
    year_animal: str = ""
    # F10: счёт стихий только видимых стволов (полный баланс §5.7 со скрытыми стволами — S4)
    visible_stem_counts: dict[str, int] = field(default_factory=dict)
    dayun: DaYun | None = None
    dayun_not_computed: str | None = None  # no_sex | no_birth_time
    pillars_not_computed: str | None = None  # no_birth_time (день/час)


@dataclass
class PythagorasSquare:
    cells: dict[int, int] = field(default_factory=dict)
    working_numbers: tuple[int, int, int, int] = (0, 0, 0, 0)


@dataclass
class NameNumber:
    """Одно число имени: значение либо явная причина not_computed (F09)."""

    value: int | None = None
    not_computed: str | None = None
    stability: str = "stable"


@dataclass
class NumerologyChart:
    life_path: int = 0
    birthday_number: int = 0
    pythagoras: PythagorasSquare | None = None
    square_not_computed: str | None = None  # rule_not_formalized (после 2000)
    # контур имени (F04): Выражение/Сердце/Облик/Зрелость
    name_numbers: dict[str, NameNumber] = field(default_factory=dict)
    # дельта «при рождении → сейчас» (§3.5): None, если name_current не задан
    name_change: dict[str, Any] | None = None


@dataclass
class FullChart:
    western: WesternChart | None = None
    vedic: VedicChart | None = None
    chinese: ChineseChart | None = None
    numerology: NumerologyChart | None = None
