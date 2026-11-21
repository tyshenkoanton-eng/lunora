"""G17-S2a: правила нумерологии по примерам спеки (NUMEROLOGY-RULES.md §1.5, §2, §3, §4, §5).

Golden §9.2 — в test_golden_numerology.py. Здесь — примеры нормализации §1.5, таблица букв,
свёртка, числа даты §4.1/§4.2 и property-тесты (seed фиксирован, детерминированно).
"""

import random
from datetime import date, timedelta

import pytest

from lunora.engines import numerology as num


def _name(s, g, p=None):
    return num.FullName(s, g, p)


OBL = {"oblique_case_suspected"}

# §1.5: (ввод, рабочая строка, сумма, Выражения, предупреждения/флаги)
NORMALIZATION = [
    (("Соколова", "Марина", "Антоновна"), "СОКОЛОВАМАРИНААНТОНОВНА", 95, 5, set()),
    (("Соколова", "Марина", "Антоновны"), "СОКОЛОВАМАРИНААНТОНОВНЫ", 96, 6, OBL),
    (("Соколовой", "Марины", "Антоновны"), "СОКОЛОВОЙМАРИНЫАНТОНОВНЫ", 105, 6, OBL),
    (("Иванова", "Анна", "Юрьевна"), "ИВАНОВААННАЮРЬЕВНА", 69, 6, set()),
    (("Соколов", "Антон", "Юрьевич"), "СОКОЛОВАНТОНЮРЬЕВИЧ", 88, 7, set()),
    (("сОКОЛОВА ", " марина", "антоновна"), "СОКОЛОВАМАРИНААНТОНОВНА", 95, 5, set()),
    (("Семенов", "Петр", "Юрьевич"), "СЕМЕНОВПЕТРЮРЬЕВИЧ", 93, 3, {"yo_possible"}),
    (("Семёнов", "Пётр", "Юрьевич"), "СЕМЁНОВПЁТРЮРЬЕВИЧ", 95, 5, set()),
    (("Римская-Корсакова", "Анна", "Сергеевна"), "РИМСКАЯКОРСАКОВААННАСЕРГЕЕВНА", 117, 9, set()),
    (("Римская Корсакова", "Анна", "Сергеевна"), "РИМСКАЯКОРСАКОВААННАСЕРГЕЕВНА", 117, 9, set()),
    (("Ким", "Виктория", None), "КИМВИКТОРИЯ", 41, 5, {"no_patronymic"}),
    (("Мамедов", "Али", "Гасан оглы"), "МАМЕДОВАЛИГАСАНОГЛЫ", 68, 5, set()),
    (("Подъячева", "Наталья", "Игоревна"), "ПОДЪЯЧЕВАНАТАЛЬЯИГОРЕВНА", 104, 5, set()),
]


@pytest.mark.parametrize("inp,working,total,expr,marks", NORMALIZATION, ids=lambda x: str(x)[:30])
def test_normalization_examples_1_5(inp, working, total, expr, marks):
    n = num.normalize(_name(*inp))
    assert n.working == working
    r = num.name_numbers(n)
    assert r.sums.all == total
    assert r.expression.value == expr
    assert set(n.warnings) | set(n.flags) == marks


@pytest.mark.parametrize(
    "inp,code,field,pos",
    [
        (("Sokolova", "Marina", None), "latin_not_supported", "surname", None),
        (("Сокол" + "o" + "ва", "Марина", None), "mixed_script", "surname", 6),
        (("Ковальчук", "Олена", "Іванівна"), "unsupported_letter", "patronymic", 1),
        (("Иванов", "Иван2", None), "invalid_character", "given", 5),
        (("Иванов", "", None), "empty_name_part", "given", None),
    ],
)
def test_fail_closed_input_errors(inp, code, field, pos):
    with pytest.raises(num.NumerologyInputError) as e:
        num.normalize(_name(*inp))
    assert (e.value.code, e.value.field, e.value.position) == (code, field, pos)


def test_nfc_composes_short_i_and_yo():
    # «и» + кратка → «й», «е» + диерезис → «ё» (§1.2 шаг 1)
    n = num.normalize(_name("Сергей", "Пётр", None))
    assert n.working == "СЕРГЕЙПЁТР"


def test_dashes_apostrophe_dot_removed():
    n = num.normalize(_name("Д’Артаньян—Ли.", "Анна", None))
    assert n.working == "ДАРТАНЬЯНЛИАННА"


def test_gender_form_mismatch_warning():
    n = num.normalize(_name("Соколова", "Марина", "Антонович"))
    assert "gender_form_mismatch" in n.warnings


def test_letter_table_control_points_2():
    v = num.LETTER_VALUES
    assert len(v) == 33
    assert (v["Ъ"], v["Ь"], v["Й"], v["Е"], v["Ё"], v["И"], v["Я"]) == (1, 3, 2, 6, 7, 1, 6)
    assert set("АЕЁИОУЫЭЮЯ") == num.VOWELS


@pytest.mark.parametrize(
    "n,free,digit",
    [(4, [4], [4]), (17, [17, 8], [17, 8]), (29, [29, 11], [29, 11, 2]), (22, [22], [22, 4]),
     (19, [19, 10, 1], [19, 10, 1]), (31, [31, 4], [31, 4]), (33, [33, 6], [33, 6]),
     (38, [38, 11], [38, 11, 2])],
)
def test_reduce_chains_3_1(n, free, digit):
    assert num.reduce_free(n) == free
    assert num.reduce_digit(n) == digit


@pytest.mark.parametrize(
    "d,total,lp", [("17.03.1986", 35, 8), ("11.04.1976", 29, 11), ("22.04.1978", 33, 6),
                   ("11.06.1976", 31, 4)]
)
def test_life_path_examples_4_2(d, total, lp):
    r = num.calculate(birth_date=d)
    assert r["LIFE_PATH"].value == lp
    assert r["LIFE_PATH"].detail["chain"][0] == total


def test_free_and_master_flags_on_final_only_3_4():
    r = num.name_numbers(num.normalize(_name("Куликов", "Роман", "Николаевич")))
    assert r.heart.value == 8 and r.heart.detail["is_free"] and not r.heart.detail["is_master"]
    assert r.persona.value == 11 and r.persona.detail["is_master"]
    assert not r.expression.detail["is_free"]  # 91 → 10 → 1


def test_results_carry_rule_versions_0_2():
    r = num.calculate(birth_date="17.03.1986", name_birth=_name("Ким", "Виктория"))
    for key in ("LIFE_PATH", "BIRTHDAY", "EXPRESSION", "HEART", "PERSONA", "PSYCHOMATRIX"):
        assert r[key].rule.id.startswith("num.")
        assert r[key].rule.version.startswith("0.")
    assert r.meta == {
        "letter_table_id": "balliett_ru_33/1",
        "vowel_set_id": "ru_10/1",
        "normalization_version": "norm/1",
    }


def test_maturity_needs_name():
    r = num.calculate(birth_date="17.03.1986")
    assert r["MATURITY"].value is None


def test_calc_date_before_birth_is_rejected():
    with pytest.raises(num.NumerologyInputError) as e:
        num.calculate(birth_date="17.03.1986", calc_date="01.01.1980")
    assert e.value.code == "date_out_of_range"


# ── property-тесты (seed фиксирован) ─────────────────────────────────────────

RNG = random.Random(20261121)
LETTERS = "".join(num.LETTER_VALUES)


def _random_name():
    def word():
        return "".join(RNG.choice(LETTERS) for _ in range(RNG.randint(1, 14)))

    return _name(word(), word(), word() if RNG.random() < 0.8 else None)


def test_property_vowels_plus_consonants_equal_total():
    for _ in range(2000):
        r = num.name_numbers(num.normalize(_random_name()))
        assert r.sums.vowels + r.sums.consonants == r.sums.all


def test_property_reduce_free_stops_only_on_11_22():
    for n in range(1, 2000):
        chain = num.reduce_free(n)
        assert chain[-1] <= 9 or chain[-1] in (11, 22)
        assert all(x > 9 and x not in (11, 22) for x in chain[:-1])


def test_property_classic_dates_give_nine_cells():
    d, end = date(1900, 1, 1), date(1999, 12, 31)
    while d <= end:
        r = num.calculate(birth_date=d.strftime("%d.%m.%Y"))
        cells = r["CELLS"].value
        assert len(cells) == 9 and all(c >= 0 for c in cells)
        assert r["WORK"].value[2] > 0
        d += timedelta(days=RNG.randint(1, 9))
