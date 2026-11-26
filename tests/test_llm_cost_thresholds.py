"""Гард дрейфа порогов LLM: `scripts/spike/llm_cost_thresholds.json` ↔ документы-источники.

Контракт задачи: `docs/current/tasks/S3b-10.md` (гард S3b-02 доведён после ревью).

Источники (объявлены в самом JSON в полях `source`; сверка — в тесте о provenance):
  * `docs/grillmax/05_business.md` §3.1 — вариант А (Haiku 4.5), §3.5 — вариант Б (топовая модель),
    §4 — постоянные затраты: месячный бюджет проекта, он же порог R-05 варианта А. Канон
    величины — `docs/grillmax/01_context.md` §4.3; сам §4.3 гард не читает: JSON объявляет
    два источника, и третий прочитанный файл развёл бы объявление с реально охраняемым;
  * `docs/current/G17-S1-план.md` § «Замер стоимости LLM» — сводка порогов.

Что делает тест:
  * сверяет каждый порог с тем, как он записан в документе, — численно, а не строкой;
  * ожидаемое значение ВЫЧИСЛЯЕТСЯ из документа, а не хранится в тесте: согласованная правка
    документа и JSON (в том числе переход `null` → число) оставляет гард зелёным, а рассинхрон
    роняет его в обе стороны;
  * `null` означает «не пересчитано» — ровно то, что говорит документ, и никаких чисел рядом;
  * проверяет provenance: объявленные в JSON `source` и `note` не устарели и совпадают с тем,
    что гард реально читает.

Принимаемые форматы записи чисел (разбор — свой, на стандартной библиотеке):
  * «10 000», «1 490» — с пробелом-разделителем (в том числе неразрывным);
  * «10000» — без разделителей;
  * «3,01», «0,4» — с запятой вместо точки;
  * «≈ 10 ₽», «~10 ₽», «**~1 ₽/мес**», «24 500 ₽/мес», «55 000 ₽/год» — с валютой;
  * «≤ 3,01 ₽ за вопрос» — со знаком и валютой;
  * «R-05» — НЕ число: идентификатор риска.

Чего тест не делает: не правит дрейф и не подгоняет пороги под документ — он только краснеет.
Ни JSON, ни документы он не меняет.
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

# Файлы, которые гард реально читает. Объявление `source` в JSON сверяется ровно с этим
# списком: расхождение «заявлено ↔ охраняется» падает (тест о provenance).
GUARDED_FILES = (
    str(BUSINESS_PATH.relative_to(ROOT)),
    str(PLAN_PATH.relative_to(ROOT)),
)

# Канонический раздел 05_business.md для каждого варианта: обязан совпасть с тем, что
# объявлено в JSON в поле `source` варианта.
CANON_SECTION = {"A": "3.1", "B": "3.5"}

# Число в тексте документа: «10 000», «3,01», «0,4», «10000».
# Перед цифрой не может стоять буква, дефис или подчёркивание — иначе «R-05» прочиталось бы как 5.
_NUMBER_RE = re.compile(
    r"(?<![\w\-])\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?"
    r"|(?<![\w\-])\d+(?:[.,]\d+)?"
)
# То же число вместе с валютой: «10 000 ₽», «0,4 ₽/мес», «24 500 ₽/мес».
_MONEY_RE = re.compile(
    r"(?<![\w\-])(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*₽"
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


def _to_float(raw: str) -> float:
    """«10 000» → 10000.0, «3,01» → 3.01."""
    compact = re.sub(r"[\s\u00a0\u202f]+", "", raw)
    return float(compact.replace(",", "."))


def _numbers(text: str) -> list[float]:
    """Числа текста: «10 000» → 10000, «3,01» → 3.01, «0,4» → 0.4, «≈ 10 ₽» → 10."""
    return [_to_float(match.group(0)) for match in _NUMBER_RE.finditer(text)]


def _money_numbers(text: str) -> list[float]:
    """Числа, записанные с валютой: «10 000 ₽» → 10000, «0,4 ₽» → 0.4.

    Число без валюты сюда не попадает: «25 вопросов» — не рубли.
    """
    return [_to_float(match.group(1)) for match in _MONEY_RE.finditer(text)]


def _marker_window(text: str, marker: str, width: int) -> str | None:
    """Кусок текста от маркера и на `width` символов; None — маркера нет.

    Маркер ищется как отдельное слово: «документ» не ловит «документацию».
    """
    match = re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", text, flags=re.IGNORECASE)
    if match is None:
        return None
    return text[match.start() : match.start() + width]


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


def _budget_phrase() -> str:
    """Месячный бюджет проекта из §4 — конкретная величина, а не «число среди чисел».

    Опора R-05 варианта А: «месячный бюджет в 10 000 ₽». Читается только она — соседние
    числа раздела («3–8 раз», «55 000 ₽/год», «73 500 ₽/мес») к бюджету не относятся и
    приниматься не должны.
    """
    window = _marker_window(_business_section("4. Постоянные затраты"), "месячный бюджет", 60)
    assert window is not None, "в §4 05_business.md нет «месячный бюджет»"
    return window


# --- модель гарда -----------------------------------------------------------------


@dataclass(frozen=True)
class Anchor:
    """Опора гарда: кусок документа, по которому читается величина порога.

    kind:
      * ``cell``    — ячейка таблицы или сводки: величина читается из неё;
      * ``phrase``  — узкое окно текста после маркера: величина читается из окна;
      * ``inherit`` — в куске написано «то же»: величина берётся у другого порога;
      * ``section`` — раздел называет сценарий (маркер): пока сценарий не назван, раздел
        молчит; назван — величина читается, если записана с валютой.
    """

    label: str
    kind: str
    extract: Callable[[], str]
    marker: str = ""


@dataclass(frozen=True)
class Threshold:
    """Порог из JSON и его опоры в документах-источниках.

    Состояние порога («число» / «не пересчитано» / «то же») в тесте не зашито: оно
    вычисляется по документам.
    """

    variant: str
    group: str
    field: str
    anchors: tuple[Anchor, ...]
    inherits: tuple[str, str, str] | None = None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.variant, self.group, self.field)


@dataclass(frozen=True)
class Reading:
    """Что источник говорит о пороге.

    kind:
      * ``number``     — величина названа числом (values — это число);
      * ``ambiguous``  — в куске несколько чисел с валютой, какое именно — неясно;
      * ``not_stated`` — источник прямо говорит «не пересчитано»;
      * ``mentioned``  — источник называет сценарий, но величину в нём прочитать нельзя;
      * ``inherited``  — источник говорит «то же» (величина — у другого порога);
      * ``silent``     — источник о пороге молчит.
    """

    kind: str
    values: frozenset[float] = frozenset()


EXPECTATIONS: tuple[Threshold, ...] = (
    # --- вариант А: канон 05_business.md §3.1 ---
    Threshold(
        variant="A",
        group="dialog",
        field="max_rub_per_day",
        anchors=(
            Anchor(
                label="05_business.md §3.1: «Сутки диалога» → «Себестоимость»",
                kind="cell",
                extract=lambda: _business_cell(
                    "3.1 Себестоимость",
                    ("Продукт", "Себестоимость"),
                    "Сутки диалога",
                    "Себестоимость",
                ),
            ),
            Anchor(
                label="сводка G17-S1-план.md: «Вопрос в диалоге», вариант А",
                kind="cell",
                extract=lambda: _plan_dialog_parts("A")[0],
            ),
        ),
    ),
    Threshold(
        variant="A",
        group="dialog",
        field="max_rub_per_question",
        anchors=(
            # В §3.1 цены вопроса нет: порог 0,4 ₽ записан только в сводке.
            Anchor(
                label="сводка G17-S1-план.md: «Вопрос в диалоге», вариант А",
                kind="cell",
                extract=lambda: _plan_dialog_parts("A")[1],
            ),
        ),
    ),
    Threshold(
        variant="A",
        group="document",
        field="max_rub",
        anchors=(
            Anchor(
                label="05_business.md §3.1: «Документ» → «Себестоимость»",
                kind="cell",
                extract=lambda: _business_cell(
                    "3.1 Себестоимость",
                    ("Продукт", "Себестоимость"),
                    "Документ",
                    "Себестоимость",
                ),
            ),
            Anchor(
                label="сводка G17-S1-план.md: «Документ-синтез», вариант А",
                kind="cell",
                extract=lambda: _plan_cell("Документ-синтез", "вариант А"),
            ),
        ),
    ),
    Threshold(
        variant="A",
        group="forecast",
        field="max_rub_per_user_month",
        anchors=(
            Anchor(
                label="05_business.md §3.1: «Бесплатный слой» → «Себестоимость»",
                kind="cell",
                extract=lambda: _business_cell(
                    "3.1 Себестоимость",
                    ("Продукт", "Себестоимость"),
                    "Бесплатный слой на пользователя",
                    "Себестоимость",
                ),
            ),
            Anchor(
                label="сводка G17-S1-план.md: «Утренний прогноз», вариант А",
                kind="cell",
                extract=lambda: _plan_cell("Утренний прогноз", "вариант А"),
            ),
        ),
    ),
    Threshold(
        variant="A",
        group="r05",
        field="max_rub_per_month_5000_mau",
        anchors=(
            Anchor(
                label="сводка G17-S1-план.md: «Итог R-05», вариант А",
                kind="cell",
                extract=lambda: _plan_cell("Итог R-05", "вариант А"),
            ),
            Anchor(
                label="05_business.md §4: «месячный бюджет в N ₽»",
                kind="phrase",
                extract=_budget_phrase,
            ),
        ),
    ),
    # --- вариант Б: канон 05_business.md §3.5 ---
    Threshold(
        variant="B",
        group="dialog",
        field="max_rub_per_question",
        anchors=(
            Anchor(
                label="05_business.md §3.5: «Opus 5» → «₽ за вопрос»",
                kind="cell",
                extract=lambda: _business_cell(
                    "3.5 Пересчёт себестоимости под Opus 5",
                    ("Модель", "₽ за вопрос"),
                    "Opus 5",
                    "₽ за вопрос",
                ),
            ),
            Anchor(
                label="сводка G17-S1-план.md: «Вопрос в диалоге», вариант Б",
                kind="cell",
                extract=lambda: _plan_dialog_parts("B")[1],
            ),
        ),
    ),
    Threshold(
        variant="B",
        group="dialog",
        field="max_rub_per_day",
        anchors=(
            Anchor(
                label="05_business.md §3.5: «25 (средний)» → «Себестоимость»",
                kind="cell",
                extract=lambda: _business_cell(
                    "3.5 Пересчёт себестоимости под Opus 5",
                    ("Вопросов за сутки", "Себестоимость"),
                    "25 (средний)",
                    "Себестоимость",
                ),
            ),
            Anchor(
                label="сводка G17-S1-план.md: «Вопрос в диалоге», вариант Б",
                kind="cell",
                extract=lambda: _plan_dialog_parts("B")[0],
            ),
        ),
    ),
    Threshold(
        variant="B",
        group="document",
        field="max_rub",
        anchors=(
            Anchor(
                label="сводка G17-S1-план.md: «Документ-синтез», вариант Б",
                kind="cell",
                extract=lambda: _plan_cell("Документ-синтез", "вариант Б"),
            ),
            Anchor(
                label="05_business.md §3.5: сценарий «документ» не назван",
                kind="section",
                extract=lambda: _business_section("3.5 Пересчёт себестоимости под Opus 5"),
                marker="документ",
            ),
        ),
    ),
    Threshold(
        variant="B",
        group="forecast",
        field="max_rub_per_user_month",
        inherits=("A", "forecast", "max_rub_per_user_month"),
        anchors=(
            Anchor(
                label="сводка G17-S1-план.md: «Утренний прогноз», вариант Б",
                kind="inherit",
                extract=lambda: _plan_cell("Утренний прогноз", "вариант Б"),
            ),
            Anchor(
                label="05_business.md §3.5: сценарий «прогноз» не назван",
                kind="section",
                extract=lambda: _business_section("3.5 Пересчёт себестоимости под Opus 5"),
                marker="прогноз",
            ),
        ),
    ),
    Threshold(
        variant="B",
        group="r05",
        field="max_rub_per_month_5000_mau",
        anchors=(
            Anchor(
                label="сводка G17-S1-план.md: «Итог R-05», вариант Б",
                kind="cell",
                extract=lambda: _plan_cell("Итог R-05", "вариант Б"),
            ),
            Anchor(
                label="05_business.md §3.5: риск «R-05» не назван",
                kind="section",
                extract=lambda: _business_section("3.5 Пересчёт себестоимости под Opus 5"),
                marker="R-05",
            ),
        ),
    ),
)

BY_KEY: dict[tuple[str, str, str], Threshold] = {t.key: t for t in EXPECTATIONS}


# --- чтение величины и ожидаемое значение -----------------------------------------


def _read_anchor(anchor: Anchor) -> Reading:
    """Что источник говорит о пороге (см. Reading)."""
    fragment = anchor.extract()
    if anchor.kind == "inherit":
        return Reading("inherited") if _INHERITED in fragment.lower() else Reading("silent")
    if anchor.kind == "section":
        window = _marker_window(fragment, anchor.marker, 120)
        if window is None:
            return Reading("silent")
        money = _money_numbers(window)
        if len(money) == 1:
            return Reading("number", frozenset(money))
        if len(money) > 1:
            return Reading("ambiguous", frozenset(money))
        return Reading("mentioned")
    money = _money_numbers(fragment)
    if len(money) == 1:
        return Reading("number", frozenset(money))
    if len(money) > 1:
        return Reading("ambiguous", frozenset(money))
    if _NOT_RECALCULATED in fragment.lower():
        return Reading("not_stated")
    numbers = _numbers(fragment)
    if len(numbers) == 1:
        return Reading("number", frozenset(numbers))
    if len(numbers) > 1:
        return Reading("ambiguous", frozenset(numbers))
    return Reading("silent")


def _collect(
    threshold: Threshold,
    stack: tuple[tuple[str, str, str], ...] = (),
) -> tuple[str, frozenset[float], list[str]]:
    """Что документы говорят о пороге.

    Возвращает (режим, значения, ошибки):
      * ``null``   — документ говорит «не пересчитано», ожидается null;
      * ``number`` — ожидается одно из значений;
      * ``any``    — величина названа, но прочитать её нельзя: ожидается любое число.
    """
    assert threshold.key not in stack, f"цикл наследования: {threshold.key}"
    readings: list[tuple[str, Reading]] = []
    for anchor in threshold.anchors:
        reading = _read_anchor(anchor)
        if reading.kind == "inherited":
            assert threshold.inherits is not None, (
                f"{threshold.key}: в источнике «то же», но не сказано, от какого порога"
            )
            parent = BY_KEY[threshold.inherits]
            mode, values, errors = _collect(parent, stack + (threshold.key,))
            assert not errors, f"{threshold.key}: не разобрался источник «то же» — {errors}"
            if mode == "null":
                readings.append((anchor.label, Reading("not_stated")))
            else:
                readings.append((anchor.label, Reading("number", values)))
        else:
            readings.append((anchor.label, reading))

    numbers = [
        (label, next(iter(reading.values)))
        for label, reading in readings
        if reading.kind == "number"
    ]
    ambiguous = [
        (label, reading.values) for label, reading in readings if reading.kind == "ambiguous"
    ]
    not_stated = [label for label, reading in readings if reading.kind == "not_stated"]
    mentioned = [label for label, reading in readings if reading.kind == "mentioned"]

    errors: list[str] = []
    if len({value for _, value in numbers}) > 1:
        errors.append(
            "источники называют разные величины: "
            + ", ".join(f"{label} — {value:g}" for label, value in numbers)
        )
    for label, values in ambiguous:
        for other_label, value in numbers:
            if value not in values:
                errors.append(
                    f"{label}: величина {value:g} из «{other_label}» не входит в {sorted(values)}"
                )
    if not_stated and (numbers or ambiguous or mentioned):
        errors.append(
            "источник говорит «не пересчитан», а другой называет величину: "
            + ", ".join(not_stated)
        )

    if numbers:
        return "number", frozenset(value for _, value in numbers), errors
    if ambiguous:
        common = set.intersection(*(set(values) for _, values in ambiguous))
        return "number", frozenset(common), errors
    if mentioned:
        return "any", frozenset(), errors
    return "null", frozenset(), errors


# --- helpers проверки --------------------------------------------------------------


def _thresholds() -> dict:
    return json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))


def _json_value(variant: str, group: str, field: str):
    """Значение порога из JSON; KeyError — если порога в файле нет."""
    return _thresholds()["variants"][variant]["thresholds"][group][field]


def _declared_files(text: str) -> set[str]:
    """Пути к документам, названные в объявлении `source`."""
    return set(re.findall(r"docs/[\w\-/]+\.md", text))


def _declared_section(text: str) -> str | None:
    """Номер раздела, названный в объявлении `source`: «§3.1» → «3.1»."""
    match = re.search(r"§\s*(\d+(?:\.\d+)*)", text)
    return match.group(1) if match else None


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
    """Каждый порог из JSON совпадает с тем, как он записан в документах-источниках.

    Ожидаемое значение вычисляется по документам: правка документа вместе с JSON (в том числе
    переход `null` → число) — зелёный, рассинхрон — красный в обе стороны.
    """
    mode, values, errors = _collect(порог)
    assert not errors, f"{порог.key}: " + "; ".join(errors)
    value = _json_value(*порог.key)
    if mode == "null":
        assert value is None, (
            f"{порог.key}: в документе «не пересчитано», а в порогах {value!r} "
            f"(null — это «не пересчитано», а не 0)"
        )
        return
    assert value is not None, (
        f"{порог.key}: в документе названа величина, а в порогах null — "
        f"порог надо пересчитать в JSON"
    )
    if mode == "number":
        assert float(value) in values, (
            f"{порог.key}: в документе {sorted(values)}, в порогах {value}"
        )


def test_every_threshold_in_json_has_an_anchor():
    """Ни один порог из JSON не остался без опоры в документах — гард не молчит."""
    data = _thresholds()
    declared = {
        (variant, group, field)
        for variant, body in data["variants"].items()
        for group, fields in body["thresholds"].items()
        for field in fields
    }
    covered = {t.key for t in EXPECTATIONS}
    assert declared - covered == set(), (
        "пороги без опоры в гарде: "
        + ", ".join(f"{v}.{g}.{f}" for v, g, f in sorted(declared - covered))
    )


def test_null_thresholds_follow_the_document():
    """Набор «не пересчитанных» порогов берётся из документов, а не зашит в тест.

    null в JSON стоит ровно у тех порогов, документ которых говорит «не пересчитано».
    """
    data = _thresholds()
    nulls = {
        (variant, group, field)
        for variant, body in data["variants"].items()
        for group, fields in body["thresholds"].items()
        for field, value in fields.items()
        if value is None
    }
    from_documents = {t.key for t in EXPECTATIONS if _collect(t)[0] == "null"}
    assert nulls == from_documents, (
        f"null в JSON: {sorted(nulls)}; по документам «не пересчитано»: {sorted(from_documents)}"
    )


def test_null_is_not_zero():
    """null = «не пересчитано»: не 0 и не «порога нет»."""
    data = _thresholds()
    for variant, body in data["variants"].items():
        for group, fields in body["thresholds"].items():
            for field, value in fields.items():
                if value is None:
                    continue
                assert value != 0, f"{variant}.{group}.{field}: 0 — не то же, что null"


def test_declared_sources_match_guarded_sources():
    """Объявленный в JSON `source` совпадает с тем, что гард реально охраняет.

    Расхождение в любую сторону — красный: JSON не должен называть источник, которого
    гард не читает, и гард не должен читать источник, который JSON не объявил.
    """
    data = _thresholds()
    declared = _declared_files(data["source"])
    for variant, body in data["variants"].items():
        declared |= _declared_files(body["source"])
        assert _declared_section(body["source"]) == CANON_SECTION[variant], (
            f"вариант {variant}: в JSON объявлен раздел "
            f"{_declared_section(body['source'])!r}, гард охраняет {CANON_SECTION[variant]!r}"
        )
    assert declared == set(GUARDED_FILES), (
        f"объявлено в JSON: {sorted(declared)}; охраняет гард: {sorted(GUARDED_FILES)}"
    )


def test_declared_note_is_not_stale():
    """`note` в JSON не устарела: гард на месте, семантика null — та же."""
    note = _thresholds()["note"]
    assert "tests/test_llm_cost_thresholds.py" in note, (
        f"note не называет гард, который ловит дрейф: {note!r}"
    )
    assert (ROOT / "tests" / "test_llm_cost_thresholds.py").exists(), (
        "note называет несуществующий файл гарда"
    )
    assert _NOT_RECALCULATED in note.lower(), (
        f"note не объясняет, что значит null: {note!r}"
    )


def test_budget_anchor_reads_one_value():
    """§4-опора читает конкретную величину бюджета, а не «число среди чисел раздела»."""
    section = _business_section("4. Постоянные затраты")
    assert len(_numbers(section)) > 10, "в §4 много чисел — опора обязана быть узкой"
    money = _money_numbers(_budget_phrase())
    assert len(money) == 1, f"§4-опора читает {len(money)} чисел, а должна — одно: {money}"


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
        ("24 500 ₽/мес", 24500.0),
        ("55 000 ₽/год", 55000.0),
        ("**~1 ₽/мес**", 1.0),
    ],
)
def test_number_formats_are_read_numerically(текст: str, ожидаемое: float):
    """Допустимые форматы записи числа читаются численно — ложной тревоги быть не должно."""
    assert _numbers(текст) == [ожидаемое]


@pytest.mark.parametrize(
    ("текст", "ожидаемое"),
    [
        ("10 000 ₽", 10000.0),
        ("24 500 ₽/мес", 24500.0),
        ("**~1 ₽/мес**", 1.0),
        ("≤ 3,01 ₽ за вопрос", 3.01),
        ("75 ₽", 75.0),
    ],
)
def test_money_formats_are_read_numerically(текст: str, ожидаемое: float):
    """Число с валютой читается численно — «10 000 ₽» → 10000."""
    assert _money_numbers(текст) == [ожидаемое]


def test_same_value_in_different_formats_is_equal():
    """«10 000», «10000» и «≈ 10 000 ₽» — одно и то же число."""
    assert _numbers("10 000")[0] == _numbers("10000")[0] == _numbers("≈ 10 000 ₽")[0]


def test_risk_id_is_not_read_as_a_number():
    """«R-05» — идентификатор риска, а не число."""
    assert _numbers("R-05 на топовую модель не пересчитан") == []


def test_question_count_is_not_a_money_value():
    """«25 вопросов» — не рубли: число без валюты в опору не попадает."""
    assert _money_numbers("сутки из 25 вопросов ≈ 10 ₽") == [10.0]
