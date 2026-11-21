"""G17-S1: справочник мест GeoNames — из вендоренного снимка (офлайн), не из сети/PyPI."""

import importlib.util
import pathlib
import sys

import pytest

from lunora.timeplace.resolve import _zone

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "data" / "vendor"
_spec = importlib.util.spec_from_file_location(
    "geonames_vendor", ROOT / "scripts" / "spike" / "geonames_vendor.py"
)
gv = importlib.util.module_from_spec(_spec)
sys.modules["geonames_vendor"] = gv
_spec.loader.exec_module(gv)


@pytest.fixture(scope="module")
def cities():
    return gv.load_cities(VENDOR)


def test_snapshot_is_cities15000(cities):
    assert len(cities) > 20_000
    assert all(c["population"] >= 0 for c in cities.values())


def test_moscow_record(cities):
    m = cities[524901]
    assert (m["countrycode"], m["timezone"]) == ("RU", "Europe/Moscow")
    assert "Москва" in m["alternatenames"]


def test_jizzakh_matches_tz_dispute_registry(cities):
    # TZD-001: основная зона Джизака по GeoNames — Asia/Samarkand
    assert cities[1513886]["timezone"] == "Asia/Samarkand"


def test_every_geonames_zone_exists_in_pinned_tzdata(cities):
    missing = set()
    for zone in {c["timezone"] for c in cities.values()}:
        try:
            _zone(zone)
        except Exception:
            missing.add(zone)
    assert missing == set()


def test_manifest_has_geonames_snapshot():
    import yaml

    m = yaml.safe_load((VENDOR / "MANIFEST.yaml").read_text(encoding="utf-8"))
    s = m["sets"]["geonames"]
    assert "CC BY 4.0" in s["license"]
    assert {f["path"] for f in s["files"]} >= {"geonames/cities15000.zip"}
