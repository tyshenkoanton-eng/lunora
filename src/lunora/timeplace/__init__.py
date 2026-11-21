"""timeplace — историческое время для расчёта карты (R-52, ARCHITECTURE.md §4).

Правила:
  - смещение берётся на дату рождения, никогда по текущим часам;
  - tz-база — закреплённый пакет tzdata (версия IANA пишется в провенанс), не системная;
  - несуществующий час (переход на летнее) — ошибка с просьбой уточнить;
  - повторённый час и интервал допуска через переход — несколько гипотез смещения.
"""

from lunora.timeplace.disputes import TzDispute, find_dispute, load_disputes
from lunora.timeplace.resolve import (
    Hypothesis,
    NonexistentLocalTime,
    ResolvedMoment,
    resolve,
    tz_build,
    zone_source,
)

__all__ = [
    "Hypothesis",
    "NonexistentLocalTime",
    "ResolvedMoment",
    "TzDispute",
    "find_dispute",
    "load_disputes",
    "resolve",
    "tz_build",
    "zone_source",
]
