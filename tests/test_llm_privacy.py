"""S3b-01: приватность пакета, уходящего в модель (152-ФЗ).

Проверяем ровно одно: в служебной части пакета (системный промпт, данные карты,
служебные поля) нет персональных данных — ФИО, даты и места рождения, города,
`user_id`, Telegram id.

Граница проверки: вопрос пользователя и история диалога — его собственные слова,
фильтровать их по контракту задачи нельзя. Поэтому в проверку входит только
служебная часть пакета, а вопрос и история исключены.

Все данные в фикстурах вымышленные.
"""

import re
from copy import deepcopy

import httpx
import pytest

from lunora.llm.client import build_messages
from lunora.llm.prompts import (
    SAFETY_ADDENDUM_CRISIS,
    SAFETY_ADDENDUM_FINANCIAL,
    SAFETY_ADDENDUM_MEDICAL,
    SYSTEM_PROMPT,
    format_chart_data,
)
from lunora.llm.safety import Category, classify_input

# ── ПДн: значения-маркеры (вымышленные) ────────────────────────────────────

PII_SURNAME = "Иванова"
PII_GIVEN = "Мария"
PII_PATRONYMIC = "Петровна"
PII_FULL_NAME = f"{PII_SURNAME} {PII_GIVEN} {PII_PATRONYMIC}"
PII_BIRTH_DATE = "1987-04-23"
PII_BIRTH_CITY = "Новосибирск"
PII_USER_ID = "11111111-2222-4333-8444-555555555555"
PII_TELEGRAM_ID = "100200300"

PII_MARKERS = {
    "фамилия": PII_SURNAME,
    "имя": PII_GIVEN,
    "отчество": PII_PATRONYMIC,
    "фио": PII_FULL_NAME,
    "дата рождения": PII_BIRTH_DATE,
    "место рождения / город": PII_BIRTH_CITY,
    "user_id": PII_USER_ID,
    "telegram_id": PII_TELEGRAM_ID,
}

# Формы, которые узнаются без знания исходных значений.
PII_PATTERNS = {
    "дата (ISO)": re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    "дата (ДД.ММ.ГГГГ)": re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b"),
    "uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    "telegram-подобный id": re.compile(r"\b\d{9,11}\b"),
}

# ── Карта: только градусы, знаки, дома и текст ──────────────────────────────

CLEAN_CHART = {
    "western": {
        "planets": [
            {
                "name": "Луна",
                "longitude": 223.42,
                "sign": "Скорпион",
                "degree_in_sign": 13.42,
                "house": 3,
                "stability": "stable",
            },
            {
                "name": "Солнце",
                "longitude": 15.2,
                "sign": "Овен",
                "degree_in_sign": 15.2,
                "house": 11,
                "stability": "stable",
            },
            {
                "name": "Марс",
                "longitude": 310.1,
                "sign": "Водолей",
                "degree_in_sign": 10.1,
                "house": 7,
                "stability": "stable",
            },
            {
                "name": "Плутон",
                "longitude": 118.0,
                "sign": "Скорпион",
                "degree_in_sign": 28.0,
                "house": 3,
                "stability": "undetermined",
            },
        ],
        "aspects": [
            {
                "planet1": "Марс",
                "planet2": "Венера",
                "aspect_type": "соединение",
                "angle": 0.0,
                "orb": 1.1,
            },
            {
                "planet1": "Солнце",
                "planet2": "Юпитер",
                "aspect_type": "квадрат",
                "angle": 90.0,
                "orb": 2.4,
            },
            {
                "planet1": "Луна",
                "planet2": "Сатурн",
                "aspect_type": "тригон",
                "angle": 120.0,
                "orb": 5.6,
            },
        ],
    },
    "vedic": {
        "planets": [
            {"name": "Луна", "sign": "Скорпион", "degree_in_sign": 13.42},
            {"name": "Солнце", "sign": "Овен", "degree_in_sign": 15.2},
        ],
        "moon_nakshatra": {"name": "Пурва Пудар", "pada": 2, "lord": "Дхарма"},
        "dasha_periods": [
            {"planet": "Луна", "start_year": 2016.0, "end_year": 2026.0, "years": 10.0},
            {"planet": "Марс", "start_year": 2026.0, "end_year": 2036.0, "years": 10.0},
        ],
    },
    "chinese": {
        "year_pillar": {
            "stem": "Динь",
            "branch": "Хай",
            "element": "Вода",
            "yin_yang": "ян",
        },
        "day_master": "Гэнь",
        "day_master_element": "Дерево",
        "day_master_yin_yang": "инь",
        "year_animal": "Крыса",
        "visible_stem_counts": {"Динь": 2, "Гэнь": 1},
    },
    "numerology": {
        "life_path": 7,
        "birthday_number": 23,
        "pythagoras": {"cells": {1: 3, 2: 2, 3: 4}, "working_numbers": [1, 2, 3, 4]},
    },
}

# Служебные поля, которых в карте быть не должно. Подкладываются в те места
# JSONB-строки, куда их может положить любая правка данных, — не в те ключи,
# которые читает сборка пакета (format_chart_data читает только перечисленные
# ключи). Если сборка когда-нибудь начнёт читать их или выгружать карту целиком,
# тест обязан покраснеть.
IDENTITY_FIELDS = {
    "user_id": PII_USER_ID,
    "telegram_id": PII_TELEGRAM_ID,
    "name": PII_FULL_NAME,
    "birth_date": PII_BIRTH_DATE,
    "birth_city": PII_BIRTH_CITY,
}


def chart_with_identity(chart: dict) -> dict:
    """Карта с подложенными ПДн в служебных полях."""
    planted = deepcopy(chart)
    planted.update(IDENTITY_FIELDS)
    planted["western"].update(IDENTITY_FIELDS)
    planted["vedic"]["name"] = PII_FULL_NAME
    planted["chinese"]["birth_date"] = PII_BIRTH_DATE
    planted["numerology"]["birth_city"] = PII_BIRTH_CITY
    return planted


# ── Golden: точный ожидаемый пакет ──────────────────────────────────────────

GOLDEN_QUESTION = "Что мне поставить в фокус на этот месяц?"
GOLDEN_PRECISION = "exact"
GOLDEN_HISTORY = [
    {"role": "user", "content": "Привет!"},
    {"role": "assistant", "content": "Привет! Я Лунора."},
]

GOLDEN_CHART_TEXT = (
    "### Западная астрология\n"
    "- Луна: 13.42° Скорпион (3 дом)\n"
    "- Солнце: 15.2° Овен (11 дом)\n"
    "- Марс: 10.1° Водолей (7 дом)\n"
    "- Ключевые аспекты: Марс соединение Венера (1.1°), Солнце квадрат Юпитер (2.4°), "
    "Луна тригон Сатурн (5.6°)\n"
    "\n"
    "### Ведическая астрология (Lahiri)\n"
    "- Луна: 13.42° Скорпион\n"
    "- Солнце: 15.2° Овен\n"
    "- Накшатра Луны: Пурва Пудар (pada 2), владыка — Дхарма\n"
    "- Текущая Mahadasha: Луна (2016–2026)\n"
    "\n"
    "### Китайская астрология (Ба-Цзы)\n"
    "- Год: ДиньХай (Вода ян, Крыса)\n"
    "- Дневной ствол: Гэнь = Дерево (инь)\n"
    "- Видимые стволы: Динь 2, Гэнь 1\n"
    "\n"
    "### Нумерология\n"
    "- Число жизненного пути: 7\n"
    "- Число дня рождения: 23\n"
    "- Сильные позиции в квадрате: 1, 3"
)

GOLDEN_USER_CONTENT = (
    "## Данные натальной карты\n"
    + GOLDEN_CHART_TEXT
    + f"\n\nТочность времени рождения: {GOLDEN_PRECISION}."
    + f"\n\n## Вопрос\n{GOLDEN_QUESTION}"
)

GOLDEN_MESSAGES = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": "Привет!"},
    {"role": "assistant", "content": "Привет! Я Лунора."},
    {"role": "user", "content": GOLDEN_USER_CONTENT},
]

# Строка планеты в пакете: «- <планета>: <градусы>° <знак> …»
PLANET_LINE_RE = re.compile(r"^- [^\s:]+: \d+(?:\.\d+)?° ", re.MULTILINE)

QUESTION_MARKER = "\n\n## Вопрос\n"


# ── Вспомогательное ─────────────────────────────────────────────────────────


def package_text(messages: list[dict]) -> str:
    """Весь пакет текстом (для проверки, что в нём вообще есть карта)."""
    return "\n".join(m["content"] for m in messages)


def service_text(messages: list[dict]) -> str:
    """Служебная часть пакета: системный промпт + данные карты + служебные поля.

    Вопрос пользователя и история диалога — его собственные слова, фильтровать
    их нельзя, поэтому в проверку ПДн они не входят. Сообщение с картой узнаём
    по маркеру вопроса: сообщения истории такого маркера не содержат.
    """
    system = [m["content"] for m in messages if m["role"] == "system"]
    users = [m["content"] for m in messages if m["role"] == "user"]
    chart_message = next((u for u in users if QUESTION_MARKER in u), None)
    if chart_message is None:
        raise AssertionError(f"в пакете нет маркера {QUESTION_MARKER!r} — формат изменился")
    head, _, _ = chart_message.partition(QUESTION_MARKER)
    return "\n".join(system + [head])


def find_personal_data(messages: list[dict]) -> list[str]:
    """Найти ПДн в служебной части пакета. Пустой список — пакет чист."""
    text = service_text(messages).casefold()
    found = {kind for kind, value in PII_MARKERS.items() if value.casefold() in text}
    found |= {kind for kind, pattern in PII_PATTERNS.items() if pattern.search(text)}
    return sorted(found)


def legacy_messages(
    question: str,
    chart_data: dict,
    precision: str,
    history: list[dict] | None = None,
) -> list[dict]:
    """Сборка пакета до выноса в build_messages — дословно как было в client.py.

    Эталон побайтового совпадения: вынос чистой функции не должен был изменить
    ни одного байта пакета.
    """
    category = classify_input(question)
    system = SYSTEM_PROMPT
    if category == Category.MEDICAL:
        system += "\n\n" + SAFETY_ADDENDUM_MEDICAL
    elif category == Category.CRISIS:
        system += "\n\n" + SAFETY_ADDENDUM_CRISIS
    elif category == Category.FINANCIAL:
        system += "\n\n" + SAFETY_ADDENDUM_FINANCIAL
    chart_text = format_chart_data(chart_data)
    precision_note = f"\nТочность времени рождения: {precision}."
    if precision in ("unknown", "approximate"):
        precision_note += " Не интерпретируй дома и ASC."
    user_content = (
        f"## Данные натальной карты\n{chart_text}\n{precision_note}\n\n## Вопрос\n{question}"
    )
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages


# ── Критерий (а): чистая функция, сборка не изменилась ──────────────────────


class TestBuildMessages:
    def test_golden_package(self):
        """Точное ожидаемое сообщение: ни байта влево, ни байта вправо."""
        messages = build_messages(GOLDEN_QUESTION, CLEAN_CHART, GOLDEN_PRECISION, GOLDEN_HISTORY)
        assert messages == GOLDEN_MESSAGES

    @pytest.mark.parametrize(
        ("question", "precision", "history"),
        [
            (GOLDEN_QUESTION, "exact", None),
            (GOLDEN_QUESTION, "exact", GOLDEN_HISTORY),
            (GOLDEN_QUESTION, "unknown", None),
            (GOLDEN_QUESTION, "approximate", None),
            (GOLDEN_QUESTION, "approximate_30", None),
            (GOLDEN_QUESTION, "approximate_60", None),
            ("У меня болит поясница, что это значит?", "exact", None),
            ("Не хочу жить", "exact", None),
            ("Стоит ли вложить в крипту?", "exact", None),
        ],
    )
    def test_matches_legacy_assembly(self, question, precision, history):
        """Сборка совпадает с прежней побайтово — на всех ветках."""
        messages = build_messages(question, CLEAN_CHART, precision, history)
        assert messages == legacy_messages(question, CLEAN_CHART, precision, history)

    def test_no_network(self, monkeypatch):
        """build_messages — чистая функция: сеть не трогаем."""

        class _Boom:
            def __init__(self, *args, **kwargs):
                raise AssertionError("build_messages не ходит в сеть")

        monkeypatch.setattr(httpx, "AsyncClient", _Boom)
        messages = build_messages(GOLDEN_QUESTION, CLEAN_CHART, GOLDEN_PRECISION)
        assert messages

    def test_does_not_mutate_input(self):
        """Чистая функция: карта и история на входе не меняются."""
        chart = deepcopy(CLEAN_CHART)
        history = deepcopy(GOLDEN_HISTORY)
        build_messages(GOLDEN_QUESTION, chart, GOLDEN_PRECISION, history)
        assert chart == CLEAN_CHART
        assert history == GOLDEN_HISTORY

    def test_returns_fresh_list(self):
        """Каждый вызов — свой список: общее состояние не течёт между пакетами."""
        first = build_messages(GOLDEN_QUESTION, CLEAN_CHART, GOLDEN_PRECISION)
        first.append({"role": "assistant", "content": "мусор"})
        second = build_messages(GOLDEN_QUESTION, CLEAN_CHART, GOLDEN_PRECISION)
        assert second == [GOLDEN_MESSAGES[0], GOLDEN_MESSAGES[3]]
        assert len(second) == 2


# ── Критерий (в): карта без ПДн — пакет чист, и он не пустой ────────────────


class TestPackagePrivacy:
    def test_clean_chart_package_has_no_personal_data(self):
        """Карта с градусами, знаками, домами и текстом — в пакете нет ПДн."""
        messages = build_messages(GOLDEN_QUESTION, CLEAN_CHART, GOLDEN_PRECISION, GOLDEN_HISTORY)
        assert find_personal_data(messages) == []

    def test_card_with_identity_fields_package_has_no_personal_data(self):
        """ПДн в служебных полях карты не должны доехать до пакета."""
        chart = chart_with_identity(CLEAN_CHART)
        messages = build_messages(GOLDEN_QUESTION, chart, GOLDEN_PRECISION, GOLDEN_HISTORY)
        assert find_personal_data(messages) == []

    def test_package_really_contains_planets(self):
        """Пустой пакет тест пропускать не должен: планеты обязаны быть в тексте."""
        messages = build_messages(GOLDEN_QUESTION, CLEAN_CHART, GOLDEN_PRECISION)
        planet_lines = PLANET_LINE_RE.findall(package_text(messages))
        # 3 западных + 2 ведических; Плутон не показываем — stability undetermined
        assert len(planet_lines) == 5
        assert "- Луна: 13.42° Скорпион (3 дом)" in package_text(messages)

    def test_user_words_are_not_filtered(self):
        """Вопрос и история — собственные слова пользователя: их не фильтруем.

        Слова пользователя остаются в пакете дословно, и в проверку ПДн они не
        входят: проверяем данные карты и служебные поля, а не речь человека.
        """
        question = "Меня зовут Иванова Мария, я из Новосибирска, когда мне ждать перемен?"
        history = [{"role": "user", "content": "Я Иванова Мария, я из Новосибирска"}]
        messages = build_messages(question, chart_with_identity(CLEAN_CHART), "exact", history)
        assert messages[-1]["content"].endswith(f"## Вопрос\n{question}")
        assert history[0]["content"] in package_text(messages)
        assert find_personal_data(messages) == []

    @pytest.mark.parametrize("kind", sorted(PII_MARKERS))
    def test_detector_catches_personal_data_that_reached_the_package(self, kind):
        """Чувствительность проверки: ПДн, дошедшие до пакета, обязаны быть найдены."""
        chart = deepcopy(CLEAN_CHART)
        chart["western"]["planets"][0]["name"] = PII_MARKERS[kind]
        messages = build_messages(GOLDEN_QUESTION, chart, GOLDEN_PRECISION)
        assert kind in find_personal_data(messages)
