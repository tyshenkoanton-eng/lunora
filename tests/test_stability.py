"""G17-S1: единица стабильности сигнала (ARCHITECTURE §4.5) — lunora.calc.stability."""

from datetime import UTC, datetime, timedelta

from lunora.calc.stability import changes, stability, values_on
from lunora.timeplace.resolve import Hypothesis, ResolvedMoment


def _moment(*spans: tuple[datetime, datetime]) -> ResolvedMoment:
    hyps = tuple(
        Hypothesis(
            utc_start=s,
            utc_end=e,
            utc_offset=timedelta(0),
            tz_abbr="X",
            weight="primary" if i == 0 else "alternative",
        )
        for i, (s, e) in enumerate(spans)
    )
    return ResolvedMoment(
        local_date=spans[0][0].date(),
        local_time=None,
        tolerance_minutes=None,
        hypotheses=hyps,
        provenance={},
    )


def _step(threshold: datetime):
    return lambda t: "after" if t >= threshold else "before"


def test_stable_when_signal_constant():
    s, e = datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, 1, tzinfo=UTC)
    tag, vals = stability(_moment((s, e)), lambda _t: "x")
    assert tag == "stable" and vals == ["x"]


def test_range_when_one_change():
    s, e = datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, 2, tzinfo=UTC)
    thr = datetime(2020, 1, 1, 1, tzinfo=UTC)
    tag, vals = stability(_moment((s, e)), _step(thr))
    assert tag == "range" and set(vals) == {"before", "after"}


def test_undetermined_when_many_values():
    s, e = datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, 3, tzinfo=UTC)
    tag, vals = stability(_moment((s, e)), lambda t: t.hour)
    assert tag == "undetermined" and len(vals) >= 3


def test_change_moment_found_by_bisection():
    s, e = datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, 2, tzinfo=UTC)
    thr = datetime(2020, 1, 1, 1, 17, 40, tzinfo=UTC)
    (moment,) = changes(_step(thr), s, e)
    assert abs((moment - thr).total_seconds()) <= 1.0


def test_two_hypotheses_same_value_stays_stable():
    # §4.5 шаг 4: сигнал, одинаковый в обеих гипотезах смещения, остаётся stable
    s1 = (datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, 1, tzinfo=UTC))
    s2 = (datetime(2020, 1, 1, 3, tzinfo=UTC), datetime(2020, 1, 1, 4, tzinfo=UTC))
    tag, vals = stability(_moment(s1, s2), lambda _t: "same")
    assert tag == "stable" and vals == ["same"]


def test_values_on_lists_in_order():
    s, e = datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 1, 2, tzinfo=UTC)
    thr = datetime(2020, 1, 1, 1, tzinfo=UTC)
    assert values_on(_step(thr), s, e) == ["before", "after"]


# ─────────────── F05: поиск границ по непрерывной угловой скорости ───────────────
# На широтах 65–67° асцендент близ полуночного максимума скорости пробегает знаки за минуты:
# сетка 10 мин теряет смены, а шаг по скорости угла — нет. Property-тест: результат рейт-поиска
# совпадает с плотным перебором (1 с), а старая сетка на той же выборке что-то теряет.

import math  # noqa: E402

from lunora.calc import _ephem as eph  # noqa: E402
from lunora.calc.stability import changes as _changes  # noqa: E402


def _asc_signals(lat: float, lon: float):
    """(знак асцендента, скорость угла °/сек) как функции времени для широты lat."""

    def sign(dt: datetime) -> int:
        return math.floor(eph.angles(eph.instant(dt), lat, lon).asc / 30.0)

    def rate(dt: datetime) -> float:
        a0 = eph.angles(eph.instant(dt), lat, lon).asc
        a1 = eph.angles(eph.instant(dt + timedelta(seconds=5)), lat, lon).asc
        return abs(((a1 - a0 + 180.0) % 360.0) - 180.0) / 5.0

    return sign, rate


def _dense_values(sign, start: datetime, end: datetime) -> list[int]:
    """Эталон: значения на плотной сетке 1 с (без пропусков по построению)."""
    out: list[int] = []
    t = start
    while t <= end:
        v = sign(t)
        if not out or out[-1] != v:
            out.append(v)
        t += timedelta(seconds=1)
    return out


def test_f05_rate_search_matches_dense_grid_at_high_latitude():
    lat, lon = 66.0, 25.0  # у Полярного круга, окно быстрого асцендента (≈5 знаков за 20 мин)
    start = datetime(1990, 6, 21, 22, 5, tzinfo=UTC)
    end = start + timedelta(minutes=25)
    sign, rate = _asc_signals(lat, lon)

    dense = _dense_values(sign, start, end)
    rate_marks = [sign(start), *(sign(m) for m in _changes(sign, start, end, rate))]
    # сжать повторы рейт-результата и сравнить со сжатым эталоном
    compact: list[int] = []
    for v in rate_marks:
        if not compact or compact[-1] != v:
            compact.append(v)
    assert compact == dense
    # смен несколько — кейс действительно «быстрый» (иначе тест ничего не проверяет)
    assert len(dense) >= 3


def test_f05_coarse_grid_misses_changes_that_rate_search_finds():
    lat, lon = 66.0, 25.0
    start = datetime(1990, 6, 21, 22, 5, tzinfo=UTC)
    end = start + timedelta(minutes=25)
    sign, rate = _asc_signals(lat, lon)

    by_rate = _changes(sign, start, end, rate)
    by_grid = _changes(sign, start, end)  # сетка 10 мин
    assert len(by_rate) > len(by_grid)  # сетка теряет часть смен, рейт-поиск — нет
