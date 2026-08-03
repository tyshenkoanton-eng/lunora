from dataclasses import dataclass, field
from datetime import date, time
from enum import StrEnum


class BirthTimePrecision(StrEnum):
    EXACT = "exact"
    APPROXIMATE_30 = "approximate_30"
    APPROXIMATE_60 = "approximate_60"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BirthData:
    birth_date: date
    birth_time: time | None
    precision: BirthTimePrecision
    lat: float
    lon: float
    timezone: str
    name: str = ""


@dataclass
class PlanetPosition:
    name: str
    longitude: float
    sign: str
    degree_in_sign: float
    house: int | None = None


@dataclass
class HousePosition:
    number: int
    longitude: float
    sign: str


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


@dataclass
class Nakshatra:
    name: str
    pada: int
    lord: str


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


@dataclass
class BaziPillar:
    stem: str
    branch: str
    element: str
    yin_yang: str
    animal: str = ""


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
    element_balance: dict[str, int] = field(default_factory=dict)


@dataclass
class PythagorasSquare:
    cells: dict[int, int] = field(default_factory=dict)
    working_numbers: tuple[int, int, int, int] = (0, 0, 0, 0)


@dataclass
class NumerologyChart:
    life_path: int = 0
    birthday_number: int = 0
    pythagoras: PythagorasSquare | None = None


@dataclass
class FullChart:
    western: WesternChart | None = None
    vedic: VedicChart | None = None
    chinese: ChineseChart | None = None
    numerology: NumerologyChart | None = None
