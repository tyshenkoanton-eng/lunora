"""Допуск времени и стабильность сигнала (ARCHITECTURE §4.5, D-046, D-G7-19).

Неточное время рождения и спорный часовой пояс — одна механика (§4.5): вход даёт
`ResolvedMoment` с интервалом(ами) UTC, а каждый зависящий от времени дискретный сигнал
(знак асцендента, столп часа, граница накшатры, термин) проверяется на этом интервале.

`stability(moment, signal)` возвращает тег §4.5:
  - `stable`        — значение одно на всех интервалах всех гипотез;
  - `range`         — различных значений ровно два;
  - `undetermined`  — больше двух.

Сигнал — функция `datetime (UTC) -> hashable`. Границы ищутся делением пополам между
точками с разными значениями (§4.5: «для дискретных сигналов — поиск корня»), а не
принимаются по значению в опорной точке.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from datetime import UTC, datetime, timedelta
from typing import Literal

from lunora.timeplace.resolve import ResolvedMoment

Stability = Literal["stable", "range", "undetermined"]
Signal = Callable[[datetime], Hashable]

# шаг первичного сканирования интервала: асцендент проходит знак (30°) не быстрее ~1,8 ч
# даже у экватора, поэтому 10 мин не пропускают смену; найденные смены уточняются делением
_SCAN_STEP = timedelta(minutes=10)
_BISECT_EPS = timedelta(seconds=1)


def _grid(start: datetime, end: datetime) -> list[datetime]:
    pts, t = [start], start + _SCAN_STEP
    while t < end:
        pts.append(t)
        t += _SCAN_STEP
    pts.append(end)
    return pts


def _refine(signal: Signal, lo: datetime, hi: datetime) -> datetime:
    """Момент смены значения в (lo, hi], где signal(lo) ≠ signal(hi)."""
    a = signal(lo)
    while hi - lo > _BISECT_EPS:
        mid = lo + (hi - lo) / 2
        if signal(mid) == a:
            lo = mid
        else:
            hi = mid
    return hi


def changes(signal: Signal, start: datetime, end: datetime) -> list[datetime]:
    """Моменты смены дискретного сигнала на [start, end] (поиск корня, не перебор)."""
    out: list[datetime] = []
    grid = _grid(start, end)
    for lo, hi in zip(grid, grid[1:], strict=False):
        if signal(lo) != signal(hi):
            out.append(_refine(signal, lo, hi))
    return out


def values_on(signal: Signal, start: datetime, end: datetime) -> list[Hashable]:
    """Все различные значения сигнала на интервале, в порядке появления."""
    seen: list[Hashable] = []
    marks = [start, *changes(signal, start, end), end]
    for lo, hi in zip(marks, marks[1:], strict=False):
        mid = lo + (hi - lo) / 2
        v = signal(mid)
        if v not in seen:
            seen.append(v)
    return seen


def stability(moment: ResolvedMoment, signal: Signal) -> tuple[Stability, list[Hashable]]:
    """Тег §4.5 и список значений по всем гипотезам смещения `moment`."""
    values: list[Hashable] = []
    for h in moment.hypotheses:
        start = h.utc_start if h.utc_start.tzinfo else h.utc_start.replace(tzinfo=UTC)
        end = h.utc_end if h.utc_end.tzinfo else h.utc_end.replace(tzinfo=UTC)
        for v in values_on(signal, start, end):
            if v not in values:
                values.append(v)
    tag: Stability = (
        "stable" if len(values) == 1 else "range" if len(values) == 2 else "undetermined"
    )
    return tag, values
