#!/usr/bin/env python3
"""geonames_vendor — чтение вендоренного снимка GeoNames (data/vendor/geonames), офлайн.

Формат — таблица `geoname` из readme.txt GeoNames (19 колонок, TSV, UTF-8).
Данные GeoNames — CC BY 4.0 (https://www.geonames.org/), атрибуция обязательна.
"""

from __future__ import annotations

import csv
import io
import pathlib
import zipfile

DEFAULT = pathlib.Path(__file__).resolve().parents[2] / "data" / "vendor"
COLUMNS = (
    "geonameid",
    "name",
    "asciiname",
    "alternatenames",
    "latitude",
    "longitude",
    "feature_class",
    "feature_code",
    "countrycode",
    "cc2",
    "admin1_code",
    "admin2_code",
    "admin3_code",
    "admin4_code",
    "population",
    "elevation",
    "dem",
    "timezone",
    "modification_date",
)


def load_cities(root: pathlib.Path = DEFAULT, name: str = "cities15000") -> dict[int, dict]:
    """geonameid → запись города (координаты float, население int, alternatenames list)."""
    with zipfile.ZipFile(root / "geonames" / f"{name}.zip") as zf:
        raw = zf.read(f"{name}.txt").decode("utf-8")
    out: dict[int, dict] = {}
    for row in csv.reader(io.StringIO(raw), delimiter="\t", quoting=csv.QUOTE_NONE):
        rec = dict(zip(COLUMNS, row, strict=True))
        rec["geonameid"] = int(rec["geonameid"])
        rec["latitude"] = float(rec["latitude"])
        rec["longitude"] = float(rec["longitude"])
        rec["population"] = int(rec["population"] or 0)
        rec["alternatenames"] = rec["alternatenames"].split(",") if rec["alternatenames"] else []
        out[rec["geonameid"]] = rec
    return out
