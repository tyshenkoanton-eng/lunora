"""Сторож продуктового контракта карты (G17-S2f, корневая задача): продуктовая проекция
`calculate(BirthData)` НЕ теряет доказанных движком величин — каждый технический сигнал
`engines.*.signals()` либо выведен в карту, либо помечен явным `not_computed` (анти-F04).

Плюс golden-проверки самой продуктовой проекции (ASC/MC, дома по цельным знакам, D9/D10,
активные даши, да-юнь, контур имени) на эталонной карте 15.03.1990 14:30 Москва.
"""

from datetime import date, time

from lunora.calc.engine import calculate
from lunora.calc.types import BirthData
from lunora.calc.types import BirthTimePrecision as P
from lunora.engines import bazi as bz
from lunora.engines import vedic as vd
from lunora.engines import western as we
from lunora.engines.numerology import FullName
from lunora.timeplace.resolve import resolve

FN = FullName("Куликов", "Роман", "Николаевич")
BIRTH = BirthData(
    birth_date=date(1990, 3, 15), birth_time=time(14, 30), precision=P.EXACT,
    lat=55.7558, lon=37.6173, timezone="Europe/Moscow", sex="m", full_name=FN, name="Роман",
)


def _moment(b: BirthData):
    return resolve(b.birth_date, b.birth_time, b.timezone, tolerance_minutes=b.tolerance_minutes)


# ───────────────────────── сторож покрытия: продукт ⊇ сигналы ─────────────────────────


def _western_covered(chart) -> set[str]:
    cov = {"w.aspect"} if chart.aspects else set()
    if chart.planets:
        cov.add("w.position")
    if chart.asc is not None:
        cov.add("w.angle.asc")
    if chart.mc is not None:
        cov.add("w.angle.mc")
    if chart.houses:
        cov.add("w.house.cusp")
    cov |= {f"w.{k}" for k in chart.not_computed}
    return cov


def test_western_product_covers_every_signal():
    we_chart = we.chart(_moment(BIRTH), BIRTH.lat, BIRTH.lon)
    techniques = {r.rule.id for r in we.signals(we_chart)}
    product = calculate(BIRTH).western
    missing = techniques - _western_covered(product)
    assert not missing, f"западные сигналы потеряны в продукте: {missing}"


def _vedic_covered(chart) -> set[str]:
    cov = set()
    if chart.planets or chart.lagna_sign:
        cov.add("v.rashi")
    if chart.active_maha is not None or "dasha.vimshottari" in chart.not_computed:
        cov.add("v.dasha.vimshottari")
    cov |= {f"v.{k}" for k in chart.not_computed}
    return cov


def test_vedic_product_covers_every_signal():
    vd_chart = vd.chart(_moment(BIRTH), BIRTH.lat, BIRTH.lon)
    techniques = {r.rule.id for r in vd.signals(vd_chart)}
    product = calculate(BIRTH).vedic
    missing = techniques - _vedic_covered(product)
    assert not missing, f"ведические сигналы потеряны в продукте: {missing}"


def _bazi_covered(chart) -> set[str]:
    cov = set()
    pillars = (
        ("bz.pillar.year", chart.year_pillar), ("bz.pillar.month", chart.month_pillar),
        ("bz.pillar.day", chart.day_pillar), ("bz.pillar.hour", chart.hour_pillar),
    )
    for key, pillar in pillars:
        if pillar is not None:
            cov.add(key)
    if chart.dayun is not None:
        cov.add("bz.dayun")
    cov |= {f"bz.{k}" for k in chart.not_computed}
    return cov


def test_bazi_product_covers_every_signal():
    bz_chart = bz.chart(_moment(BIRTH), BIRTH.lat, BIRTH.lon, sex=BIRTH.sex)
    techniques = {r.rule.id for r in bz.signals(bz_chart)}
    product = calculate(BIRTH).chinese
    missing = techniques - _bazi_covered(product)
    assert not missing, f"сигналы Ба-Цзы потеряны в продукте: {missing}"


def test_no_time_losses_are_explicit_not_computed():
    # без времени ASC/MC/куспиды/день-час/да-юнь/активная даша — явный not_computed, не пропуск
    b = BirthData(birth_date=date(1990, 3, 15), birth_time=None, precision=P.UNKNOWN,
                  lat=55.7558, lon=37.6173, timezone="Europe/Moscow", sex="m", full_name=FN)
    c = calculate(b)
    assert c.western.not_computed["angle.asc"] == "no_birth_time"
    assert c.western.not_computed["house.cusp"] == "no_birth_time"
    assert c.vedic.not_computed["dasha.vimshottari"] == "no_birth_time"
    assert c.chinese.not_computed["pillar.day"] == "no_birth_time"
    assert c.chinese.not_computed["dayun"] == "no_birth_time"


def test_no_sex_dayun_is_explicit_not_computed():
    # без пола да-юнь — явный not_computed:no_sex (пол обязателен, но контракт держит причину)
    b = BirthData(birth_date=date(1990, 3, 15), birth_time=time(14, 30), precision=P.EXACT,
                  lat=55.7558, lon=37.6173, timezone="Europe/Moscow", sex="", full_name=FN)
    c = calculate(b)
    assert c.chinese.not_computed["dayun"] == "no_sex"
    assert c.chinese.dayun is None


# ───────────────────────── golden на продуктовую проекцию ─────────────────────────


def test_product_carries_asc_mc():
    c = calculate(BIRTH).western
    assert c.asc is not None and c.asc.sign == "Лев"
    assert c.mc is not None and c.mc.sign  # MC посчитан


def test_product_carries_whole_sign_house():
    c = calculate(BIRTH).western
    sun = next(p for p in c.planets if p.name == "Солнце")
    assert sun.house_whole is not None
    assert sun.house is not None  # Плацидус тоже


def test_product_carries_navamsa_dashamsa():
    c = calculate(BIRTH).vedic
    surya = next(p for p in c.planets if p.name == "Сурья")
    assert surya.navamsa and surya.dashamsa


def test_product_carries_active_dasha():
    c = calculate(BIRTH).vedic
    assert c.active_maha is not None
    assert c.dasha_periods  # последовательность МД


def test_product_carries_dayun_and_name_contour():
    c = calculate(BIRTH)
    assert c.chinese.dayun is not None and len(c.chinese.dayun.decades) == 9
    nn = c.numerology.name_numbers
    assert all(nn[k].value is not None for k in ("expression", "heart", "persona", "maturity"))
