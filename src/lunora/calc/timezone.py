"""Координаты → зона IANA ближайшего города (G17-S2e, замена `timezonefinder`).

`timezonefinder` ушёл из рантайма (ADR-001: рантайм не тянет оракулы/тяжёлые пакеты).
Источник — вендоренный снимок GeoNames `cities15000` (data/vendor/geonames/cities15000.zip,
манифест + SHA-256), ~26k городов мира с колонкой IANA-зоны. `timezone_for` возвращает зону
ближайшего города по равнопромежуточной метрике (с поправкой cos φ). Сети и загрузок нет.

Используется только UX-эндпоинтом `/geocode` (подсказка зоны по выбранному городу); сам
онбординг получает зону от клиента.
"""

from __future__ import annotations

import math
import os
import pathlib
import zipfile
from functools import cache

_REPO_DIR = pathlib.Path(__file__).resolve().parents[3] / "data" / "vendor" / "geonames"
_ARCHIVE = "cities15000.zip"
_MEMBER = "cities15000.txt"


def _data_dir() -> pathlib.Path:
    env = os.environ.get("LUNORA_GEONAMES_DIR")
    return pathlib.Path(env) if env else _REPO_DIR


@cache
def _cities() -> list[tuple[float, float, str]]:
    """Список (широта, долгота, зона IANA) из вендоренного снимка; кэш на процесс."""
    path = _data_dir() / _ARCHIVE
    out: list[tuple[float, float, str]] = []
    with zipfile.ZipFile(path) as z, z.open(_MEMBER) as fh:
        for raw in fh:
            cols = raw.decode("utf-8").rstrip("\n").split("\t")
            if len(cols) < 18:
                continue
            tz = cols[17].strip()
            if not tz:
                continue
            try:
                out.append((float(cols[4]), float(cols[5]), tz))
            except ValueError:
                continue
    return out


def timezone_for(lat: float, lon: float) -> str | None:
    """Зона IANA ближайшего города к (`lat`, `lon`); `None`, если снимок пуст."""
    cities = _cities()
    if not cities:
        return None
    coslat = math.cos(math.radians(lat))
    best_tz: str | None = None
    best_d = math.inf
    for clat, clon, tz in cities:
        dlat = clat - lat
        dlon = (clon - lon) * coslat
        d = dlat * dlat + dlon * dlon
        if d < best_d:
            best_d = d
            best_tz = tz
    return best_tz
