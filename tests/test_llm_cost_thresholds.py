"""Гард дрейфа порогов LLM: `scripts/spike/llm_cost_thresholds.json` ↔ документы-источники.

Контракт задачи: `docs/current/tasks/S3b-02.md`.

Источники (перечислены в самом JSON в поле `source`):
  * `docs/grillmax/05_business.md` §3.1 — вариант А (Haiku 4.5), §3.5 — вариант Б (топовая модель);
  * `docs/current/G17-S1-план.md` § «Замер стоимости LLM» — сводка порогов.

Что делает тест:
  * сверяет каждый порог с тем, как он записан в документе, — численно, а не строкой
    («10 000» → 10000, «3,01» → 3.01, «0,4» → 0.4, «≈ 10 ₽» → 10);
  * `null` трактует как «не пересчитано»: в документе должно стоять «не пересчитан»
    и не должно быть числа; `null` — это не 0 и не «порога нет»;
  * проверяет, что ни один порог из JSON не остался без опоры в документах.

Чего тест не делает: не правит дрейф и не подгоняет пороги под документ — он только
краснеет. Ни JSON, ни документы он не меняет.

Разбор чисел — только стандартная библиотека.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Callable
from dataclasses import dataclass

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
THRESHOLDS_PATH = ROOT / "scripts" / "spike" / "llm_cost_thresholds.json"
BUSINESS_PATH = ROOT / "docs" / "grillmax" / "05_business.md"
PLAN_PATH = ROOT / "docs" / "current" / "G17-S1-план.md"

# Число в тексте документа: «10 000», «3,01», «0,4», «10000».
# Перед цифрой не может стоять буква, дефис или подчёркивание — иначе «R-05» прочиталось бы как 5.
_NUMBER_RE = re.compile(
    r"(?<![\w\-])\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?"
    r"|(?<![\w\-])\d+(?:[.,]\d+)?"
)
_NOT_RECALCULATED = "не пересчит"
_INHERITED = "то же"


# --- разбор документов ------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(text: str, title: str) -> str:
    """Раздел markdown по заголовку (без решёток).

    Идёт до следующего заголовка того же или более высокого уровня.
    """
    lines = text.splitlines()
    start = None
    level = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        hashes = len(stripped) - len(stripped.lstrip("#"))
        if stripped[hashes:].strip().startswith(title):
            start, level = index, hashes
            break
    if start is None:
        raise AssertionError(f"заголовок {title!r} не найден")
    block = [lines[start]]
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            if hashes <= level:
                break
        block.append(line)
    return "\n".join(block)


def _tables(text: str) -> list[list[list[str]]]:
    """Markdown-таблицы: список таблиц, каждая — список строк, каждая — список ячеек."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if cells and all(cell and set(cell) <= set("-: ") for cell in cells):
                continue  # строка-разделитель заголовка
            current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _table(text: str, *header_markers: str) -> tuple[list[str], list[list[str]]]:
    """Заголовок и тело таблицы, найденной по маркерам в строке заголовка."""
    for rows in _tables(text):
        if rows and all(any(marker in cell for cell in rows[0]) for marker in header_markers):
            return rows[0], rows[1:]
    raise AssertionError(f"таблица с заголовком {header_markers!r} не найдена")


def _row(body: list[list[str]], marker: str) -> list[str]:
    for row in body:
        if any(marker in cell for cell in row):
            return row
    raise AssertionError(f"строка {marker!r} не найдена")


def _column_index(header: list[str], marker: str) -> int:
    for index, cell in enumerate(header):
        if marker in cell:
            return index
    raise AssertionError(f"колонка {marker!r} не найдена")


def _cell(header: list[str], body: list[list[str]], row_marker: str, column_marker: str) -> str:
    row = _row(body, row_marker)
    index = _column_index(header, column_marker)
    if index >= len(row):
        raise AssertionError(f"в строке {row_marker!r} нет колонки {column_marker!r}")
    return row[index]


def _sentence_with(text: str, marker: str) -> str:
    """Предложение текста, в котором встретился маркер."""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if marker in sentence:
            return sentence
    raise AssertionError(f"в тексте нет предложения с {marker!r}")


def _numbers(text: str) -> list[float]:
    """Числа текста: «10 000» → 10000, «3,01» → 3.01, «0,4» → 0.4, «≈ 10 ₽» → 10."""
    found: list[float] = []
    for match in _NUMBER_RE.finditer(text):
        raw = re.sub(r"[\s\u00a0\u202f]+", "", match.group(0))
        found.append(float(raw.replace(",", ".")))
    return found


# --- вырезки из источников --------------------------------------------------------


def _business_section(title: str) -> str:
    return _section(_read(BUSINESS_PATH), title)


def _business_cell(
    title: str, header_markers: tuple[str, ...], row_marker: str, column_marker: str
) -> str:
    header, body = _table(_business_section(title), *header_markers)
    return _cell(header, body, row_marker, column_marker)


def _plan_section() -> str:
    return _section(_read(PLAN_PATH), "Замер стоимости LLM")


def _plan_cell(row_marker: str, column_marker: str) -> str:
    header, body = _table(_plan_section(), "Сценарий")
    return _cell(header, body, row_marker, column_marker)


def _plan_dialog_parts(variant: str) -> tuple[str, str]:
    """Кусок про сутки и кусок про вопрос из строки «Вопрос в диалоге» сводки.

    Вариант А: «сутки из 25 вопросов ≈ 10 ₽ (≈ 0,4 ₽ за вопрос)» →
      сутки — «сутки из 25 вопросов ≈ 10 ₽», вопрос — «≈ 0,4 ₽ за вопрос».
    Вариант Б: «≤ 3,01 ₽ за вопрос; ≤ 75 ₽ за сутки» →
      вопрос — «≤ 3,01 ₽ за вопрос», сутки — «≤ 75 ₽ за сутки».
    """
    # В сводке варианты подписаны кириллицей: «вариант А», «вариант Б».
    letter = {"A": "А", "B": "Б"}[variant]
    cell = _plan_cell("Вопрос в диалоге", f"вариант {letter}")
    parts = [part.strip() for part in cell.split(";")]
    question = next((part for part in parts if "за вопрос" in part), None)
    day = next((part for part in parts if "за сутки" in part), None)
    if question is None or day is None:
        # Вариант А: сутки и вопрос записаны одной фразой, вопрос — в скобках.
        head, _, tail = cell.partition("(")
        day, question = head.strip(), tail.rstrip(") ").strip()
    return day, question


# --- модель гарда -----------------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    """Опора гарда: кусок документа, где записан порог.

    kind:
      * ``stated`` — порог записан числом; значение обязано совпасть с JSON;
      * ``recalculated`` — порог не пересчитан: в куске нет «не пересчитан» и нет числа;
      * ``inherited`` — порог унаследован («то же»);
      * ``absent`` — в куске не должно быть marker'а (в разделе не пересчитали).
    """

    label: str
    kind: str
    extract: Callable[[], str]
    marker: str = ""


@dataclass(frozen=True)
class Threshold:
    """Порог из JSON и его опоры в документах-источниках.

    kind:
      * ``number`` — в документе записано число;
      * ``null`` — в документе «не пересчитан», в JSON стоит null;
      * ``inherited`` — в документе «то же», значение наследуется у inherits.
    """

    variant: str
    group: str
    field: str
    kind: str
    anchors: tuple[Anchor, ...]
    inherits: tuple[str, str, str] | None = None


EXPECTATIONS: tuple[Threshold, ...] = (
    Threshold(
        variant="A",
        group="dialog",
        field="max_rub_per_day",
        kind="number",
        anchors=(
            Anchor(
                label="05_business.md §3.1: «Сутки диалога» → «Себестоимость»",
                kind="stated",
                extract=lambda: _business_cell(
                    "3.1 Себестоимость",
                    ("Продукт", "Себестоимость"),
                    "Сутки диалога",
                    "Себестоимость",
                ),
            ),
            Anchor(
                label="сводка G17-S1-план.md: «Вопрос в диалоге», вариант А",
                kind="stated",
                extract=lambda: _plan_dialog_parts("A")[0],
            ),
        ),
    ),
    Threshold(
        variant="A",
        group="dialog",
        field="max_rub_per_question",
        kind="number",
        anchors=(
            # В §3.1 цены вопроса нет: порог 0,4 ₽ записан только в сводке.
            Anchor(
                label="сводка G17-S1-план.md: «Вопрос в диалоге», вариант А",
                kind="stated",
                extract=lambda: _plan_dialog_parts("A")[1],
            ),
        ),
    ),
    Threshold(
        variant="A",
        group="document",
        field="max_rub",
        kind="number",
        anchors=(
            Anchor(
                label="05_business.md §3.1: «Документ» → «Себестоимость»",
                kind="stated",
                extract=lambda: _business_cell(
                    "3.1 Себестоимость",
                    ("Продукт", "Себестоимость"),
                    "Документ",
                    "Себестоимость",
                ),
            ),
            Anchor(
                label="сводка G17-S1-план.md: «Документ-синтез», вариант А",
                kind="stated",
                extract=lambda: _plan_cell("Документ-синтез", "вариант А"),
            ),
        ),
    ),
    Threshold(
        variant="A",
        group="forecast",
        field="max_rub_per_user_month",
        kind="number",
        anchors=(
            Anchor(
                label="05_business.md §3.1: «Бесплатный слой» → «Себестоимость»",
                kind="stated",
                extract=lambda: _business_cell(
                    "3.1 Себестоимость",
                    ("Продукт", "Себестоимость"),
                    "Бесплатный слой на пользователя",
                    "Себестоимость",
                ),
            ),
            Anchor(
                label="сводка G17-S1-план.md: «Утренний прогноз», вариант А",
                kind="stated",
                extract=lambda: _plan_cell("Утренний прогноз", "вариант А"),
            ),
        ),
    ),
    Threshold(
        variant="A",
        group="r05",
        field="max_rub_per_month_5000_mau",
        kind="number",
        anchors=(
            Anchor(
                label="сводка G17-S1-план.md: «Итог R-05», вариант А",
                kind="stated",
                extract=lambda: _plan_cell("Итог R-05", "вариант А"),
            ),
            Anchor(
                label="05_business.md §4: «месячный бюджет»",
                kind="stated",
                extract=lambda: _sentence_with(
                    _business_section("4. Постоянные затраты"), "месячный бюджет"
                ),
            ),
        ),
    ),
    Threshold(
        variant="B",
        group="dialog",
        field="max_rub_per_question",
        kind="number",
        anchors=(
            Anchor(
                label="05_business.md §3.5: «Opus 5» → «₽ за вопрос»",
                kind="stated",
                extract=lambda: _business_cell(
                    "3.5 Пересчёт себестоимости под Opus 5",
                    ("Модель", "₽ за вопрос"),
                    "Opus 5",
                    "₽ за вопрос",
                ),
            ),
            Anchor(
                label="сводка G17-S1-план.md: «Вопрос в диалоге», вариант Б",
                kind="stated",
                extract=lambda: _plan_dialog_parts("B")[1],
            ),
        ),
    ),
    Threshold(
        variant="B",
        group="dialog",
        field="max_rub_per_day",
        kind="number",
        anchors=(
            Anchor(
                label="05_business.md §3.5: «25 (средний)» → «Себестоимость»",
                kind="stated",
                extract=lambda: _business_cell(
                    "3.5 Пересчёт себестоимости под Opus 5",
                    ("Вопросов за сутки", "Себестоимость"),
                    "25 (средний)",
                    "Себестоимость",
                ),
            ),
            Anchor(
                label="сводка G17-S1-план.md: «Вопрос в диалоге», вариант Б",
                kind="stated",
                extract=lambda: _plan_dialog_parts("B")[0],
            ),
        ),
    ),
    Threshold(
        variant="B",
        group="document",
        field="max_rub",
        kind="null",
        anchors=(
            Anchor(
                label="сводка G17-S1-план.md: «Документ-синтез», вариант Б",
                kind="recalculated",
                extract=lambda: _plan_cell("Документ-синтез", "вариант Б"),
            ),
            Anchor(
                label="05_business.md §3.5: нет «документ»",
                kind="absent",
                extract=lambda: _business_section("3.5 Пересчёт себестоимости под Opus 5"),
                marker="документ",
            ),
        ),
    ),
    Threshold(
        variant="B",
        group="forecast",
        field="max_rub_per_user_month",
        kind="inherited",
        inherits=("A", "forecast", "max_rub_per_user_month"),
        anchors=(
            Anchor(
                label="сводка G17-S1-план.md: «Утренний прогноз», вариант Б",
                kind="inherited",
                extract=lambda: _plan_cell("Утренний прогноз", "вариант Б"),
            ),
            Anchor(
                label="05_business.md §3.5: нет «прогноз»",
                kind="absent",
                extract=lambda: _business_section("3.5 Пересчёт себестоимости под Opus 5"),
                marker="прогноз",
            ),
        ),
    ),
    Threshold(
        variant="B",
        group="r05",
        field="max_rub_per_month_5000_mau",
        kind="null",
        anchors=(
            Anchor(
                label="сводка G17-S1-план.md: «Итог R-05», вариант Б",
                kind="recalculated",
                extract=lambda: _plan_cell("Итог R-05", "вариант Б"),
            ),
            Anchor(
                label="05_business.md §3.5: нет «R-05»",
                kind="absent",
                extract=lambda: _business_section("3.5 Пересчёт себестоимости под Opus 5"),
                marker="r-05",
            ),
        ),
    ),
)


# --- helpers проверки --------------------------------------------------------------


def _thresholds() -> dict:
    return json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))


def _json_value(variant: str, group: str, field: str):
    """Значение порога из JSON; KeyError — если порога в файле нет."""
    return _thresholds()["variants"][variant]["thresholds"][group][field]


def _assert_stated(fragment: str, value: float, label: str) -> None:
    """Порог должен совпасть с числом в документе — численно, а не строкой."""
    numbers = _numbers(fragment)
    assert numbers, f"{label}: в куске {fragment!r} нет ни одного числа"
    if len(numbers) == 1:
        assert numbers[0] == value, f"{label}: в документе {numbers[0]}, в порогах {value}"
    else:
        assert value in numbers, f"{label}: в документе {numbers}, в порогах {value}"


def _check_anchor(anchor: Anchor, value) -> None:
    fragment = anchor.extract()
    if anchor.kind == "stated":
        assert value is not None, f"{anchor.label}: в порогах null, а в документе {fragment!r}"
        _assert_stated(fragment, float(value), anchor.label)
    elif anchor.kind == "recalculated":
        assert _NOT_RECALCULATED in fragment.lower(), (
            f"{anchor.label}: в документе нет «не пересчитан»: {fragment!r}"
        )
        assert not _numbers(fragment), (
            f"{anchor.label}: в документе стоит число, "
            f"а порог помечен «не пересчитан»: {fragment!r}"
        )
    elif anchor.kind == "inherited":
        assert _INHERITED in fragment.lower(), (
            f"{anchor.label}: в документе нет «то же»: {fragment!r}"
        )
    elif anchor.kind == "absent":
        assert anchor.marker not in fragment.lower(), (
            f"{anchor.label}: в документе появилось «{anchor.marker}» — порог надо пересчитать"
        )
    else:  # pragma: no cover - защита от опечатки в описании опоры
        raise AssertionError(f"неизвестный вид опоры {anchor.kind!r}")


# --- проверки ----------------------------------------------------------------------


def test_thresholds_file_shape():
    """JSON цел: обе варианта, все группы, значения — числа или null."""
    data = _thresholds()
    assert data["schema_version"] == 1
    assert set(data["variants"]) == {"A", "B"}
    for variant, body in data["variants"].items():
        assert body["thresholds"], f"вариант {variant}: пустые пороги"
        for group, fields in body["thresholds"].items():
            assert fields, f"вариант {variant}, группа {group}: пустые пороги"
            for field, value in fields.items():
                assert value is None or (
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                ), f"порог {variant}.{group}.{field} — не число и не null: {value!r}"


@pytest.mark.parametrize(
    "порог",
    EXPECTATIONS,
    ids=lambda t: f"{t.variant}.{t.group}.{t.field}",
)
def test_threshold_matches_document_sources(порог: Threshold):
    """Каждый порог из JSON совпадает с тем, как он записан в документах-источниках."""
    value = _json_value(порог.variant, порог.group, порог.field)
    inherits_value = None
    if порог.inherits is not None:
        inherits_value = _json_value(*порог.inherits)
    if порог.kind == "null":
        assert value is None, (
            f"{порог.variant}.{порог.group}.{порог.field}: в документе «не пересчичено», "
            f"а в порогах {value!r} (null — это «не пересчитано», а не 0)"
        )
    elif порог.kind == "inherited":
        assert value == inherits_value, (
            f"{порог.variant}.{порог.group}.{порог.field}: в документе «то же», "
            f"в порогах {value!r} против {inherits_value!r} у {порог.inherits}"
        )
    else:
        assert value is not None, f"{порог.variant}.{порог.group}.{порог.field}: порог не задан"
    for anchor in порог.anchors:
        _check_anchor(anchor, value)


def test_every_threshold_in_json_has_an_anchor():
    """Ни один порог из JSON не остался без опоры в документах — гард не молчит."""
    data = _thresholds()
    declared = {
        (variant, group, field)
        for variant, body in data["variants"].items()
        for group, fields in body["thresholds"].items()
        for field in fields
    }
    covered = {(t.variant, t.group, t.field) for t in EXPECTATIONS}
    assert declared - covered == set(), (
        "пороги без опоры в гарде: "
        + ", ".join(f"{v}.{g}.{f}" for v, g, f in sorted(declared - covered))
    )


def test_null_thresholds_are_null_not_zero():
    """null = «не пересчитано»: не 0 и не «порога нет»."""
    data = _thresholds()
    nulls = (("B", "document", "max_rub"), ("B", "r05", "max_rub_per_month_5000_mau"))
    for variant, group, field in nulls:
        assert field in data["variants"][variant]["thresholds"][group], (
            f"{variant}.{group}.{field}: порога нет в JSON, а должен быть null"
        )
        value = _json_value(variant, group, field)
        assert value is None, f"{variant}.{group}.{field}: ожидался null, получено {value!r}"
        assert value != 0, f"{variant}.{group}.{field}: null не должен читаться как 0"


@pytest.mark.parametrize(
    ("текст", "ожидаемое"),
    [
        ("10 000", 10000.0),
        ("10 000 ₽ в месяц", 10000.0),
        ("1 490", 1490.0),
        ("10000", 10000.0),
        ("3,01", 3.01),
        ("0,4", 0.4),
        ("≈ 10 ₽", 10.0),
        ("**~10 ₽**", 10.0),
        ("**~1 ₽/мес**", 1.0),
        ("**3,01**", 3.01),
        ("≤ 3,01 ₽ за вопрос", 3.01),
        ("75 ₽", 75.0),
    ],
)
def test_number_formats_are_read_numerically(текст: str, ожидаемое: float):
    """Допустимые форматы записи числа читаются численно — ложной тревоги быть не должно."""
    assert _numbers(текст) == [ожидаемое]


def test_same_value_in_different_formats_is_equal():
    """«10 000», «10000» и «≈ 10 000 ₽» — одно и то же число."""
    assert _numbers("10 000")[0] == _numbers("10000")[0] == _numbers("≈ 10 000 ₽")[0]


def test_risk_id_is_not_read_as_a_number():
    """«R-05» — идентификатор риска, а не число."""
    assert _numbers("R-05 на топовую модель не пересчитан") == []
