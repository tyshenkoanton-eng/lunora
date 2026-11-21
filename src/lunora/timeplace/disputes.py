"""Реестр спорных случаев tz_disputes: место или регион + интервал дат → две зоны-гипотезы.

Запись привязана либо к месту (`place_id`, точечный спор — Джизак), либо к регионам
(`regions`, admin1 GeoNames — всё Приднестровье). `examples` — справочные места региона,
в правиле не участвуют.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cache
from importlib import resources

import yaml


@dataclass(frozen=True)
class TzDispute:
    id: str
    place_id: str | None
    regions: tuple[str, ...]
    examples: tuple[str, ...]
    name: str
    primary_zone: str
    alternative_zone: str
    valid_from: date | None
    valid_to: date | None
    status: str
    source_note: str

    def applies(
        self, place_id: str | None, zone_id: str, on: date, region: str | None = None
    ) -> bool:
        where = (self.place_id is not None and place_id == self.place_id) or (
            region is not None and region in self.regions
        )
        return (
            where
            and zone_id == self.primary_zone
            and (self.valid_from is None or on >= self.valid_from)
            and (self.valid_to is None or on <= self.valid_to)
        )


def region_of(country_code: str, admin1_code: str) -> str:
    """Код региона для реестра: admin1 GeoNames, например «geonames-admin1:MD.58»."""
    return f"geonames-admin1:{country_code}.{admin1_code}"


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
                place_id=r.get("place_id"),
                regions=tuple(r.get("regions") or ()),
                examples=tuple(r.get("examples") or ()),
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


def find_dispute(
    place_id: str | None, zone_id: str, on: date, region: str | None = None
) -> TzDispute | None:
    if place_id is None and region is None:
        return None
    return next((d for d in load_disputes() if d.applies(place_id, zone_id, on, region)), None)
