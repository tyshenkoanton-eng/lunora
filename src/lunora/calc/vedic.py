from datetime import datetime, timezone

import swisseph as swe

from lunora.calc.types import (
    BirthData,
    DashaPeriod,
    Nakshatra,
    PlanetPosition,
    VedicChart,
)

SIGNS_EN = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
SIGNS_RU = [
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы",
]
SIGNS_SANSKRIT = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena",
]

NAKSHATRAS = [
    ("Ashwini", "Кету"), ("Bharani", "Венера"), ("Krittika", "Солнце"),
    ("Rohini", "Луна"), ("Mrigashira", "Марс"), ("Ardra", "Раху"),
    ("Punarvasu", "Юпитер"), ("Pushya", "Сатурн"), ("Ashlesha", "Меркурий"),
    ("Magha", "Кету"), ("Purva Phalguni", "Венера"), ("Uttara Phalguni", "Солнце"),
    ("Hasta", "Луна"), ("Chitra", "Марс"), ("Swati", "Раху"),
    ("Vishakha", "Юпитер"), ("Anuradha", "Сатурн"), ("Jyeshtha", "Меркурий"),
    ("Mula", "Кету"), ("Purva Ashadha", "Венера"), ("Uttara Ashadha", "Солнце"),
    ("Shravana", "Луна"), ("Dhanishta", "Марс"), ("Shatabhisha", "Раху"),
    ("Purva Bhadrapada", "Юпитер"), ("Uttara Bhadrapada", "Сатурн"), ("Revati", "Меркурий"),
]

DASHA_LORDS_ORDER = ["Кету", "Венера", "Солнце", "Луна", "Марс",
                     "Раху", "Юпитер", "Сатурн", "Меркурий"]
DASHA_YEARS = {"Кету": 7, "Венера": 20, "Солнце": 6, "Луна": 10, "Марс": 7,
               "Раху": 18, "Юпитер": 16, "Сатурн": 19, "Меркурий": 17}

PLANETS = [
    (swe.SUN, "Солнце"),
    (swe.MOON, "Луна"),
    (swe.MERCURY, "Меркурий"),
    (swe.VENUS, "Венера"),
    (swe.MARS, "Марс"),
    (swe.JUPITER, "Юпитер"),
    (swe.SATURN, "Сатурн"),
    (swe.MEAN_NODE, "Раху"),
]


def _to_jd(data: BirthData) -> float:
    from zoneinfo import ZoneInfo

    if data.birth_time:
        dt = datetime.combine(data.birth_date, data.birth_time, tzinfo=ZoneInfo(data.timezone))
    else:
        dt = datetime.combine(data.birth_date, datetime.min.time(), tzinfo=ZoneInfo(data.timezone))
    utc = dt.astimezone(timezone.utc)
    return swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60.0)


def _sign_index(lon: float) -> int:
    return int(lon / 30)


def _degree_in_sign(lon: float) -> float:
    return round(lon % 30, 4)


def _get_nakshatra(moon_lon: float) -> Nakshatra:
    nak_index = int(moon_lon / (360 / 27))
    pada = int((moon_lon % (360 / 27)) / (360 / 108)) + 1
    name, lord = NAKSHATRAS[nak_index]
    return Nakshatra(name=name, pada=pada, lord=lord)


def _calc_dasha(moon_lon: float, birth_year: float) -> list[DashaPeriod]:
    nak_index = int(moon_lon / (360 / 27))
    _, nak_lord = NAKSHATRAS[nak_index]

    elapsed_fraction = (moon_lon % (360 / 27)) / (360 / 27)
    lord_idx = DASHA_LORDS_ORDER.index(nak_lord)

    remaining_years = DASHA_YEARS[nak_lord] * (1 - elapsed_fraction)

    periods = []
    current_year = birth_year
    first_lord = DASHA_LORDS_ORDER[lord_idx]
    periods.append(DashaPeriod(
        planet=first_lord,
        start_year=round(current_year, 1),
        end_year=round(current_year + remaining_years, 1),
        years=round(remaining_years, 1),
    ))
    current_year += remaining_years

    for i in range(1, 9):
        idx = (lord_idx + i) % 9
        lord = DASHA_LORDS_ORDER[idx]
        years = DASHA_YEARS[lord]
        periods.append(DashaPeriod(
            planet=lord,
            start_year=round(current_year, 1),
            end_year=round(current_year + years, 1),
            years=years,
        ))
        current_year += years

    return periods


def calculate_vedic(data: BirthData) -> VedicChart:
    swe.set_ephe_path(None)
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    jd = _to_jd(data)

    ayanamsha = swe.get_ayanamsa_ut(jd)

    planets = []
    moon_lon = 0.0
    for pid, name in PLANETS:
        result = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)
        lon = result[0][0]
        si = _sign_index(lon)
        planets.append(PlanetPosition(
            name=name,
            longitude=round(lon, 4),
            sign=SIGNS_RU[si],
            degree_in_sign=_degree_in_sign(lon),
        ))
        if pid == swe.MOON:
            moon_lon = lon

    # Ketu
    rahu_lon = next(p.longitude for p in planets if p.name == "Раху")
    ketu_lon = (rahu_lon + 180) % 360
    si = _sign_index(ketu_lon)
    planets.append(PlanetPosition(
        name="Кету",
        longitude=round(ketu_lon, 4),
        sign=SIGNS_RU[si],
        degree_in_sign=_degree_in_sign(ketu_lon),
    ))

    moon_nakshatra = _get_nakshatra(moon_lon)
    birth_year = data.birth_date.year + (data.birth_date.timetuple().tm_yday / 365.25)
    dasha_periods = _calc_dasha(moon_lon, birth_year)

    # Reset to tropical for other callers
    swe.set_sid_mode(swe.SIDM_FAGAN_BRADLEY)

    return VedicChart(
        planets=planets,
        ayanamsha=round(ayanamsha, 4),
        moon_nakshatra=moon_nakshatra,
        dasha_periods=dasha_periods,
    )
