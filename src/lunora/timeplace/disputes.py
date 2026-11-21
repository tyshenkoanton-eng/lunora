"""Реестр спорных случаев tz_disputes: место + интервал дат → две зоны-гипотезы."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cache
from importlib import resources

import yaml


@dataclass(frozen=True)
class TzDispute:
    id: str
    place_id: str
    name: str
    primary_zone: str
    alternative_zone: str
    valid_from: date | None
    valid_to: date | None
    status: str
    source_note: str

    def applies(self, place_id: str | None, zone_id: str, on: date) -> bool:
        return (
            place_id == self.place_id
            and zone_id == self.primary_zone
            and (self.valid_from is None or on >= self.valid_from)
            and (self.valid_to is None or on <= self.valid_to)
        )


def _d(v: object) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


@cache
def load_disputes() -> tuple[TzDispute, ...]:
    text = (
        resources.files("lunora.timeplace").joinpath("data", "tz_disputes.yaml").read_text("utf-8")
    )
    out = []
    for r in yaml.safe_load(text) or []:
        out.append(
            TzDispute(
                id=r["id"],
                place_id=r["place_id"],
                name=r["name"],
                primary_zone=r["primary_zone"],
                alternative_zone=r["alternative_zone"],
                valid_from=_d(r.get("valid_from")),
                valid_to=_d(r.get("valid_to")),
                status=r["status"],
                source_note=r["source_note"],
            )
        )
    return tuple(out)


def find_dispute(place_id: str | None, zone_id: str, on: date) -> TzDispute | None:
    if place_id is None:
        return None
    return next((d for d in load_disputes() if d.applies(place_id, zone_id, on)), None)
