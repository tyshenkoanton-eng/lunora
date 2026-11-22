"""G17-S2b: юнит-правила движка Ба-Цзы (§5.1–5.5, §5.10) — без эталона, по спеке.

Проверяет формулы изолированно: кодировка и обращение (стебель/ветвь ↔ номер 60-цикла),
опорная константа JDN (01.01.2000 → 戊午), «пять тигров» и «пять крыс», смена дня 23:00,
направление да-юнь по секте и полу. Эталонные карты — в test_golden_bazi.
"""

import pytest

from lunora.engines import bazi


def test_encoding_roundtrip():
    # §5.1: каждый валидный столп (ствол ≡ ветвь mod 2) обращается однозначно
    for n in range(60):
        stem, branch = n % 10, n % 12
        assert bazi.sexagenary_index(stem, branch) == n
        assert bazi.pillar_name(stem, branch) == bazi.STEMS[stem] + bazi.BRANCHES[branch]


def test_stem_element_and_polarity():
    # §5.1: стихия = floor(index/2) по кругу порождения; чётный индекс — ян
    assert bazi.stem_element(0) == "Дерево"  # 甲
    assert bazi.stem_element(9) == "Вода"  # 癸
    assert bazi.stem_is_yang(0) and not bazi.stem_is_yang(1)


def test_jdn_reference_constant():
    # §5.4 самопроверка: 01.01.2000 → JDN 2 451 545 → номер 54 → 戊午
    j = bazi.jdn(2000, 1, 1)
    assert j == 2451545
    assert (j + 49) % 60 == 54
    assert bazi.pillar_name((j + 9) % 10, (j + 1) % 12) == "戊午"


@pytest.mark.parametrize("y,m,d,expect", [
    (1984, 2, 4, "戊辰"),  # A
    (1987, 6, 15, "乙未"),  # B
    (1990, 12, 22, "辛酉"),  # C
])
def test_day_pillar_jdn(y, m, d, expect):
    j = bazi.jdn(y, m, d)
    assert bazi.pillar_name((j + 9) % 10, (j + 1) % 12) == expect


def test_five_tigers_month_stem():
    # §5.3 五虎遁: ствол месяца 寅 (m=0) по стволу года
    table = {0: 2, 1: 4, 2: 6, 3: 8, 4: 0}  # 甲→丙, 乙→戊, 丙→庚, 丁→壬, 戊→甲
    for y_stem, expect in table.items():
        assert (2 * y_stem + 2 + 0) % 10 == expect
        assert (2 * (y_stem + 5) + 2 + 0) % 10 == expect  # 己…癸 повторяют 甲…戊


def test_five_rats_hour_stem():
    # §5.5 五鼠遁: ствол часа 子 по стволу дня
    table = {0: 0, 1: 2, 2: 4, 3: 6, 4: 8}  # 甲→甲, 乙→丙, 丙→戊, 丁→庚, 戊→壬
    for d_stem, expect in table.items():
        assert (2 * d_stem + 0) % 10 == expect


@pytest.mark.parametrize("hour,branch", [
    (23, 0), (0, 0), (1, 1), (13, 7), (15, 8), (21, 11),
])
def test_hour_branch(hour, branch):
    # §5.5: ветвь_часа = floor((часы+1)/2) mod 12; 23:00–00:59 → 子
    assert ((hour + 1) // 2) % 12 == branch


def test_month_index_from_sun_longitude():
    # §5.3: m = floor(((λ − 315) mod 360)/30); 寅=0 … 丑=11
    assert bazi._month_index(315.0) == 0  # ли-чунь → 寅
    assert bazi._month_index(314.82) == 11  # перед ли-чунь → 丑 (карта A)
    assert bazi._month_index(83.71) == 4  # карта B → 午
    assert bazi._month_index(136.07) == 6  # карта D → 申


def test_dayun_direction_rule():
    # §5.10: ян-год+м или инь-год+ж → прямое; иначе обратное
    def fwd(year_stem, sex):
        yang = bazi.stem_is_yang(year_stem)
        return (yang and sex == "m") or (not yang and sex == "f")
    assert not fwd(9, "m")  # A: 癸 инь, м → обратное
    assert fwd(3, "f")  # B: 丁 инь, ж → прямое
    assert not fwd(8, "f")  # D: 壬 ян, ж → обратное
