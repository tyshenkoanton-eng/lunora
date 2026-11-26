"""G17-S1: реестр спорных случаев tz_disputes (11_architecture.md §4.3, слой 3).

Джизак (UZ): GeoNames → Asia/Samarkand, полигон → Asia/Tashkent; истории зон расходятся
до 1991. Решение Антона 2026-11-21: рантайм считает обе гипотезы, S1 не блокирует.
"""

import importlib.util
import pathlib
from datetime import date, time, timedelta

import pytest

from lunora.timeplace import load_disputes, region_of, resolve

ROOT = pathlib.Path(__file__).resolve().parents[1]

H = timedelta(hours=1)
JIZZAX = "geonames:1513886"


def test_registry_has_jizzax_with_two_zones():
    d = {x.place_id: x for x in load_disputes()}[JIZZAX]
    assert d.id == "TZD-001"
    assert (d.primary_zone, d.alternative_zone) == ("Asia/Samarkand", "Asia/Tashkent")
    assert d.status == "disputed"
    assert d.source_note


def test_disputed_place_and_date_gives_both_hypotheses():
    m = resolve(date(1985, 7, 1), time(12), "Asia/Samarkand", place_id=JIZZAX)
    assert [h.utc_offset for h in m.hypotheses] == [6 * H, 7 * H]
    assert [h.weight for h in m.hypotheses] == ["primary", "alternative"]
    assert m.hypotheses[1].reason == "tz_dispute"
    assert m.provenance["dispute_id"] == "TZD-001"


def test_disputed_place_after_zones_converge_is_unambiguous():
    m = resolve(date(2005, 1, 15), time(12), "Asia/Samarkand", place_id=JIZZAX)
    assert len(m.hypotheses) == 1
    assert "dispute_id" not in m.provenance


def test_place_without_dispute_unchanged():
    m = resolve(date(1985, 7, 1), time(12), "Asia/Tashkent", place_id="geonames:1512569")
    assert len(m.hypotheses) == 1


def test_dispute_zone_must_match_resolved_zone():
    # реестр применяется только к той зоне места, для которой заведён
    m = resolve(date(1985, 7, 1), time(12), "Asia/Tashkent", place_id=JIZZAX)
    assert len(m.hypotheses) == 1


# TZD-002 — региональное правило: всё Приднестровье по admin1 GeoNames (MD.58 Transnistria,
# MD.62 Bender Municipality), а не перечисление городов. Решение Антона 2026-11-21.
_spec = importlib.util.spec_from_file_location(
    "geonames_vendor", ROOT / "scripts" / "spike" / "geonames_vendor.py"
)
gv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gv)
CITIES = gv.load_cities(ROOT / "data" / "vendor")


def _place(geonameid: int) -> tuple[str, str, str]:
    """place_id, region (admin1 GeoNames), зона — как их отдаст справочник мест."""
    c = CITIES[geonameid]
    return f"geonames:{geonameid}", region_of(c["countrycode"], c["admin1_code"]), c["timezone"]


@pytest.mark.parametrize("geonameid", [617239, 618577, 617486, 618365])  # Тирасполь, Бендеры,
def test_transnistria_1990_gives_two_hypotheses(geonameid):  # Рыбница, Дубоссары
    place_id, region, zone = _place(geonameid)
    m = resolve(date(1990, 7, 1), time(12), zone, place_id=place_id, region=region)
    assert [h.utc_offset for h in m.hypotheses] == [3 * H, 4 * H]
    assert m.hypotheses[1].reason == "tz_dispute"
    assert m.provenance["dispute_id"] == "TZD-002"


def test_rule_is_regional_not_a_city_list():
    # населённый пункт, которого нет в записи, но он в регионе, — тоже две гипотезы
    m = resolve(date(1990, 7, 1), time(12), "Europe/Chisinau", region="geonames-admin1:MD.58")
    assert m.provenance["dispute_id"] == "TZD-002"
    d = {x.id: x for x in load_disputes()}["TZD-002"]
    assert d.place_id is None
    assert set(d.regions) == {"geonames-admin1:MD.58", "geonames-admin1:MD.62"}


def test_registry_examples_lie_in_the_region():
    d = {x.id: x for x in load_disputes()}["TZD-002"]
    assert {"geonames:617239", "geonames:618577"} <= set(d.examples)
    for ex in d.examples:
        _pid, region, zone = _place(int(ex.split(":")[1]))
        assert region in d.regions
        assert zone == d.primary_zone


def test_rest_of_moldova_unambiguous():
    place_id, region, zone = _place(618426)  # Кишинёв
    m = resolve(date(1990, 7, 1), time(12), zone, place_id=place_id, region=region)
    assert len(m.hypotheses) == 1


def test_transnistria_outside_window_unambiguous():
    # МСК после 1992-01-19 в backzone — по комментарию IANA (Эггерт, 2006) ошибка источника
    place_id, region, zone = _place(618577)
    for day in (date(1990, 4, 1), date(1991, 7, 1), date(1995, 7, 1)):
        m = resolve(day, time(12), zone, place_id=place_id, region=region)
        assert len(m.hypotheses) == 1, day
