"""G17-S1: минимальный справочник мест S1 (lunora.timeplace.places)."""

import pathlib
import re

import pytest

from lunora.timeplace.places import UnknownPlace, all_places, lookup

ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"


def _golden_place_ids() -> set[str]:
    ids = set()
    for path in GOLDEN.rglob("*.y*ml"):
        if "evidence" in path.parts:
            continue
        ids |= set(re.findall(r"geonames:\d+", path.read_text(encoding="utf-8")))
    return ids


def test_two_kirovs_resolve_to_different_zones():
    # различение тёзок — ядро задачи справочника в S1
    oblast = lookup("geonames:548408")
    kaluga = lookup("geonames:548410")
    assert oblast.name == kaluga.name == "Kirov"
    assert oblast.timezone == "Europe/Kirov"
    assert kaluga.timezone == "Europe/Moscow"
    assert oblast.region != kaluga.region


def test_directory_covers_every_golden_place():
    missing = _golden_place_ids() - {p.place_id for p in all_places()}
    assert not missing, missing


def test_region_is_geonames_admin1():
    assert lookup("geonames:548408").region == "geonames-admin1:RU.33"


def test_unknown_place_raises():
    with pytest.raises(UnknownPlace):
        lookup("geonames:1")
