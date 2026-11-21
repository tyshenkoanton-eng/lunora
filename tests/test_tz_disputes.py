"""G17-S1: реестр спорных случаев tz_disputes (ARCHITECTURE.md §4.3, слой 3).

Джизак (UZ): GeoNames → Asia/Samarkand, полигон → Asia/Tashkent; истории зон расходятся
до 1991. Решение Антона 2026-11-21: рантайм считает обе гипотезы, S1 не блокирует.
"""

from datetime import date, time, timedelta

from lunora.timeplace import load_disputes, resolve

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
