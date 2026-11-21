"""Минимальный справочник мест S1 (карточка G17-S1).

Решение Антона: в S1 справочник держим минимальным — ровно чтобы различать тёзок (два
Кирова: областной `Europe/Kirov` и Калужской обл. `Europe/Moscow`) и покрыть golden-кейсы.
Полный продуктовый справочник (мелкие НП, русские названия из alternateNames) — фаза
стройки, не S1.

Данные — `data/places_min.yaml`, собран из вендоренного снимка GeoNames
(`scripts/spike/build_places_min.py`). `lookup` возвращает `Place` с зоной и регионом
admin1; регион идёт в правило `tz_disputes` (`region_of`). Сети и рантайм-загрузок нет.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib import resources

import yaml

from lunora.timeplace.disputes import region_of


class UnknownPlace(KeyError):
    """place_id нет в минимальном справочнике S1."""


@dataclass(frozen=True)
class Place:
    place_id: str
    name: str
    country: str
    admin1: str
    lat: float
    lon: float
    timezone: str

    @property
    def region(self) -> str:
        """Код региона для реестра tz_disputes (admin1 GeoNames)."""
        return region_of(self.country, self.admin1)


@cache
def _table() -> dict[str, Place]:
    text = (
        resources.files("lunora.timeplace").joinpath("data", "places_min.yaml").read_text("utf-8")
    )
    out: dict[str, Place] = {}
    for r in yaml.safe_load(text) or []:
        out[r["place_id"]] = Place(
            place_id=r["place_id"],
            name=r["name"],
            country=r["country"],
            admin1=r["admin1"],
            lat=r["lat"],
            lon=r["lon"],
            timezone=r["timezone"],
        )
    return out


def lookup(place_id: str) -> Place:
    """Место по place_id (`geonames:NNN`) из минимального справочника S1."""
    try:
        return _table()[place_id]
    except KeyError as exc:
        raise UnknownPlace(place_id) from exc


def all_places() -> tuple[Place, ...]:
    return tuple(_table().values())
