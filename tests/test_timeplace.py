"""G17-S1, шаг 3: время и пояса (R-52). Ожидаемые смещения — история зон IANA 2026f.

Это тесты кода против закреплённой tz-базы. Внешний эталон (astro.com) приходит
отдельно — golden-кейсы слоя timeplace в tests/golden/ после ручного съёма.
"""

import ast
import pathlib
from datetime import UTC, date, datetime, time, timedelta

import pytest

from lunora import timeplace
from lunora.timeplace import NonexistentLocalTime, resolve

H = timedelta(hours=1)


def test_tz_build_is_pinned_2026f():
    assert timeplace.tz_build() == "2026f"


@pytest.mark.parametrize(
    ("zone", "d", "t", "offset"),
    [
        ("Europe/Moscow", date(1987, 7, 1), time(12), 4 * H),  # декретное + летнее
        ("Europe/Moscow", date(1987, 1, 15), time(12), 3 * H),  # декретное
        ("Europe/Moscow", date(1991, 7, 1), time(12), 3 * H),  # отмена декретного
        ("Europe/Moscow", date(1992, 1, 10), time(12), 2 * H),  # зима 1991–92
        ("Europe/Moscow", date(2010, 7, 1), time(12), 4 * H),
        ("Europe/Moscow", date(2012, 7, 1), time(12), 4 * H),  # «вечное летнее»
        ("Europe/Moscow", date(2015, 1, 15), time(12), 3 * H),
        ("Europe/Volgograd", date(1984, 2, 4), time(15), 4 * H),  # R-52: не московское
    ],
)
def test_offset_on_birth_date_not_today(zone, d, t, offset):
    m = resolve(d, t, zone)
    assert len(m.hypotheses) == 1
    h = m.hypotheses[0]
    assert h.utc_offset == offset
    assert h.weight == "primary"
    assert h.utc_start == h.utc_end == datetime.combine(d, t, UTC) - offset


def test_volgograd_1984_reference_chart_utc():
    # Карта A (ENGINE-SPEC §0.5): 04.02.1984 15:00 местного → 11:00 UTC
    h = resolve(date(1984, 2, 4), time(15), "Europe/Volgograd").hypotheses[0]
    assert h.utc_start == datetime(1984, 2, 4, 11, tzinfo=UTC)


def test_nonexistent_hour_is_an_error_asking_to_clarify():
    with pytest.raises(NonexistentLocalTime) as exc:
        resolve(date(1987, 3, 29), time(2, 30), "Europe/Moscow")
    assert "уточн" in str(exc.value)


def test_repeated_hour_gives_two_hypotheses():
    m = resolve(date(1987, 9, 27), time(2, 30), "Europe/Moscow")
    offsets = [h.utc_offset for h in m.hypotheses]
    assert offsets == [4 * H, 3 * H]
    assert [h.weight for h in m.hypotheses] == ["primary", "alternative"]
    assert m.hypotheses[1].reason == "repeated_hour"


def test_tolerance_makes_utc_interval():
    h = resolve(date(1987, 7, 1), time(12), "Europe/Moscow", tolerance_minutes=30).hypotheses[0]
    assert h.utc_start == datetime(1987, 7, 1, 7, 30, tzinfo=UTC)
    assert h.utc_end == datetime(1987, 7, 1, 8, 30, tzinfo=UTC)


def test_tolerance_across_transition_adds_alternative_offset():
    # 29.03.1987 в 02:00 Москва перешла на летнее; ±3 ч от 01:00 пересекает переход
    m = resolve(date(1987, 3, 29), time(1), "Europe/Moscow", tolerance_minutes=180)
    assert {h.utc_offset for h in m.hypotheses} == {3 * H, 4 * H}
    assert any(h.reason == "interval_crosses_transition" for h in m.hypotheses)


def test_unknown_time_covers_whole_local_day():
    m = resolve(date(1984, 2, 4), None, "Europe/Volgograd")
    h = m.hypotheses[0]
    assert m.local_time is None
    assert h.utc_start == datetime(1984, 2, 3, 20, tzinfo=UTC)
    assert h.utc_end == datetime(1984, 2, 4, 20, tzinfo=UTC)


def test_provenance_records_build_and_zone():
    m = resolve(date(1984, 2, 4), time(15), "Europe/Volgograd")
    assert m.provenance == {"tz_build": "2026f", "zone_id": "Europe/Volgograd"}


def test_unknown_zone_rejected():
    with pytest.raises(ValueError):
        resolve(date(1984, 2, 4), time(15), "Mars/Olympus")


def test_never_reads_current_clock():
    src = pathlib.Path(timeplace.__file__).parent
    for py in src.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text("utf-8"))):
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"now", "utcnow", "today"}, f"{py.name}: {node.attr}"


def test_ignores_system_tzdb():
    # зона читается из закреплённого пакета tzdata, не из /usr/share/zoneinfo образа
    assert timeplace.zone_source("Europe/Moscow") == "tzdata-package"
