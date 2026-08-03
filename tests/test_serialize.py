from lunora.calc.serialize import chart_to_dict
from lunora.calc.types import (
    BaziPillar,
    ChineseChart,
    FullChart,
    NumerologyChart,
    PlanetPosition,
    PythagorasSquare,
    WesternChart,
)


def test_planet_to_dict():
    p = PlanetPosition(name="Sun", longitude=350.5, sign="Pisces", degree_in_sign=20.5, house=7)
    d = chart_to_dict(p)
    assert d["name"] == "Sun"
    assert d["house"] == 7


def test_western_chart():
    w = WesternChart(
        planets=[PlanetPosition("Sun", 0.0, "Aries", 0.0)],
        houses=[],
        aspects=[],
    )
    d = chart_to_dict(w)
    assert len(d["planets"]) == 1
    assert d["planets"][0]["sign"] == "Aries"


def test_chinese_chart():
    c = ChineseChart(
        year_pillar=BaziPillar(stem="庚", branch="午", element="Metal", yin_yang="Yang", animal="Horse"),
        element_balance={"Wood": 2, "Fire": 3},
    )
    d = chart_to_dict(c)
    assert d["year_pillar"]["stem"] == "庚"
    assert d["element_balance"]["Fire"] == 3


def test_numerology_pythagoras():
    n = NumerologyChart(
        life_path=1,
        birthday_number=6,
        pythagoras=PythagorasSquare(cells={1: 3, 2: 0}, working_numbers=(1, 2, 3, 4)),
    )
    d = chart_to_dict(n)
    assert d["life_path"] == 1
    assert d["pythagoras"]["working_numbers"] == [1, 2, 3, 4]


def test_none_chart():
    assert chart_to_dict(None) == {}


def test_full_chart():
    fc = FullChart()
    d = chart_to_dict(fc)
    assert d["western"] is None
    assert d["vedic"] is None
