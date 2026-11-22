"""G17-S2b: дифф движка Ба-Цзы против двух оракулов (lunar-python, cnlunar).

Схема сверки S2b (одобрено Антоном): один ручной эталон bazi.biz + два независимых
автоматических оракула на разном коде. Оракулам подаётся то же TST, что считает наш движок,
режим смены дня — 23:00 (lunar-python sect 2). Тест фиксирует и совпадения, и ДВА известных
расхождения (класс конвенции), чтобы дрейф любой стороны ловился:

  - карта A, cnlunar — год/месяц: граница термина (суточная точность ли-чунь у cnlunar);
  - карта E, lunar-python — столп дня: конвенция позднего часа Крысы (晚子时, sect 2 двигает
    только ствол часа, а не весь столп дня).

В каждом расхождении наше значение подтверждают второй оракул + ручной bazi.biz + спека §5.3/§5.4.
Оракулы — группа тестов, рантайм от них не зависит (ADR-001, test_no_oracle_imports).
"""

from datetime import date, datetime, time

import pytest

from lunora.calc import _ephem as eph
from lunora.engines import bazi
from lunora.timeplace import resolve

CARDS = [
    ("A", "geonames:472757", "1984-02-04", "15:00", "Europe/Volgograd", 44.4976,
     ("癸亥", "乙丑", "戊辰", "己未")),
    ("B", "geonames:524901", "1987-06-15", "12:00", "Europe/Moscow", 37.61781,
     ("丁卯", "丙午", "乙未", "辛巳")),
    ("C", "geonames:524305", "1990-12-22", "23:40", "Europe/Moscow", 33.09922,
     ("庚午", "戊子", "辛酉", "己亥")),
    ("D", "geonames:498817", "1962-08-09", "06:15", "Europe/Moscow", 30.31413,
     ("壬寅", "戊申", "己卯", "丁卯")),
    ("E", "geonames:524901", "1987-06-15", "00:50", "Europe/Moscow", 37.61781,
     ("丁卯", "丙午", "乙未", "丙子")),
]
# известные расхождения оракула (класс конвенции, не ошибка): {карта: {оракул: {столп}}}
KNOWN = {
    "A": {"cnlunar": {"year", "month"}},
    "E": {"lunar_python": {"day"}},
}
SLOTS = ("year", "month", "day", "hour")


def _our_tst(inp):
    m = resolve(date.fromisoformat(inp[2]), time.fromisoformat(inp[3]), inp[4],
                place_id=inp[1])
    bu = next(h for h in m.hypotheses if h.weight == "primary").utc_start
    return eph.true_solar_time(eph.instant(bu), inp[5]).tst


def _lunar_python(tst):
    Solar = pytest.importorskip("lunar_python").Solar
    ec = Solar.fromYmdHms(tst.year, tst.month, tst.day, tst.hour, tst.minute,
                          tst.second).getLunar().getEightChar()
    ec.setSect(2)  # смена дня в 23:00
    return (ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime())


def _cnlunar(tst):
    cnlunar = pytest.importorskip("cnlunar")
    lun = cnlunar.Lunar(datetime(tst.year, tst.month, tst.day, tst.hour, tst.minute,
                                 tst.second), godType="8char")
    return (lun.year8Char, lun.month8Char, lun.day8Char, lun.twohour8Char)


def _our(inp):
    m = resolve(date.fromisoformat(inp[2]), time.fromisoformat(inp[3]), inp[4],
                place_id=inp[1])
    ch = bazi.chart(m, 0.0, inp[5])
    return (ch.year.name, ch.month.name, ch.day.name, ch.hour.name)


@pytest.mark.parametrize("card", CARDS, ids=[c[0] for c in CARDS])
@pytest.mark.parametrize("oracle_name", ["lunar_python", "cnlunar"])
def test_bazi_oracle_matches_except_known(card, oracle_name):
    name = card[0]
    expected = card[6]
    assert _our(card) == expected  # наш движок = bazi.biz/спека
    tst = _our_tst(card)
    oracle = {"lunar_python": _lunar_python, "cnlunar": _cnlunar}[oracle_name](tst)
    allow = KNOWN.get(name, {}).get(oracle_name, set())
    diffs = {SLOTS[i] for i in range(4) if oracle[i] != expected[i]}
    assert diffs == allow, (
        f"{name}/{oracle_name}: расхождения {diffs}, ожидались {allow}; "
        f"оракул={oracle}, эталон={expected}"
    )
