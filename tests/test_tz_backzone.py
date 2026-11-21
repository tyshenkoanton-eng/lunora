"""G17-S1, шаг 3д: стандартная сборка IANA 2026f ↔ полная с backzone; пакет tzdata ↔ исходники.

Сборка — из вендоренных tzcode/tzdata (data/vendor/iana) компилятором zic 2026f, офлайн.
"""

import importlib.util
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "spike"))
_spec = importlib.util.spec_from_file_location(
    "tz_backzone_check", ROOT / "scripts" / "spike" / "tz_backzone_check.py"
)
bz = importlib.util.module_from_spec(_spec)
sys.modules["tz_backzone_check"] = bz
_spec.loader.exec_module(bz)

pytestmark = pytest.mark.skipif(
    not (shutil.which("make") and shutil.which("cc")), reason="нужны make и cc для сборки zic"
)


@pytest.fixture(scope="module")
def build(tmp_path_factory):
    return bz.build(ROOT / "data" / "vendor", tmp_path_factory.mktemp("tzbuild"))


def test_both_builds_are_2026f_and_backzone_adds_zones(build):
    assert build.version == "2026f"
    assert build.zic_version.endswith("2026f")
    assert build.zones_full > build.zones_std


def test_standard_build_equals_pinned_tzdata_package(build):
    # пакет tzdata==2026.6 с PyPI собран из тех же исходников: TZif совпадают побайтно
    assert bz.package_mismatches(build) == []


def test_zone_outside_backzone_has_no_diff(build):
    assert bz.zone_diff(build, "Europe/Moscow") is None


def test_backzone_zone_differs_before_1970(build):
    # Asia/Kuwait — в стандартной сборке ссылка на Asia/Riyadh, в backzone своя история
    d = bz.zone_diff(build, "Asia/Kuwait")
    assert d is not None
    assert d["first_year"] < 1970


def test_grid_divergence_counts_sample_dates(build):
    assert bz.grid_divergence(build, "Europe/Moscow") == 0
    assert 0 <= bz.grid_divergence(build, "Asia/Kuwait") <= len(bz.SAMPLE_DATES)


def test_tiraspol_backzone_twin_is_reported(build):
    # GeoNames ведёт Тирасполь по Europe/Chisinau; backzone: Europe/Tiraspol на МСК в 1991
    twins = {r["geonameid"]: r for r in bz.namesake_rows(build, 100_000)}
    r = twins[617239]
    assert (r["geonames_zone"], r["backzone_zone"]) == ("Europe/Chisinau", "Europe/Tiraspol")
    assert r["grid"] > 0


def test_no_ex_ussr_city_zone_differs_between_builds(build):
    _total, rows = bz.city_rows(build, 100_000)
    assert rows == []
