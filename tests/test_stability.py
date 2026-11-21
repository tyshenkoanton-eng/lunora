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
