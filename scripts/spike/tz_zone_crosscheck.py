#!/usr/bin/env python3
"""tz_zone_crosscheck — зона места двумя путями: GeoNames ↔ timezonefinder (полигоны).

Для городов бывшего СССР от N жителей сравнивает зону IANA из GeoNames с зоной по
координатам. Если зоны разные, считает, на скольких датах сетки 1930–2014 × 4 смещения
расходятся (ARCHITECTURE.md §6.4). Расхождение > 0 — кандидат в tz_disputes, ручной разбор.

Запуск:  python scripts/spike/tz_zone_crosscheck.py [--min-pop 100000] [--write REPORT.md]
Нужно:   pip install -e ".[dev,oracle]"  (geonamescache, timezonefinder)
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import datetime

from lunora.timeplace.resolve import _zone, tz_build

EX_USSR = {
    "RU",
    "UA",
    "BY",
    "KZ",
    "UZ",
    "GE",
    "AZ",
    "AM",
    "MD",
    "LV",
    "LT",
    "EE",
    "KG",
    "TJ",
    "TM",
}
SAMPLE_DATES = [datetime(y, m, 15, 12) for y in range(1930, 2015) for m in (1, 4, 7, 10)]


def offset_divergence(zone_a: str, zone_b: str) -> int:
    """Число дат сетки, где смещения двух зон различаются."""
    if zone_a == zone_b:
        return 0
    za, zb = _zone(zone_a), _zone(zone_b)
    return sum(
        d.replace(tzinfo=za).utcoffset() != d.replace(tzinfo=zb).utcoffset() for d in SAMPLE_DATES
    )


def crosscheck(min_pop: int) -> tuple[int, list[dict]]:
    import geonamescache
    from timezonefinder import TimezoneFinder

    tf = TimezoneFinder()
    cities = [
        c
        for c in geonamescache.GeonamesCache().get_cities().values()
        if c["countrycode"] in EX_USSR and c["population"] >= min_pop
    ]
    rows = []
    for c in cities:
        poly = tf.timezone_at(lat=c["latitude"], lng=c["longitude"])
        if poly and poly != c["timezone"]:
            n = offset_divergence(c["timezone"], poly)
            rows.append(
                {
                    "geonameid": c["geonameid"],
                    "name": c["name"],
                    "country": c["countrycode"],
                    "population": c["population"],
                    "geonames_zone": c["timezone"],
                    "polygon_zone": poly,
                    "divergent_dates": n,
                }
            )
    rows.sort(key=lambda r: (-r["divergent_dates"], r["name"]))
    return len(cities), rows


def render(total: int, rows: list[dict], min_pop: int) -> str:
    import importlib.metadata as md

    cand = [r for r in rows if r["divergent_dates"]]
    lines = [
        "# Сверка зоны места: GeoNames ↔ полигоны (G17-S1, шаг 3б)",
        "",
        "<!-- СГЕНЕРИРОВАНО scripts/spike/tz_zone_crosscheck.py. Руками не править. -->",
        "",
        f"Города бывшего СССР от {min_pop:,} жителей: **{total}**. ".replace(",", " ")
        + f"Разные зоны: **{len(rows)}**, из них кандидатов в `tz_disputes` "
        f"(смещения расходятся хотя бы на одной дате сетки 1930–2014 × 4): **{len(cand)}**.",
        "",
        f"Версии: tzdata {tz_build()}, geonamescache {md.version('geonamescache')}, "
        f"timezonefinder {md.version('timezonefinder')}. Данные мест — GeoNames, CC BY 4.0.",
        "",
        "| GeoNames id | Город | Страна | Население | Зона GeoNames | Зона по полигону "
        "| Дат с расхождением (из 340) | Разбор |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['geonameid']} | {r['name']} | {r['country']} | {r['population']} "
            f"| {r['geonames_zone']} | {r['polygon_zone']} | {r['divergent_dates']} "
            "| требует ручного разбора |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-pop", type=int, default=100_000)
    ap.add_argument("--write", type=pathlib.Path)
    args = ap.parse_args()
    total, rows = crosscheck(args.min_pop)
    text = render(total, rows, args.min_pop)
    if args.write:
        args.write.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
