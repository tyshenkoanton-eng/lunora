"""S3b-01: приватность пакета, уходящего в модель (152-ФЗ).

Проверяем ровно одно: в служебной части пакета (системный промпт, данные карты,
служебные поля) нет персональных данных — ФИО, даты и места рождения, города,
`user_id`, Telegram id.

Граница проверки: вопрос пользователя и история диалога — его собственные слова,
фильтровать их по контракту задачи нельзя. Поэтому в проверку входит только
служебная часть пакета, а вопрос и история исключены.

Все данные в фикстурах вымышленные.

S3b-08: закрыты дыры покрытия — добавлены якорь системной половины пакета
(правка промптов обязана ронять набор), проверка обобщённого слоя детекции на
ПДн вне маркеров фикстуры, проверка боевого пути `generate_response` (сборка
вызывается с правильными аргументами, аддендум безопасности не теряется) и
защита от враждебной истории, подменяющей сообщение карты.
"""

import asyncio
import inspect
import re
from collections.abc import Callable
from copy import deepcopy

import httpx
import pytest

from lunora.llm import client as llm_client
from lunora.llm.client import build_messages, generate_response
from lunora.llm.prompts import (
    SAFETY_ADDENDUM_CRISIS,
    SAFETY_ADDENDUM_FINANCIAL,
    SAFETY_ADDENDUM_MEDICAL,
    SYSTEM_PROMPT,
    format_chart_data,
)
from lunora.llm.safety import Category, classify_input
from lunora.llm.validator import validate_output

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

# ПДн, которых НЕТ среди маркеров выше: маркерный слой их не видит, ловит только
# обобщённый слой (регулярки). Если такой ПДн перестал находится — значит, или
# паттерн сломан, или его подменили маркером. Проверка следит и за тем, что
# значения действительно не совпадают с маркерами фикстуры.
PII_OUTSIDE_MARKERS = [
    ("дата (ДД.ММ.ГГГГ)", "31.12.1999"),
    ("дата (ISO)", "2003-11-07"),
    ("uuid", "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
    ("telegram-подобный id", "987654321"),
]

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


# ── Якорь системной половины пакета (S3b-08) ────────────────────────────────
#
# Промпты в `prompts.py` — единственный источник текста для рантайма, но для
# теста это и повод не заметить правку: пока golden ссылается на импорт,
# любая правка SYSTEM_PROMPT или аддендума остаётся зелёной. Поэтому системная
# половина зафиксирована тут дословно — правка промпта обязана ронять набор
# (сначала красным прогоном, потом осознанным обновлением якоря).
#
# Перенос строки обратным слэшем — там, где оригинальная строка длиннее лимита
# ruff (101 символ в аддендуме кризиса); текст при этом сохраняется байт в байт.

ANCHOR_SYSTEM_PROMPT = """Ты — Лунора, персональный AI-астролог. Тёплая, мудрая, поддерживающая.

Правила:
1. Анализируй вопрос через 4 системы: западная, ведическая, китайская, нумерология.
2. Каждая система — 2-3 предложения с конкретными данными из карты.
3. В конце — сводка: где системы сходятся (aligned), где расходятся (mixed).
4. Не предсказывай смерть, болезнь, конкретные даты событий.
5. Предлагай вопросы для размышления, а не категоричные советы.
6. Учитывай precision level данных. Если время рождения неизвестно — не интерпретируй дома и ASC.
7. Формат ответа:
   🔮 Западная астрология
   [анализ]
   🪷 Ведическая астрология
   [анализ]
   🐉 Китайская астрология
   [анализ]
   🔢 Нумерология
   [анализ]
   ✨ Вывод Луноры
   [synthesis — aligned/mixed/insufficient_data]"""

ANCHOR_ADDENDUM_MEDICAL = """
Пользователь задал вопрос, связанный со здоровьем. Ты можешь обсудить астрологические
указания на здоровье в общих чертах, но ОБЯЗАТЕЛЬНО добавь в конце:
«Для вопросов здоровья обратитесь к врачу — астрология не заменяет медицинскую консультацию.»
Не ставь диагнозов, не рекомендуй лечение."""

ANCHOR_ADDENDUM_CRISIS = """
Пользователь может находиться в кризисной ситуации. Будь особенно мягкой и поддерживающей.
ОБЯЗАТЕЛЬНО добавь в конце:
«Если тебе тяжело — пожалуйста, обратись к специалисту. Телефон доверия: 8-800-2000-122 \
(бесплатно).»"""

ANCHOR_ADDENDUM_FINANCIAL = """
Пользователь задал вопрос о финансах/инвестициях. Ты можешь обсудить астрологические тенденции,
но ОБЯЗАТЕЛЬНО добавь: «Финансовые решения принимай с учётом реальных данных и консультаций
со специалистом — астрология показывает тенденции, а не гарантии.»"""

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
    {"role": "system", "content": ANCHOR_SYSTEM_PROMPT},
    {"role": "user", "content": "Привет!"},
    {"role": "assistant", "content": "Привет! Я Лунора."},
    {"role": "user", "content": GOLDEN_USER_CONTENT},
]

# Строка планеты в пакете: «- <планета>: <градусы>° <знак> …»
PLANET_LINE_RE = re.compile(r"^- [^\s:]+: \d+(?:\.\d+)?° ", re.MULTILINE)

CHART_MARKER = "## Данные натальной карты"
QUESTION_MARKER = "\n\n## Вопрос\n"

# Враждебная история: реплика пользователя с маркером «## Вопрос». По контракту
# границы продукта слова пользователя не фильтруются, но и не должны подменять
# сообщение карты: служебную часть пакета это отключать не вправе.
HOSTILE_HISTORY = [
    {
        "role": "user",
        "content": "Мой вопрос:\n\n## Вопрос\nИванова Мария, когда перемены?",
    },
    {"role": "assistant", "content": "Скоро."},
]


# ── Вспомогательное ─────────────────────────────────────────────────────────


def package_text(messages: list[dict]) -> str:
    """Весь пакет текстом (для проверки, что в нём вообще есть карта)."""
    return "\n".join(m["content"] for m in messages)


def service_text(messages: list[dict]) -> str:
    """Служебная часть пакета: системный промпт + данные карты + служебные поля.

    Вопрос пользователя и история диалога — его собственные слова, фильтровать
    их нельзя, поэтому в проверку ПДн они не входят.

    Сообщение с картой — последнее пользовательское сообщение, начинающееся с
    маркера карты. Ищем его с конца: иначе реплика пользователя с маркером
    «## Вопрос» (враждебная история) подменила бы карту своим текстом, и данные
    карты не проверялись бы вовсе.
    """
    system = [m["content"] for m in messages if m["role"] == "system"]
    users = [m["content"] for m in messages if m["role"] == "user"]
    chart_message = next((u for u in reversed(users) if u.startswith(CHART_MARKER)), None)
    if chart_message is None:
        raise AssertionError(
            f"в пакете нет сообщения с маркером {CHART_MARKER!r} — формат изменился"
        )
    head, separator, _ = chart_message.partition(QUESTION_MARKER)
    if not separator:
        raise AssertionError(
            f"в сообщении карты нет маркера {QUESTION_MARKER!r} — формат изменился"
        )
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


# ── Критерий (в): якорь системной половины пакета (S3b-08) ──────────────────


class TestSystemPromptAnchor:
    """Правка промптов обязана ронять набор, а не проходить молча."""

    def test_system_prompt_matches_anchor(self):
        """SYSTEM_PROMPT — дословно как в якоре."""
        assert SYSTEM_PROMPT == ANCHOR_SYSTEM_PROMPT

    def test_normal_category_has_no_addendum(self):
        """Обычный вопрос: системный промпт без аддендума."""
        messages = build_messages(GOLDEN_QUESTION, CLEAN_CHART, GOLDEN_PRECISION)
        assert messages[0]["content"] == ANCHOR_SYSTEM_PROMPT

    @pytest.mark.parametrize(
        ("question", "addendum_constant", "addendum_anchor"),
        [
            (
                "У меня болит поясница, что это значит?",
                SAFETY_ADDENDUM_MEDICAL,
                ANCHOR_ADDENDUM_MEDICAL,
            ),
            ("Не хочу жить", SAFETY_ADDENDUM_CRISIS, ANCHOR_ADDENDUM_CRISIS),
            (
                "Стоит ли вложить в крипту?",
                SAFETY_ADDENDUM_FINANCIAL,
                ANCHOR_ADDENDUM_FINANCIAL,
            ),
        ],
    )
    def test_safety_addendum_matches_anchor(self, question, addendum_constant, addendum_anchor):
        """Каждый аддендум безопасности зафиксирован дословно и попадает в пакет."""
        assert addendum_constant == addendum_anchor
        messages = build_messages(question, CLEAN_CHART, GOLDEN_PRECISION)
        assert messages[0]["content"] == ANCHOR_SYSTEM_PROMPT + "\n\n" + addendum_anchor


# ── Критерий (а): боевой путь generate_response (S3b-08) ─────────────────────

# Ответ-заглушка: проходит validate_output — все пять секций и длина от 200.
VALID_LLM_RESPONSE = (
    "🔮 Западная астрология\n"
    "Луна в Скорпионе в третьем доме даёт глубину и перемены, "
    "Солнце в Овне в одиннадцатом доме поддерживает инициативу.\n"
    "🪷 Ведическая астрология\n"
    "Луна в Скорпионе, накшатра Пурва Пудар, владыка — Дхарма, "
    "текущая Махадаша Луны.\n"
    "🐉 Китайская астрология\n"
    "Год ДиньХай — вода, ян; дневной ствол Гэнь — дерево, инь.\n"
    "🔢 Нумерология\n"
    "Число жизненного пути 7, число дня рождения 23, сильные позиции 1 и 3.\n"
    "✨ Вывод Луноры\n"
    "aligned — системы сходятся в указании на период перемен."
)

# Четыре категории вопроса — по одной на каждую ветку сборки.
CATEGORY_QUESTIONS = [
    (GOLDEN_QUESTION, Category.NORMAL, None),
    ("У меня болит поясница, что это значит?", Category.MEDICAL, SAFETY_ADDENDUM_MEDICAL),
    ("Не хочу жить", Category.CRISIS, SAFETY_ADDENDUM_CRISIS),
    ("Стоит ли вложить в крипту?", Category.FINANCIAL, SAFETY_ADDENDUM_FINANCIAL),
]


class _StubLLM:
    """Заглушка сетевого вызова: запоминает пакет и отдаёт валидный ответ."""

    def __init__(self, response: str):
        self.response = response
        self.calls: list[list[dict]] = []

    async def __call__(self, messages: list[dict]) -> str:
        self.calls.append(deepcopy(messages))
        return self.response


class _BuildMessagesSpy:
    """Заглушка сборки: запоминает аргументы вызова и зовёт оригинал."""

    def __init__(self, original: Callable[..., list[dict]]):
        self.original = original
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs) -> list[dict]:
        self.calls.append((args, kwargs))
        return self.original(*args, **kwargs)


class TestGenerateResponseCall:
    """Боевой путь: `generate_response` собирает пакет правильно."""

    def test_stub_response_passes_validation(self):
        """Ответ-заглушка обязан проходить валидацию — иначе будут повторы вызова."""
        valid, reason = validate_output(VALID_LLM_RESPONSE)
        assert valid, reason

    @pytest.mark.parametrize(("question", "category", "addendum"), CATEGORY_QUESTIONS)
    def test_generate_response_builds_package_as_expected(
        self, monkeypatch, question, category, addendum
    ):
        stub = _StubLLM(VALID_LLM_RESPONSE)
        spy = _BuildMessagesSpy(llm_client.build_messages)
        monkeypatch.setattr(llm_client, "_call_llm", stub)
        monkeypatch.setattr(llm_client, "build_messages", spy)

        answer, returned_category = asyncio.run(
            generate_response(question, CLEAN_CHART, GOLDEN_PRECISION, GOLDEN_HISTORY)
        )

        # 1. Сборка вызвана ровно один раз и с теми аргументами, что ожидаются.
        assert len(spy.calls) == 1
        args, kwargs = spy.calls[0]
        bound = inspect.signature(build_messages).bind(*args, **kwargs)
        bound.apply_defaults()
        assert bound.arguments["question"] == question
        assert bound.arguments["chart_data"] == CLEAN_CHART
        assert bound.arguments["precision"] == GOLDEN_PRECISION
        assert bound.arguments["history"] == GOLDEN_HISTORY
        assert bound.arguments["category"] == category

        # 2. Категория, выданная наружу, — та же, что ушла в сборку.
        assert returned_category == category

        # 3. Перехваченный пакет: аддендум безопасности на месте, ответ принят.
        assert len(stub.calls) == 1
        assert answer == VALID_LLM_RESPONSE
        payload = stub.calls[0]
        expected_system = SYSTEM_PROMPT if addendum is None else SYSTEM_PROMPT + "\n\n" + addendum
        assert payload[0] == {"role": "system", "content": expected_system}

        # 4. История на месте; карта и вопрос — в своём сообщении.
        assert payload[1:3] == GOLDEN_HISTORY
        assert payload[-1]["content"].startswith(CHART_MARKER)
        assert payload[-1]["content"].endswith(f"## Вопрос\n{question}")


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

    @pytest.mark.parametrize(("kind", "value"), PII_OUTSIDE_MARKERS)
    def test_general_patterns_catch_pii_outside_markers(self, kind, value):
        """Обобщённый слой детекции ловит ПДн, которых нет среди маркеров фикстуры.

        Значения подобраны так, чтобы маркерный слой их не видел: если такой ПДн
        находится — работает именно регулярка.
        """
        assert value not in PII_MARKERS.values()
        chart = deepcopy(CLEAN_CHART)
        chart["western"]["planets"][0]["name"] = value
        messages = build_messages(GOLDEN_QUESTION, chart, GOLDEN_PRECISION)
        assert find_personal_data(messages) == [kind]

    def test_hostile_history_does_not_hide_chart_data(self):
        """«## Вопрос» в реплике пользователя не отключает проверку данных карты."""
        chart = deepcopy(CLEAN_CHART)
        chart["western"]["planets"][0]["name"] = PII_FULL_NAME
        messages = build_messages(GOLDEN_QUESTION, chart, GOLDEN_PRECISION, HOSTILE_HISTORY)
        assert "фио" in find_personal_data(messages)

    def test_hostile_history_user_words_are_not_flagged(self):
        """Слова пользователя в истории не проверяются — даже с маркером вопроса."""
        messages = build_messages(GOLDEN_QUESTION, CLEAN_CHART, GOLDEN_PRECISION, HOSTILE_HISTORY)
        assert find_personal_data(messages) == []
