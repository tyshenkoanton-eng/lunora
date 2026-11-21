"""Эфемеридный слой Луноры — единственная точка доступа к астрономии (ADR-001, ENGINE-SPEC §2).

Рантайм: Skyfield (закреплённая версия, builtin-шкала времени) + JPL DE440s из
data/vendor/jpl (манифест SHA-256, качает make setup). Ни один движок не импортирует
Skyfield напрямую. Сети здесь нет: нет файла или не та сумма — EphemerisDataError.

Состав (§2.2–§2.7): момент (UT1 до 1972 / UTC с 1972), видимые геоцентрические долготы и
скорости 10 тел в эклиптике истинного равноденствия даты, RAMC/ε/ASC/MC с полярным
правилом, цельные знаки и Плацидус, средний и истинный узел, средняя айанамша Лахири.
Swiss Ephemeris — только тестовый оракул (tests/diff), сюда не импортируется.
"""

from __future__ import annotations

import functools
import hashlib
import math
import os
import pathlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import skyfield
from skyfield.api import load, load_file
from skyfield.framelib import ecliptic_frame
from skyfield.timelib import Time, Timescale

# --- данные -----------------------------------------------------------------------------

EPHEMERIS = "DE440s"
EPHEMERIS_FILE = "de440s.bsp"
EPHEMERIS_SHA256 = "c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2"
_REPO_DIR = pathlib.Path(__file__).resolve().parents[3] / "data" / "vendor" / "jpl"

# NAIF ID: Солнце, Луна, Меркурий, Венера — центры; Марс…Плутон — барицентры систем (§2.3)
_TARGETS = {
    "sun": 10,
    "moon": 301,
    "mercury": 199,
    "venus": 299,
    "mars": 4,
    "jupiter": 5,
    "saturn": 6,
    "uranus": 7,
    "neptune": 8,
    "pluto": 9,
}
BODIES: tuple[str, ...] = tuple(_TARGETS)

SPEED_STEP_DAYS = 0.01  # центральная разность на t ± 0,01 сут TT (§2.3)
PLACIDUS_MAX_LAT = 66.56  # D-105: константа, не 90° − ε(t) (§2.5)
UTC_FROM = datetime(1972, 1, 1, tzinfo=UTC)  # §2.2


class EphemerisDataError(RuntimeError):
    """Эфемеридного файла нет или он не совпадает с манифестом."""


@dataclass(frozen=True)
class BodyPosition:
    lon: float  # видимая долгота, эклиптика и истинное равноденствие даты, [0, 360)
    lat: float
    speed: float  # °/сутки

    @property
    def retrograde(self) -> bool:
        return self.speed < 0


@dataclass(frozen=True)
class Angles:
    ramc: float  # местное истинное звёздное время, градусы
    obliquity: float  # истинный наклон эклиптики
    asc: float
    mc: float

    @property
    def dc(self) -> float:
        return (self.asc + 180.0) % 360.0

    @property
    def ic(self) -> float:
        return (self.mc + 180.0) % 360.0


@dataclass(frozen=True)
class NotComputed:
    reason: str


def _data_dir() -> pathlib.Path:
    env = os.environ.get("LUNORA_EPHEMERIS_DIR")
    return pathlib.Path(env) if env else _REPO_DIR


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@functools.cache
def _kernel():
    path = _data_dir() / EPHEMERIS_FILE
    if not path.is_file():
        raise EphemerisDataError(
            f"нет {path} — эфемериды качает make setup (scripts/fetch_vendor.py)"
        )
    if _sha256(path) != EPHEMERIS_SHA256:
        raise EphemerisDataError(f"{path}: SHA-256 не совпадает с манифестом ({EPHEMERIS})")
    return load_file(str(path))


@functools.cache
def timescale() -> Timescale:
    """Встроенные в закреплённый Skyfield таблицы ΔT и секунд координации — без сети (§2.1)."""
    return load.timescale(builtin=True)


def reset_cache() -> None:
    """Сбросить загруженный файл (тесты подмены каталога данных)."""
    _kernel.cache_clear()


def versions() -> dict[str, str]:
    """Что записывается в каждый расчёт и в `versions` golden-кейса."""
    return {"ephemeris": EPHEMERIS, "sha256": EPHEMERIS_SHA256, "skyfield": skyfield.__version__}


# --- §2.2 момент ------------------------------------------------------------------------


def instant_scale(moment: datetime) -> Literal["utc", "ut1"]:
    if moment.tzinfo is None:
        raise ValueError("нужно время с поясом (гражданское время минус смещение)")
    return "utc" if moment >= UTC_FROM else "ut1"


def instant(moment: datetime) -> Time:
    """Момент из гражданского времени с поясом: с 1972 — UTC, до 1972 — UT1 (§2.2)."""
    scale = instant_scale(moment)
    u = moment.astimezone(UTC)
    sec = u.second + u.microsecond / 1e6
    ts = timescale()
    build = ts.utc if scale == "utc" else ts.ut1
    return build(u.year, u.month, u.day, u.hour, u.minute, sec)


# --- §2.3 тела --------------------------------------------------------------------------


def _lonlat(t: Time, name: str) -> tuple[float, float]:
    k = _kernel()
    lat, lon, _ = k["earth"].at(t).observe(k[_TARGETS[name]]).apparent().frame_latlon(
        ecliptic_frame
    )
    return lon.degrees % 360.0, lat.degrees


def body(t: Time, name: str) -> BodyPosition:
    if name not in _TARGETS:
        raise KeyError(f"тело {name!r} не в ядре v1 (§2.3, §2.10)")
    lon, lat = _lonlat(t, name)
    ts = timescale()
    before, _ = _lonlat(ts.tt_jd(t.tt - SPEED_STEP_DAYS), name)
    after, _ = _lonlat(ts.tt_jd(t.tt + SPEED_STEP_DAYS), name)
    speed = ((after - before + 180.0) % 360.0 - 180.0) / (2 * SPEED_STEP_DAYS)
    return BodyPosition(lon=lon, lat=lat, speed=speed)


def bodies(t: Time) -> dict[str, BodyPosition]:
    return {name: body(t, name) for name in BODIES}


# --- §2.4 углы --------------------------------------------------------------------------


def nutation(t: Time) -> tuple[float, float]:
    """Δψ, Δε (ИАЮ 2000A), градусы."""
    dpsi, deps = t._nutation_angles_radians
    return math.degrees(float(dpsi)), math.degrees(float(deps))


def mean_obliquity(t: Time) -> float:
    """Средний наклон эклиптики ИАЮ 2006, градусы."""
    return math.degrees(float(t._mean_obliquity_radians))


def true_obliquity(t: Time) -> float:
    return mean_obliquity(t) + nutation(t)[1]


def ramc(t: Time, lon_geo: float) -> float:
    """θ = GAST·15° + λ, градусы [0, 360)."""
    return (float(t.gast) * 15.0 + lon_geo) % 360.0


def _asc_mc(theta: float, eps: float, lat: float) -> tuple[float, float]:
    th, e, phi = math.radians(theta), math.radians(eps), math.radians(lat)
    mc = math.degrees(math.atan2(math.sin(th), math.cos(th) * math.cos(e))) % 360.0
    y = math.cos(th)
    x = -(math.sin(th) * math.cos(e) + math.tan(phi) * math.sin(e))
    asc = math.degrees(math.atan2(y, x)) % 360.0
    if (asc - mc) % 360.0 >= 180.0:  # полярное правило (§2.4, GE-04)
        asc = (asc + 180.0) % 360.0
    return asc, mc


def angles(t: Time, lat: float, lon: float) -> Angles:
    theta = ramc(t, lon)
    eps = true_obliquity(t)
    asc, mc = _asc_mc(theta, eps, lat)
    return Angles(ramc=theta, obliquity=eps, asc=asc, mc=mc)


# --- §2.5 дома --------------------------------------------------------------------------


def whole_sign_house(lon: float, asc: float) -> int:
    """Номер цельнознакового дома 1…12; границы знаков полуоткрыты [k·30°, (k+1)·30°)."""
    return (math.floor((lon % 360.0) / 30.0) - math.floor((asc % 360.0) / 30.0)) % 12 + 1


_PLACIDUS_STEPS = {11: (30.0, 1 / 3), 12: (60.0, 2 / 3), 2: (120.0, 2 / 3), 3: (150.0, 1 / 3)}


def placidus(ramc_deg: float, lat: float, eps: float) -> tuple[float, ...] | NotComputed:
    """Куспиды Плацидуса 1…12 (индекс 0 = I дом) или not_applicable_latitude (§2.5)."""
    if abs(lat) > PLACIDUS_MAX_LAT:
        return NotComputed("not_applicable_latitude")
    e, phi = math.radians(eps), math.radians(lat)
    asc, mc = _asc_mc(ramc_deg, eps, lat)
    cusps: dict[int, float] = {1: asc, 10: mc}
    for k, (h, f) in _PLACIDUS_STEPS.items():
        alpha = math.radians(ramc_deg + h)
        for _ in range(200):
            delta = math.atan(math.sin(alpha) * math.tan(e))
            x = math.tan(phi) * math.tan(delta)
            if abs(x) > 1.0:
                return NotComputed("not_applicable_latitude")
            new = math.radians(ramc_deg + h) + f * math.asin(x)
            done = abs(math.degrees(new - alpha)) < 1e-11
            alpha = new
            if done:
                break
        else:
            return NotComputed("not_applicable_latitude")
        cusps[k] = math.degrees(math.atan2(math.sin(alpha), math.cos(alpha) * math.cos(e))) % 360
    for k, opposite in ((4, 10), (5, 11), (6, 12), (7, 1), (8, 2), (9, 3)):
        cusps[k] = (cusps[opposite] + 180.0) % 360.0
    return tuple(cusps[k] for k in range(1, 13))


# --- §2.6 узлы --------------------------------------------------------------------------


def _centuries_tt(t: Time) -> float:
    return (t.tt - 2451545.0) / 36525.0


def mean_node(t: Time) -> float:
    """Средний восходящий узел, тропическая видимая долгота (с Δψ), градусы."""
    T = _centuries_tt(t)
    omega = (
        125.0445479
        - 1934.1362891 * T
        + 0.0020754 * T**2
        + T**3 / 467441.0
        - T**4 / 60616000.0
    )
    return (omega + nutation(t)[0]) % 360.0


def true_node(t: Time) -> float:
    """Истинный (оскулирующий) узел: h = r × v геоцентрической Луны в эклиптике даты."""
    k = _kernel()
    r, v = (k["moon"] - k["earth"]).at(t).frame_xyz_and_velocity(ecliptic_frame)
    rx, ry, rz = r.au
    vx, vy, vz = v.au_per_d
    hx = ry * vz - rz * vy
    hy = rz * vx - rx * vz
    return math.degrees(math.atan2(hx, -hy)) % 360.0


def south_node(node_lon: float) -> float:
    return (node_lon + 180.0) % 360.0


# --- §2.7 айанамша ----------------------------------------------------------------------

_LAHIRI_ANCHOR = 23.2455610  # средняя айанамша на 1956-03-21 0h TT (не 23°15′00,658″)
_LAHIRI_T0 = (2435553.5 - 2451545.0) / 36525.0


def _precession_pa(T: float) -> float:
    """Общая прецессия по долготе p_A, ИАЮ 2006, градусы."""
    return (
        5028.796195 * T
        + 1.1054348 * T**2
        + 0.00007964 * T**3
        - 0.000023857 * T**4
        - 0.0000000383 * T**5
    ) / 3600.0


def ayanamsha_lahiri_mean(t: Time) -> float:
    T = _centuries_tt(t)
    return _LAHIRI_ANCHOR + _precession_pa(T) - _precession_pa(_LAHIRI_T0)


def sidereal(lon_tropical: float, t: Time) -> float:
    """Сидерическая долгота по Лахири: λ − Δψ − A_mean (§2.7)."""
    return (lon_tropical - nutation(t)[0] - ayanamsha_lahiri_mean(t)) % 360.0
