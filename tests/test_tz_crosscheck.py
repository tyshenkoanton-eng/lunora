"""G17-S1, шаг 3б: сверка зоны места по двум независимым путям (GeoNames ↔ полигоны)."""

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "tz_zone_crosscheck", ROOT / "scripts" / "spike" / "tz_zone_crosscheck.py"
)
xc = importlib.util.module_from_spec(_spec)
sys.modules["tz_zone_crosscheck"] = xc
_spec.loader.exec_module(xc)


def test_same_zone_is_not_a_candidate():
    assert xc.offset_divergence("Europe/Moscow", "Europe/Moscow") == 0


def test_alias_zones_with_identical_history_are_not_candidates():
    # Europe/Kiev — ссылка на Europe/Kyiv: разные имена, одинаковая история
    assert xc.offset_divergence("Europe/Kiev", "Europe/Kyiv") == 0


def test_different_history_is_counted_per_sample_date():
    # Самарканд и Ташкент расходились в 1930–1990-х (R-52: соседние зоны ≠ одно время)
    n = xc.offset_divergence("Asia/Samarkand", "Asia/Tashkent")
    assert n > 0
    assert n <= len(xc.SAMPLE_DATES)


def test_sample_grid_is_1930_2014_four_dates_a_year():
    assert len(xc.SAMPLE_DATES) == (2014 - 1930 + 1) * 4
    assert xc.SAMPLE_DATES[0].year == 1930 and xc.SAMPLE_DATES[-1].year == 2014
