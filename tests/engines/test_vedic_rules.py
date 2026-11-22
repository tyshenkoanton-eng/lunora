"""G17-S2d: юнит-правила ведического движка (§4.1–4.4) — без эталона, по спеке.

Формулы изолированно: раши/накшатра/пада, навамша D9 и дашамша D10 на примерах §4.4,
порядок и суммы Вимшоттари, управитель накшатры, бхавы. Эталонные карты — test_golden_vedic.
"""

import pytest

from lunora.engines import vedic


def test_rashi_nakshatra_pada_boundaries():
    assert vedic.rashi_index(0.0) == 0 and vedic.rashi_index(359.9) == 11
    assert vedic.nakshatra_index(0.0) == 0  # Ашвини
    assert vedic.nakshatra_index(13 + 1 / 3) == 1  # граница Бхарани
    assert vedic.pada(0.0) == 1 and vedic.pada(11.0) == 4  # 11° Меши = 4-я пада Ашвини


def test_vimshottari_order_sum():
    assert sum(y for _, y in vedic.VIMSHOTTARI) == 120
    assert vedic.VIMSHOTTARI[0] == ("Кету", 7)
    # управитель накшатры = порядок[N mod 9]: Шатабхиша N=23 → Раху
    assert vedic.nakshatra_lord(23) == "Раху"  # карта A Чандра
    assert vedic.nakshatra_lord(21) == "Чандра"  # Шравана (B)
    assert vedic.nakshatra_lord(15) == "Гуру"  # Вишакха (D)


@pytest.mark.parametrize("lon,d9", [
    (291.187, "Карка"),   # A Сурья 21°11′ Макары
    (318.05, "Мина"),     # A Чандра 18°03′ Кумбхи
    (202.4, "Меша"),      # A Шани 22°24′ Тулы
    (359.766, "Мина"),    # B Гуру 29°46′ Мины (варготтама)
])
def test_navamsa_d9(lon, d9):
    assert vedic.RASHIS[vedic.navamsa_sign(lon)] == d9


@pytest.mark.parametrize("lon,d10", [
    (291.187, "Меша"),   # A Сурья: Макара (чётный знак) k=7 → (9+8+7)%12=0
    (318.05, "Симха"),   # A Чандра: Кумбха (нечётный) k=6 → (10+6)%12=4
    (202.4, "Вришабха"), # A Шани: Тула (нечётный) k=0 → (6+0)? проверка §4.4
])
def test_dashamsa_d10(lon, d10):
    assert vedic.RASHIS[vedic.dashamsa_sign(lon)] == d10


def test_dashamsa_odd_even_rule():
    # нечётный знак (индекс чётный): с себя; чётный (индекс нечётный): с 9-го (+8)
    assert vedic.dashamsa_sign(0.0) == 0       # Меша (нечётн.) k=0 → 0
    assert vedic.dashamsa_sign(30.0) == 1 + 8  # Вришабха (чётн.) k=0 → 9 (Макара)


def test_navamsa_vargottama():
    # варготтама: D1 и D9 совпадают (B Гуру 29°46′ Мины → обе Мина)
    lon = 359.766
    assert vedic.rashi_index(lon) == vedic.navamsa_sign(lon) == 11
