#!/usr/bin/env python3
"""build_places_min — минимальный справочник мест S1 из вендоренного снимка GeoNames.

Карточка G17-S1 (решение Антона): для S1 справочник мест — МИНИМАЛЬНЫЙ, ровно чтобы
доказать различение тёзок и покрыть golden-кейсы. Полный продуктовый справочник (мелкие
НП, русские имена) — фаза стройки, не S1.

Берёт из data/vendor/geonames/cities15000.zip ровно те geonameid, что встречаются в
tests/golden (place_id вида `geonames:NNN`), плюс обоих тёзок-Кировых (548408 Europe/Kirov
и 548410 Europe/Moscow). Для каждого пишет id, имя, координаты, зону и регион admin1 в
src/lunora/timeplace/data/places_min.yaml — по нему работает lunora.timeplace.places.

Офлайн (снимок уже завендорен). Запуск:  python scripts/spike/build_places_min.py
"""

from __future__ import annotations

import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "spike"))
import geonames_vendor as gv  # noqa: E402

OUT = ROOT / "src" / "lunora" / "timeplace" / "data" / "places_min.yaml"
GOLDEN = ROOT / "tests" / "golden"
NAMESAKES = (548408, 548410)  # Киров областной (Europe/Kirov) и Калужской обл. (Europe/Moscow)


def golden_ids() -> set[int]:
    ids: set[int] = set()
    for path in GOLDEN.rglob("*.y*ml"):
        if "evidence" in path.parts:
            continue
        for m in re.finditer(r"geonames:(\d+)", path.read_text(encoding="utf-8")):
            ids.add(int(m.group(1)))
    return ids


def main() -> int:
    cities = gv.load_cities()
    wanted = sorted(golden_ids() | set(NAMESAKES))
    records = []
    for gid in wanted:
        c = cities.get(gid)
        if c is None:
            print(f"WARN  geonames:{gid} нет в снимке cities15000 — пропущен")
            continue
        records.append(
            {
                "place_id": f"geonames:{gid}",
                "name": c["name"],
                "country": c["countrycode"],
                "admin1": c["admin1_code"],
                "lat": round(c["latitude"], 5),
                "lon": round(c["longitude"], 5),
                "timezone": c["timezone"],
            }
        )
    header = (
        "# Минимальный справочник мест S1 (карточка G17-S1): тёзки + места golden-кейсов.\n"
        "# Источник — вендоренный снимок GeoNames cities15000 (data/vendor, CC BY 4.0).\n"
        "# Не править руками: python scripts/spike/build_places_min.py\n"
    )
    OUT.write_text(
        header + yaml.safe_dump(records, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(f"build_places_min: {len(records)} мест → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
