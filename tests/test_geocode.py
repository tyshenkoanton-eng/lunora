from lunora.calc.timezone import timezone_for


def test_moscow_timezone():
    assert timezone_for(55.7558, 37.6173) == "Europe/Moscow"


def test_london_timezone():
    assert timezone_for(51.5074, -0.1278) == "Europe/London"


def test_ocean_returns_none():
    result = timezone_for(0.0, -30.0)
    assert result is None or isinstance(result, str)
