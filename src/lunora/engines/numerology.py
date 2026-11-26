"""Нумерологический движок (NUMEROLOGY-RULES.md, G17-S2a).

Два контура, которые в расчётах не смешиваются (§0.1):
  - **имя** — метод Баллиетт (1908) на русском алфавите: числа Выражения, Сердца, Облика;
  - **дата** — квадрат Пифагора по методу Александрова и числа даты западной традиции.

Fail closed (§0.2): вход, который нельзя посчитать однозначно, даёт `NumerologyInputError`
с кодом; мягкие проверки (§1.4) — предупреждения, а не исправления. Квадрат для дат с
01.01.2000 не выдаётся (`rule_not_formalized`, решение Антона №2 2026-11-21, ENGINE-SPEC
§8.4). Проверка «кармический долг» — вне v1 (§4.3). Влияние линий (§5.5) и переходы (§7.2)
считаются как пометки поверх базового квадрата и его не меняют.

Тексты значений (охраняемые формулировки Александрова) сюда не входят — только арифметика.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from lunora.engines.result import Result, Rule

RULES_VERSION = "0.1.0"  # 0.x — до подписи практика (ENGINE-SPEC §1.3)
META = {
    "letter_table_id": "balliett_ru_33/1",
    "vowel_set_id": "ru_10/1",
    "normalization_version": "norm/1",
}


def _rule(name: str) -> Rule:
    return Rule(f"num.{name.lower()}", RULES_VERSION)


# ── §2 таблица букв ──────────────────────────────────────────────────────────
ALPHABET = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
LETTER_VALUES: dict[str, int] = {c: (i % 9) + 1 for i, c in enumerate(ALPHABET)}
VOWELS = frozenset("АЕЁИОУЫЭЮЯ")  # Й, Ъ, Ь — «остальные» (§2, решение П-1 до практика)

# §1.2 шаг 4: разделители без числового значения
_SEPARATORS = frozenset(
    " \t -‐‑‒–—―−'’ʼ`‘."
)

# §1.4 мягкие проверки
_OBLIQUE_PATRONYMIC = (
    "ИНИЧНЫ", "ОВНЫ", "ЕВНЫ", "ИЧНЫ", "ОВНЕ", "ЕВНЕ", "ОВНУ", "ЕВНУ", "ОВНОЙ", "ЕВНОЙ",
    "ОВИЧА", "ЕВИЧА", "ИЧА", "ОВИЧУ", "ЕВИЧУ", "ОВИЧЕМ", "ЕВИЧЕМ",
)
_OBLIQUE_SURNAME = ("ОВОЙ", "ЕВОЙ", "ИНОЙ", "СКОЙ", "ОВУ", "ЕВУ", "ИНУ")
_OBLIQUE_GIVEN = ("Ы", "И")
_MALE_PATRONYMIC = ("ОВИЧ", "ЕВИЧ", "ИЧ")
_FEMALE_PATRONYMIC = ("ВНА", "ЧНА")
_FEMALE_SURNAME = ("ОВА", "ЕВА", "ИНА", "СКАЯ")
_MALE_SURNAME = ("ОВ", "ЕВ", "ИН", "СКИЙ")
# Справочник содержания, не часть правил (§1.4, П-7): минимальный список из примеров спеки.
_YO_WORDS = frozenset(
    {"ПЁТР", "СЕМЁН", "ФЁДОР", "АЛЁНА", "АРТЁМ", "СОЛОВЬЁВ", "СЕМЁНОВ"}
)
_YO_AS_E = frozenset(w.replace("Ё", "Е") for w in _YO_WORDS)

FREE_NUMBERS = frozenset({8, 9, 11, 22})
MASTER_NUMBERS = frozenset({11, 22})


class NumerologyInputError(ValueError):
    """Отказ движка (fail closed): вход нельзя посчитать однозначно."""

    def __init__(self, code: str, field: str | None = None, position: int | None = None):
        self.code, self.field, self.position = code, field, position
        where = f" в поле {field}" if field else ""
        at = f", позиция {position}" if position else ""
        super().__init__(f"{code}{where}{at}")


@dataclass(frozen=True, slots=True)
class FullName:
    """ФИО при рождении, как в первом свидетельстве, именительный падеж (§1.1)."""

    surname: str
    given: str
    patronymic: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedName:
    surname: str
    given: str
    patronymic: str
    working: str
    flags: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


# ── §3.1 свёртка ─────────────────────────────────────────────────────────────


def _digit_sum(n: int) -> int:
    return sum(int(c) for c in str(abs(n)))


def reduce_free(n: int) -> list[int]:
    """Цепочка свёртки с остановкой на 11 и 22 (§3.1, §7.1). 33 → 6."""
    chain = [n]
    while n > 9 and n not in MASTER_NUMBERS:
        n = _digit_sum(n)
        chain.append(n)
    return chain


def reduce_digit(n: int) -> list[int]:
    """Полная свёртка до одной цифры (§3.1)."""
    chain = [n]
    while n > 9:
        n = _digit_sum(n)
        chain.append(n)
    return chain


def _number(name: str, raw: int, *, free: bool = True) -> Result:
    chain = reduce_free(raw) if free else reduce_digit(raw)
    final = chain[-1]
    return Result.computed(
        _rule(name),
        final,
        chain=chain,
        is_free=final in FREE_NUMBERS,
        is_master=final in MASTER_NUMBERS,
    )


# ── §1.2–1.4 нормализация ФИО ────────────────────────────────────────────────


def _is_latin(ch: str) -> bool:
    return ch.isalpha() and "LATIN" in unicodedata.name(ch, "")


def _is_cyrillic(ch: str) -> bool:
    return ch.isalpha() and "CYRILLIC" in unicodedata.name(ch, "")


def _normalize_field(raw: str | None, field_name: str) -> str:
    text = unicodedata.normalize("NFC", raw or "").strip().upper()
    letters = [c for c in text if c not in _SEPARATORS]
    if letters and all(_is_latin(c) for c in letters):
        raise NumerologyInputError("latin_not_supported", field_name)
    for pos, ch in enumerate(text, start=1):
        if ch in _SEPARATORS or ch in LETTER_VALUES:
            continue
        if _is_latin(ch):
            raise NumerologyInputError("mixed_script", field_name, pos)
        if _is_cyrillic(ch):
            raise NumerologyInputError("unsupported_letter", field_name, pos)
        raise NumerologyInputError("invalid_character", field_name, pos)
    return "".join(letters)


def _soft_checks(s: str, g: str, p: str) -> list[str]:
    warnings = []
    oblique = (p and p.endswith(_OBLIQUE_PATRONYMIC)) or (
        s.endswith(_OBLIQUE_SURNAME) and g.endswith(_OBLIQUE_GIVEN)
    )
    if oblique:
        warnings.append("oblique_case_suspected")
    if any(w in _YO_AS_E and "Е" in w for w in (s, g, p)):
        warnings.append("yo_possible")
    male_p, female_p = p.endswith(_MALE_PATRONYMIC), p.endswith(_FEMALE_PATRONYMIC)
    if (male_p and s.endswith(_FEMALE_SURNAME)) or (female_p and s.endswith(_MALE_SURNAME)):
        warnings.append("gender_form_mismatch")
    return warnings


def normalize(name: FullName) -> NormalizedName:
    """Нормализация `norm/1` (§1.2): NFC, края, регистр, разделители, алфавит, длина."""
    s = _normalize_field(name.surname, "surname")
    g = _normalize_field(name.given, "given")
    p = _normalize_field(name.patronymic, "patronymic")
    for value, field_name in ((s, "surname"), (g, "given")):
        if not value:
            raise NumerologyInputError("empty_name_part", field_name)
    flags = () if p else ("no_patronymic",)
    return NormalizedName(s, g, p, s + g + p, flags, tuple(_soft_checks(s, g, p)))


# ── §3 числа имени ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class NameSums:
    all: int
    vowels: int
    consonants: int


@dataclass(frozen=True, slots=True)
class NameNumbers:
    sums: NameSums
    expression: Result
    heart: Result
    persona: Result


def _name_number(key: str, raw: int, empty_code: str | None = None) -> Result:
    if raw == 0 and empty_code:
        # §3.3 вырожденный случай: ноль числом имени не является (fail closed, F09)
        return Result.missing(_rule(key), empty_code)
    return _number(key, raw)


def name_numbers(n: NormalizedName) -> NameNumbers:
    """Выражения, Сердца, Облика — сплошь по рабочей строке (§3.2, §3.3)."""
    total = sum(LETTER_VALUES[c] for c in n.working)
    vowels = sum(LETTER_VALUES[c] for c in n.working if c in VOWELS)
    sums = NameSums(total, vowels, total - vowels)
    return NameNumbers(
        sums=sums,
        expression=_name_number("EXPRESSION", total),
        heart=_name_number("HEART", vowels, "no_vowels"),
        persona=_name_number("PERSONA", sums.consonants, "no_consonants"),
    )


# ── §4–5 дата ────────────────────────────────────────────────────────────────

_MIN_DATE = date(1900, 1, 1)
_POST2000 = date(2000, 1, 1)
LINES: dict[str, tuple[int, int, int]] = {  # канонический порядок §5.4
    "LINE_ROW_1": (1, 4, 7),
    "LINE_ROW_2": (2, 5, 8),
    "LINE_ROW_3": (3, 6, 9),
    "LINE_COL_1": (1, 2, 3),
    "LINE_COL_2": (4, 5, 6),
    "LINE_COL_3": (7, 8, 9),
    "LINE_DIAG_UP": (3, 5, 7),
    "LINE_DIAG_DOWN": (1, 5, 9),
}
_LEVELS = ("ABSENT", "WEAK", "NORM", "IMPULSE", "STRONG", "PEAK")


def level(count: int) -> str:
    """Семиуровневая шкала §5.6 (не линейна, уровни не сравниваются как числа)."""
    return _LEVELS[count] if count < 6 else "OVERLOAD"


def parse_date(value: str | date | None, *, field_name: str = "birth_date") -> date:
    if isinstance(value, date):
        return value
    try:
        dd, mm, yyyy = (int(x) for x in str(value).strip().split("."))
        return date(yyyy, mm, dd)
    except (ValueError, TypeError) as exc:
        raise NumerologyInputError("invalid_date", field_name) from exc


def _work_numbers(d: date) -> list[int]:
    digits = f"{d.day:02d}{d.month:02d}{d.year:04d}"
    w1 = sum(int(c) for c in digits)
    w2 = _digit_sum(w1)
    f = int(next(c for c in f"{d.day:02d}" if c != "0"))  # первая ненулевая цифра дня
    w3 = w1 - 2 * f
    if w3 <= 0:
        raise NumerologyInputError("work3_non_positive", "birth_date")
    return [w1, w2, w3, _digit_sum(w3)]


def _influence(cells: list[int], strength: Mapping[str, int]) -> dict[str, Any]:
    """Влияние линий §5.5 — пометки поверх базового квадрата, один проход без итераций."""
    n = {k: cells[k - 1] for k in range(1, 10)}
    dominant = [line for line, s in strength.items() if s >= 5]
    captured: dict[int, str] = {}
    for k in range(1, 10):
        through = [line for line in dominant if k in LINES[line]]
        if n[k] >= 2 and through:
            best = max(strength[line] for line in through)
            captured[k] = next(line for line in through if strength[line] == best)
    effective: dict[str, int] = {}
    weakened: dict[str, list[tuple[str, int]]] = {}
    for k, owner in captured.items():
        for line, ks in LINES.items():
            if line != owner and k in ks:
                effective[line] = effective.get(line, strength[line]) - n[k]
                weakened.setdefault(line, []).append((owner, k))
    effective = {line: max(0, s) for line, s in effective.items()}
    boosted: dict[int, list[str]] = {}
    for line in dominant:
        if strength[line] == 5:
            for k in LINES[line]:
                if n[k] <= 1:
                    boosted.setdefault(k, []).append(line)
    return {
        "dominant": dominant,
        "captured": captured,
        "weakened": weakened,
        "effective": effective,
        "boosted": boosted,
    }


def _transitions(cells: list[int]) -> dict[str, dict[str, int]]:
    """Доступные прямые переходы §7.2 — один шаг, базовый квадрат не меняется."""
    n = {k: cells[k - 1] for k in range(1, 10)}
    out: dict[str, dict[str, int]] = {}
    if n[2] >= 2:
        out["TRANSITION_22_TO_4"] = {"2": n[2] - 2, "4": n[4] + 1}
    if n[8] >= 1:
        out["TRANSITION_8_TO_11"] = {"8": n[8] - 1, "1": n[1] + 2}
    if n[6] >= 1:
        out["TRANSITION_6_TO_7"] = {"6": n[6] - 1, "7": n[7] + 1}
    return out


_SQUARE_KEYS = ("WORK", "CELLS", "LINES", "LEVELS", "INFLUENCE", "TRANSITIONS")


def _psychomatrix(d: date) -> dict[str, Result]:
    if d >= _POST2000:
        reason = "rule_not_formalized"  # §5.2, П-5: fail closed до сверки со стр. 51
        out = {"PSYCHOMATRIX": Result.missing(_rule("PSYCHOMATRIX"), reason, era="post2000")}
        out.update({k: Result.missing(_rule(k), reason) for k in _SQUARE_KEYS})
        return out
    work = _work_numbers(d)
    row = f"{d.day:02d}{d.month:02d}{d.year:04d}" + "".join(str(w) for w in work)
    cells = [row.count(str(k)) for k in range(1, 10)]
    strength = {line: sum(cells[k - 1] for k in ks) for line, ks in LINES.items()}
    levels = {f"CELL_{k}": level(cells[k - 1]) for k in range(1, 10)}
    levels |= {line: level(s) for line, s in strength.items()}
    return {
        "PSYCHOMATRIX": Result.computed(_rule("PSYCHOMATRIX"), "classic", era="classic"),
        "WORK": Result.computed(_rule("WORK"), work, digit_row=row),
        "CELLS": Result.computed(_rule("CELLS"), cells),
        "LINES": Result.computed(_rule("LINES"), strength),
        "LEVELS": Result.computed(_rule("LEVELS"), levels),
        "INFLUENCE": Result.computed(_rule("INFLUENCE"), _influence(cells, strength)),
        "TRANSITIONS": Result.computed(_rule("TRANSITIONS"), _transitions(cells)),
    }


def _date_numbers(d: date) -> dict[str, Result]:
    digits = f"{d.day:02d}{d.month:02d}{d.year:04d}"
    life_path = _number("LIFE_PATH", sum(int(c) for c in digits))
    m = reduce_digit(d.month)[-1]
    dd = reduce_digit(d.day)[-1]
    y = reduce_digit(_digit_sum(d.year))[-1]
    lp = reduce_digit(life_path.value)[-1]
    p1, p2, p4 = reduce_free(m + dd), reduce_free(dd + y), reduce_free(m + y)
    p3 = reduce_free(reduce_digit(p1[-1])[-1] + reduce_digit(p2[-1])[-1])
    c1, c2, c4 = abs(m - dd), abs(dd - y), abs(m - y)
    ends = [d.year + 36 - lp, d.year + 45 - lp, d.year + 54 - lp]
    out = {
        "BIRTHDAY": _number("BIRTHDAY", d.day),
        "LIFE_PATH": life_path,
        "PERIODS": Result.computed(_rule("PERIODS"), ends, components={"m": m, "d": dd, "y": y,
                                                                         "lp": lp}),
        "KARMIC_DEBT_CHECK": Result.missing(_rule("KARMIC_DEBT_CHECK"), "out_of_v1"),
    }
    for i, chain in enumerate((p1, p2, p3, p4), start=1):
        out[f"PINNACLE_{i}"] = Result.computed(
            _rule(f"PINNACLE_{i}"), chain[-1], chain=chain, is_master=chain[-1] in MASTER_NUMBERS
        )
    for i, c in enumerate((c1, c2, abs(c1 - c2), c4), start=1):
        out[f"CHALLENGE_{i}"] = Result.computed(_rule(f"CHALLENGE_{i}"), c)
    return out


def _personal_cycles(birth: date, calc: date) -> dict[str, Result]:
    raw = _digit_sum(birth.day) + _digit_sum(birth.month) + _digit_sum(calc.year)
    year = reduce_digit(raw)
    month = reduce_digit(year[-1] + calc.month)
    day = reduce_digit(month[-1] + calc.day)
    return {
        "PERSONAL_YEAR": Result.computed(_rule("PERSONAL_YEAR"), year[-1], chain=year),
        "PERSONAL_MONTH": Result.computed(_rule("PERSONAL_MONTH"), month[-1], chain=month),
        "PERSONAL_DAY": Result.computed(_rule("PERSONAL_DAY"), day[-1], chain=day),
    }


# ── сборка §7.3 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NumerologyResult(Mapping[str, Result]):
    """Величины по enum-ключам §6 + служебные (`WORK`, `CELLS`, …); `meta` — версии §0.2."""

    values: dict[str, Result]
    name: NormalizedName | None = None
    name_sums: NameSums | None = None
    meta: dict[str, str] = field(default_factory=lambda: dict(META))

    def __getitem__(self, key: str) -> Result:
        return self.values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)


def calculate(
    birth_date: str | date | None = None,
    name_birth: FullName | None = None,
    calc_date: str | date | None = None,
    name_current: FullName | None = None,
) -> NumerologyResult:
    """Полный расчёт по §7.3. Дата — «ДД.ММ.ГГГГ» или `date`; «сегодня» приходит параметром."""
    values: dict[str, Result] = {}
    norm = sums = None
    if birth_date is not None:
        d = parse_date(birth_date)
        if d < _MIN_DATE:
            raise NumerologyInputError("date_out_of_range", "birth_date")
        if calc_date is not None:
            c = parse_date(calc_date, field_name="calc_date")
            if c < d:
                raise NumerologyInputError("date_out_of_range", "calc_date")
            values |= _personal_cycles(d, c)
        values |= _psychomatrix(d)
        values |= _date_numbers(d)
    if name_birth is not None:
        norm = normalize(name_birth)
        nn = name_numbers(norm)
        sums = nn.sums
        values |= {"EXPRESSION": nn.expression, "HEART": nn.heart, "PERSONA": nn.persona}
        if name_current is not None:
            values |= _name_change(norm, name_current)
    if "LIFE_PATH" in values:
        expr = values.get("EXPRESSION")
        if expr is not None and expr.is_computed:
            # §4.3: складываются итоговые значения, мастер-числа как есть
            values["MATURITY"] = _number("MATURITY", values["LIFE_PATH"].value + expr.value)
        else:
            # §4.3: число зрелости требует ФИО; без него — непосчитано (F09, не null)
            values["MATURITY"] = Result.missing(_rule("MATURITY"), "no_name")
    return NumerologyResult(values=values, name=norm, name_sums=sums)


def _name_change(birth: NormalizedName, current: FullName) -> dict[str, Result]:
    """Второй набор чисел имени по `name_current` и дельта «при рождении → сейчас» (§3.5).

    Движок не выводит «лучше/хуже» (§8): только пара значений по каждому из трёх чисел и
    признак «изменилось/нет». Если после нормализации текущее ФИО совпало с ФИО при рождении —
    дельта не строится (`name_equals_current`).
    """
    cur = normalize(current)
    cur_nn = name_numbers(cur)
    out: dict[str, Result] = {
        "EXPRESSION_CURRENT": cur_nn.expression,
        "HEART_CURRENT": cur_nn.heart,
        "PERSONA_CURRENT": cur_nn.persona,
    }
    if cur.working == birth.working:
        out["NAME_CHANGE"] = Result.missing(
            _rule("NAME_CHANGE"), "out_of_v1", flag="name_equals_current"
        )
        return out
    birth_nn = name_numbers(birth)
    delta: dict[str, Any] = {}
    for key, b, c in (
        ("EXPRESSION", birth_nn.expression, cur_nn.expression),
        ("HEART", birth_nn.heart, cur_nn.heart),
        ("PERSONA", birth_nn.persona, cur_nn.persona),
    ):
        bv = b.value if b.is_computed else None
        cv = c.value if c.is_computed else None
        delta[key] = {"birth": bv, "current": cv, "changed": bv != cv}
    out["NAME_CHANGE"] = Result.computed(
        _rule("NAME_CHANGE"), delta, changed=any(d["changed"] for d in delta.values())
    )
    return out


def snapshot(r: NumerologyResult) -> dict[str, Any]:
    """Плоская раскладка результата по путям golden-кейсов."""
    out: dict[str, Any] = {}
    for key, res in r.items():
        if res.not_computed:
            out[f"{key}.not_computed"] = res.not_computed
            continue
        out[key] = res.value
        for k in ("chain", "is_free", "is_master"):
            if k in res.detail:
                out[f"{key}.{k}"] = res.detail[k]
    if "PINNACLE_1" in r:
        out["PINNACLES"] = [r[f"PINNACLE_{i}"].value for i in range(1, 5)]
        out["CHALLENGES"] = [r[f"CHALLENGE_{i}"].value for i in range(1, 5)]
        out["PERIODS.ends"] = r["PERIODS"].value
    if "LEVELS" in r and r["LEVELS"].is_computed:
        out |= {f"LEVELS.{k}": v for k, v in r["LEVELS"].value.items()}
        inf = r["INFLUENCE"].value
        out |= {f"INFLUENCE.{k}": inf[k] for k in ("dominant", "captured", "effective")}
        out["INFLUENCE.boosted"] = inf["boosted"]
    if r.name is not None:
        out["name.working"] = r.name.working
        out["name.flags"] = sorted(r.name.flags)
        out["name.warnings"] = sorted(r.name.warnings)
        out["name.sum.all"] = r.name_sums.all
        out["name.sum.vowels"] = r.name_sums.vowels
        out["name.sum.consonants"] = r.name_sums.consonants
    return out
