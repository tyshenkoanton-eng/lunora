"""Контракт сборки `calc.engine.calculate` на новом слое движков (G17-S2e).

Проверяется, что рантайм-адаптер отдаёт карту из доказанных движков `lunora.engines.*`
в форме `calc.types` (хранимый чарт / API). Содержательная корректность каждого движка
закрыта golden-наборами S2a–S2d; здесь — склейка адаптера на эталоне 15.03.1990 14:30 Москва.
"""
from datetime import date, time

from lunora.calc.engine import calculate
from lunora.calc.types import BirthData, BirthTimePrecision

BIRTH = BirthData(
    birth_date=date(1990, 3, 15),
    birth_time=time(14, 30),
    precision=BirthTimePrecision.EXACT,
    lat=55.7558,
    lon=37.6173,
    timezone="Europe/Moscow",
    name="Test",
)


class TestWestern:
    def test_sun_in_pisces(self):
        chart = calculate(BIRTH)
        sun = next(p for p in chart.western.planets if p.name == "Солнце")
        assert sun.sign == "Рыбы"
        assert 24.0 < sun.degree_in_sign < 25.0

    def test_moon_in_scorpio(self):
        chart = calculate(BIRTH)
        moon = next(p for p in chart.western.planets if p.name == "Луна")
        assert moon.sign == "Скорпион"

    def test_planet_count(self):
        chart = calculate(BIRTH)
        assert len(chart.western.planets) == 12  # септенер + высшие + Раху/Кету

    def test_houses_calculated(self):
        chart = calculate(BIRTH)
        assert len(chart.western.houses) == 12

    def test_asc_in_leo(self):
        chart = calculate(BIRTH)
        assert chart.western.houses[0].sign == "Лев"

    def test_aspects_found(self):
        chart = calculate(BIRTH)
        assert len(chart.western.aspects) > 10

    def test_ketu_opposite_rahu(self):
        chart = calculate(BIRTH)
        rahu = next(p for p in chart.western.planets if p.name == "Раху")
        ketu = next(p for p in chart.western.planets if p.name == "Кету")
        diff = abs(rahu.longitude - ketu.longitude)
        assert abs(diff - 180) < 0.01 or abs(diff - 180 + 360) < 0.01


class TestVedic:
    def test_ayanamsha_lahiri(self):
        chart = calculate(BIRTH)
        assert 23.5 < chart.vedic.ayanamsha < 24.0

    def test_sidereal_shift(self):
        # западная (тропик) − ведическая (сидерика) ≈ айанамша Лахири
        chart = calculate(BIRTH)
        sun_w = next(p for p in chart.western.planets if p.name == "Солнце")
        sun_v = next(p for p in chart.vedic.planets if p.name == "Сурья")
        shift = sun_w.longitude - sun_v.longitude
        assert 23.0 < shift < 24.5

    def test_graha_names_sanskrit(self):
        chart = calculate(BIRTH)
        names = {p.name for p in chart.vedic.planets}
        assert {"Сурья", "Чандра", "Раху", "Кету"} <= names

    def test_moon_nakshatra_swati(self):
        chart = calculate(BIRTH)
        assert chart.vedic.moon_nakshatra is not None
        assert chart.vedic.moon_nakshatra.name == "Свати"
        assert chart.vedic.moon_nakshatra.pada == 3
        assert chart.vedic.moon_nakshatra.lord == "Раху"

    def test_dasha_periods(self):
        chart = calculate(BIRTH)
        assert len(chart.vedic.dasha_periods) == 9
        assert chart.vedic.dasha_periods[0].planet == "Раху"
        total = sum(p.years for p in chart.vedic.dasha_periods)
        assert 118 < total < 122  # полный круг Вимшоттари = 120 лет


class TestChinese:
    def test_year_horse(self):
        chart = calculate(BIRTH)
        assert chart.chinese.year_animal == "Лошадь"

    def test_year_pillar(self):
        chart = calculate(BIRTH)
        assert chart.chinese.year_pillar is not None
        assert chart.chinese.year_pillar.stem == "庚"
        assert chart.chinese.year_pillar.element == "Металл"
        assert chart.chinese.year_pillar.yin_yang == "Ян"

    def test_day_master(self):
        chart = calculate(BIRTH)
        assert chart.chinese.day_master == "己"
        assert chart.chinese.day_master_element == "Земля"
        assert chart.chinese.day_master_yin_yang == "Инь"

    def test_element_balance(self):
        chart = calculate(BIRTH)
        assert chart.chinese.element_balance["Земля"] >= 2
        assert chart.chinese.element_balance["Металл"] >= 2


class TestNumerology:
    def test_life_path(self):
        chart = calculate(BIRTH)
        assert chart.numerology.life_path == 1

    def test_birthday_number(self):
        chart = calculate(BIRTH)
        assert chart.numerology.birthday_number == 6

    def test_pythagoras_square(self):
        chart = calculate(BIRTH)
        sq = chart.numerology.pythagoras
        assert sq is not None
        assert sq.cells[1] == 3  # сильный характер (три единицы)


class TestPrecisionContract:
    def test_no_houses_when_unknown_time(self):
        data = BirthData(
            birth_date=date(1990, 3, 15),
            birth_time=None,
            precision=BirthTimePrecision.UNKNOWN,
            lat=55.7558,
            lon=37.6173,
            timezone="Europe/Moscow",
        )
        chart = calculate(data)
        assert len(chart.western.houses) == 0
        for p in chart.western.planets:
            assert p.house is None
