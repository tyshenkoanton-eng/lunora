from datetime import datetime, timezone

import swisseph as swe

from lunora.calc.types import (
    Aspect,
    BirthData,
    HousePosition,
    PlanetPosition,
    WesternChart,
)

SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы",
]

PLANETS = [
    (swe.SUN, "Солнце"),
    (swe.MOON, "Луна"),
    (swe.MERCURY, "Меркурий"),
    (swe.VENUS, "Венера"),
    (swe.MARS, "Марс"),
    (swe.JUPITER, "Юпитер"),
    (swe.SATURN, "Сатурн"),
    (swe.URANUS, "Уран"),
    (swe.NEPTUNE, "Нептун"),
    (swe.PLUTO, "Плутон"),
    (swe.MEAN_NODE, "Раху"),
]

ASPECT_TYPES = {
    0: ("соединение", 8),
    60: ("секстиль", 6),
    90: ("квадратура", 7),
    120: ("тригон", 8),
    180: ("оппозиция", 8),
}


def _sign_index(lon: float) -> int:
    return int(lon / 30)


def _degree_in_sign(lon: float) -> float:
    return round(lon % 30, 4)


def _to_jd(data: BirthData) -> float:
    from zoneinfo import ZoneInfo

    if data.birth_time:
        dt = datetime.combine(data.birth_date, data.birth_time, tzinfo=ZoneInfo(data.timezone))
    else:
        dt = datetime.combine(
            data.birth_date, datetime.min.time(), tzinfo=ZoneInfo(data.timezone)
        )
    utc = dt.astimezone(timezone.utc)
    return swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60.0)


def _find_house(lon: float, cusps: list[float]) -> int:
    for i in range(12):
        start = cusps[i]
        end = cusps[(i + 1) % 12]
        if start < end:
            if start <= lon < end:
                return i + 1
        else:
            if lon >= start or lon < end:
                return i + 1
    return 1


def calculate_western(data: BirthData) -> WesternChart:
    swe.set_ephe_path(None)
    jd = _to_jd(data)

    planets = []
    positions = {}
    for pid, name in PLANETS:
        result = swe.calc_ut(jd, pid)
        lon = result[0][0]
        si = _sign_index(lon)
        pp = PlanetPosition(
            name=name,
            longitude=round(lon, 4),
            sign=SIGNS[si],
            degree_in_sign=_degree_in_sign(lon),
        )
        positions[name] = lon
        planets.append(pp)

    # Ketu = 180° from Rahu
    rahu_lon = positions["Раху"]
    ketu_lon = (rahu_lon + 180) % 360
    si = _sign_index(ketu_lon)
    planets.append(PlanetPosition(
        name="Кету",
        longitude=round(ketu_lon, 4),
        sign=SIGNS[si],
        degree_in_sign=_degree_in_sign(ketu_lon),
    ))
    positions["Кету"] = ketu_lon

    houses = []
    has_time = data.birth_time is not None and data.precision != "unknown"
    if has_time:
        cusps_tuple, ascmc = swe.houses(jd, data.lat, data.lon, b"P")
        cusps = list(cusps_tuple)
        for i, cusp in enumerate(cusps):
            si = _sign_index(cusp)
            houses.append(HousePosition(
                number=i + 1,
                longitude=round(cusp, 4),
                sign=SIGNS[si],
            ))
        for pp in planets:
            pp.house = _find_house(pp.longitude, cusps)

    aspects = []
    planet_names = [name for _, name in PLANETS] + ["Кету"]
    for i in range(len(planet_names)):
        for j in range(i + 1, len(planet_names)):
            n1, n2 = planet_names[i], planet_names[j]
            if n1 not in positions or n2 not in positions:
                continue
            diff = abs(positions[n1] - positions[n2])
            if diff > 180:
                diff = 360 - diff
            for angle, (atype, max_orb) in ASPECT_TYPES.items():
                orb = abs(diff - angle)
                if orb <= max_orb:
                    aspects.append(Aspect(
                        planet1=n1,
                        planet2=n2,
                        aspect_type=atype,
                        angle=angle,
                        orb=round(orb, 2),
                    ))
                    break

    return WesternChart(planets=planets, houses=houses, aspects=aspects)
