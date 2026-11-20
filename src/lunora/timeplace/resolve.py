"""Местное время + зона IANA → интервалы UTC с гипотезами смещения (ResolvedMoment)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from importlib import resources
from zoneinfo import ZoneInfo


class NonexistentLocalTime(ValueError):
    """Местного времени не было: часы перевели вперёд."""


@dataclass(frozen=True)
class Hypothesis:
    utc_start: datetime
    utc_end: datetime
    utc_offset: timedelta
    tz_abbr: str
    weight: str  # primary | alternative
    reason: str | None = None


@dataclass(frozen=True)
class ResolvedMoment:
    local_date: date
    local_time: time | None
    tolerance_minutes: int | None
    hypotheses: tuple[Hypothesis, ...]
    provenance: dict[str, str]


@cache
def tz_build() -> str:
    """Версия IANA закреплённого пакета tzdata (например, '2026f')."""
    header = resources.files("tzdata").joinpath("zoneinfo", "tzdata.zi").read_text("utf-8")
    m = re.match(r"#\s*version\s+(\S+)", header)
    if not m:
        raise RuntimeError("tzdata: не найдена версия IANA в tzdata.zi")
    return m.group(1)


@cache
def _zone(zone_id: str) -> ZoneInfo:
    parts = zone_id.split("/")
    node = resources.files("tzdata").joinpath("zoneinfo", *parts)
    if not node.is_file():
        raise ValueError(f"неизвестная зона IANA: {zone_id!r}")
    with node.open("rb") as fh:
        return ZoneInfo.from_file(fh, key=zone_id)


def zone_source(zone_id: str) -> str:
    _zone(zone_id)
    return "tzdata-package"


def _offsets_at(local: datetime, tz: ZoneInfo) -> list[tuple[timedelta, str]]:
    """Возможные смещения для местного момента: 0 — несуществующий, 2 — повторённый."""
    found: list[tuple[timedelta, str]] = []
    for fold in (0, 1):
        aware = local.replace(tzinfo=tz, fold=fold)
        off = aware.utcoffset()
        # момент существует, если UTC → зона возвращает то же местное время
        back = aware.astimezone(UTC).astimezone(tz).replace(tzinfo=None)
        if back == local and all(off != f[0] for f in found):
            found.append((off, aware.tzname()))
    return found


def resolve(
    local_date: date,
    local_time: time | None,
    zone_id: str,
    tolerance_minutes: int | None = 0,
) -> ResolvedMoment:
    tz = _zone(zone_id)
    if local_time is None:
        start = datetime.combine(local_date, time(0))
        end = start + timedelta(days=1)
        center = start + timedelta(hours=12)
    else:
        center = datetime.combine(local_date, local_time)
        delta = timedelta(minutes=tolerance_minutes or 0)
        start, end = center - delta, center + delta

    at_center = _offsets_at(center, tz)
    if not at_center and local_time is not None and not tolerance_minutes:
        raise NonexistentLocalTime(
            f"{center:%d.%m.%Y %H:%M} в зоне {zone_id} не существовало: часы переводили "
            "вперёд. Пожалуйста, уточните время рождения."
        )

    hyps: list[Hypothesis] = []

    def add(off: timedelta, abbr: str, reason: str | None) -> None:
        if any(h.utc_offset == off for h in hyps):
            return
        hyps.append(
            Hypothesis(
                utc_start=(start - off).replace(tzinfo=UTC),
                utc_end=(end - off).replace(tzinfo=UTC),
                utc_offset=off,
                tz_abbr=abbr,
                weight="primary" if not hyps else "alternative",
                reason=None if not hyps else reason,
            )
        )

    for off, abbr in at_center:
        add(off, abbr, "repeated_hour")
    for edge in (start, end):
        for off, abbr in _offsets_at(edge, tz):
            add(off, abbr, "interval_crosses_transition")

    return ResolvedMoment(
        local_date=local_date,
        local_time=local_time,
        tolerance_minutes=tolerance_minutes if local_time is not None else None,
        hypotheses=tuple(hyps),
        provenance={"tz_build": tz_build(), "zone_id": zone_id},
    )
