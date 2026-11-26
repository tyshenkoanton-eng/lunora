"""S3b-09: приватность пакета портрета, уходящего в модель (152-ФЗ).

Второй путь, который уходит в модель: портрет (`GET /api/portrait/{user_id}`).
Пакет портрета — системный промпт `PORTRAIT_SYSTEM_PROMPT` и один промпт
пользователя, собранный `build_portrait_prompt(blocks, chart_data)`.

Проверяем ровно одно: в пакете портрета нет персональных данных — ФИО, даты и
места рождения, города, `user_id`, Telegram id. И отдельно — что пакет не пуст:
в нём есть тексты интерпретаций планет, год зверя, стихия дневного мастера и
число жизненного пути. Без второй проверки первая прошла бы вхолостую.

Продуктовый код не меняем: тест фиксирует поведение текущей сборки пакета.
Все данные в фикстурах вымышленные.
"""

import re
import types
import uuid
from copy import deepcopy

import httpx
import pytest

from lunora.api import routes
from lunora.interpret.planets import PLANET_INTERPRETATIONS
from lunora.interpret.portrait import (
    PORTRAIT_SYSTEM_PROMPT,
    build_interpretation_blocks,
    build_portrait_prompt,
)
from lunora.llm import client as llm_client

# ── ПДн: значения-маркеры (вымышленные) ────────────────────────────────────

PII_SURNAME = "Соколова"
PII_GIVEN = "Анна"
PII_PATRONYMIC = "Дмитриевна"
PII_FULL_NAME = f"{PII_SURNAME} {PII_GIVEN} {PII_PATRONYMIC}"
PII_BIRTH_DATE = "1991-07-14"
PII_BIRTH_CITY = "Казань"
PII_USER_ID = "22222222-3333-4444-8555-666666666666"
PII_TELEGRAM_ID = "9051122334"

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

# ── Карта: градусы, знаки, дома и тексты интерпретаций ─────────────────────

CLEAN_CHART = {
    "western": {
        "planets": [
            {
                "name": "Sun",
                "longitude": 15.2,
                "sign": "Aries",
                "degree_in_sign": 15.2,
                "house": 11,
                "stability": "stable",
            },
            {
                "name": "Moon",
                "longitude": 223.42,
                "sign": "Scorpio",
                "degree_in_sign": 13.42,
                "house": 3,
                "stability": "stable",
            },
            {
                "name": "Venus",
                "longitude": 310.1,
                "sign": "Aquarius",
                "degree_in_sign": 10.1,
                "house": 7,
                "stability": "stable",
            },
            {
                "name": "Mercury",
                "longitude": 118.0,
                "sign": "Scorpio",
                "degree_in_sign": 28.0,
                "house": 3,
                "stability": "stable",
            },
            {
                "name": "Mars",
                "longitude": 45.0,
                "sign": "Taurus",
                "degree_in_sign": 15.0,
                "house": 2,
                "stability": "stable",
            },
            {
                "name": "Jupiter",
                "longitude": 210.0,
                "sign": "Libra",
                "degree_in_sign": 0.5,
                "house": 9,
                "stability": "stable",
            },
            {
                "name": "Saturn",
                "longitude": 288.0,
                "sign": "Capricorn",
                "degree_in_sign": 18.0,
                "house": 5,
                "stability": "stable",
            },
        ],
        "aspects": [
            {
                "planet1": "Mars",
                "planet2": "Venus",
                "aspect_type": "соединение",
                "angle": 0.0,
                "orb": 1.1,
            },
            {
                "planet1": "Sun",
                "planet2": "Jupiter",
                "aspect_type": "квадрат",
                "angle": 90.0,
                "orb": 2.4,
            },
        ],
    },
    "vedic": {
        "planets": [
            {"name": "Moon", "sign": "Scorpio", "degree_in_sign": 13.42},
            {"name": "Sun", "sign": "Aries", "degree_in_sign": 15.2},
        ],
        "moon_nakshatra": {"name": "Пурва Пудар", "pada": 2, "lord": "Дхарма"},
        "dasha_periods": [
            {"planet": "Moon", "start_year": 2016.0, "end_year": 2026.0, "years": 10.0},
            {"planet": "Mars", "start_year": 2026.0, "end_year": 2036.0, "years": 10.0},
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
# которые читает сборка пакета (см. тест чувствительности детектора: там ПДн
# подкладываются именно в читаемые ключи).
IDENTITY_FIELDS = {
    "user_id": PII_USER_ID,
    "telegram_id": PII_TELEGRAM_ID,
    "name": PII_FULL_NAME,
    "birth_date": PII_BIRTH_DATE,
    "birth_city": PII_BIRTH_CITY,
}

# Строка интерпретации планеты в промпте портрета: «**<планета> в <знак>**: <текст>».
PLANET_LINE_RE = re.compile(r"^\*\*[^*]+ в [^*]+\*\*: ", re.MULTILINE)


def chart_with_identity(chart: dict) -> dict:
    """Карта с подложенными ПДн в служебных полях.

    Подкладываем ПДн и в корень карты, и в каждый JSONB-блок, и в поля самих
    планет — так ПДн выглядели бы, если бы их положили в карту при сохранении.
    Ключ `name` у планет не трогаем: имя планеты — служебное поле сборки, его
    отдельный тест закрывает.
    """
    planted = deepcopy(chart)
    planted.update(IDENTITY_FIELDS)
    for block in ("western", "vedic", "chinese", "numerology"):
        planted[block].update(IDENTITY_FIELDS)
    for planet in planted["western"]["planets"]:
        planet.update({k: v for k, v in IDENTITY_FIELDS.items() if k != "name"})
    return planted


# ── Вспомогательное ─────────────────────────────────────────────────────────


def portrait_package(chart: dict) -> list[dict]:
    """Пакет портрета так, как его собирает `routes.get_portrait` (routes.py:299-305)."""
    blocks = build_interpretation_blocks(chart)
    prompt = build_portrait_prompt(blocks, chart)
    return [
        {"role": "system", "content": PORTRAIT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]


def package_text(messages: list[dict]) -> str:
    """Весь пакет текстом."""
    return "\n".join(m["content"] for m in messages)


def user_prompt(messages: list[dict]) -> str:
    """Промпт пользователя из пакета портрета."""
    return next(m["content"] for m in messages if m["role"] == "user")


def find_personal_data(messages: list[dict]) -> list[str]:
    """Найти ПДн в пакете портрета. Пустой список — пакет чист.

    Портрет не содержит свободных слов пользователя (в отличие от чата, где
    есть вопрос и история), поэтому проверяется весь пакет целиком.
    """
    text = package_text(messages).casefold()
    found = {kind for kind, value in PII_MARKERS.items() if value.casefold() in text}
    found |= {kind for kind, pattern in PII_PATTERNS.items() if pattern.search(text)}
    return sorted(found)


def chart_row(chart: dict) -> types.SimpleNamespace:
    """Строка `natal_charts`: четыре JSONB-колонки и `user_id` (внешний ключ)."""
    return types.SimpleNamespace(
        id=uuid.UUID(PII_USER_ID),  # фикс авторизации: _authorized_user сверяет user.id
        user_id=uuid.UUID(PII_USER_ID),
        western=chart["western"],
        vedic=chart["vedic"],
        chinese=chart["chinese"],
        numerology=chart["numerology"],
    )


class _FakeScalarResult:
    """Ответ `session.execute(...).scalar_one_or_none()` — без настоящей БД."""

    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, stmt):
        return _FakeScalarResult(self._row)


class _FakeSessionMaker:
    """Замена `async_session()`: асинхронный контекстный менеджер с фейковой сессией."""

    def __init__(self, row):
        self._row = row

    def __call__(self):
        return self

    async def __aenter__(self):
        return _FakeSession(self._row)

    async def __aexit__(self, *exc_info):
        return False


async def call_portrait_route(monkeypatch, row) -> list[dict]:
    """Прогнать `GET /api/portrait/{user_id}` и вернуть пакет, ушедший в модель."""
    captured: dict[str, list[dict]] = {}

    async def fake_call_llm(messages: list[dict]) -> str:
        captured["messages"] = messages
        return "тестовый портрет"

    class _NoNetwork:
        def __init__(self, *args, **kwargs):
            raise AssertionError("портрет не должен ходить в сеть из теста")

    monkeypatch.setattr(httpx, "AsyncClient", _NoNetwork)
    monkeypatch.setattr(llm_client, "_call_llm", fake_call_llm)
    monkeypatch.setattr(routes, "async_session", _FakeSessionMaker(row))
    # Фикс авторизации: маршрут требует telegram_id из подписи; владелец берётся из него.
    response = await routes.get_portrait(uuid.UUID(PII_USER_ID), telegram_id=100_200_300)
    assert response.portrait == "тестовый портрет"
    return captured["messages"]


# ── Критерий (а): в пакете портрета нет ПДн ─────────────────────────────────


class TestPortraitPackagePrivacy:
    def test_clean_chart_package_has_no_personal_data(self):
        """Карта с градусами, знаками, домами и текстами — в пакете нет ПДн."""
        assert find_personal_data(portrait_package(CLEAN_CHART)) == []

    def test_card_with_identity_fields_package_has_no_personal_data(self):
        """ПДн в служебных полях карты не должны доехать до пакета портрета."""
        chart = chart_with_identity(CLEAN_CHART)
        assert find_personal_data(portrait_package(chart)) == []

    def test_chart_stored_interpretation_text_does_not_reach_package(self):
        """Текст интерпретации берётся из кода, а не из карты.

        Если сборка когда-нибудь начнёт брать текст из карты, сохранённый там
        текст (а с ним и ПДн) доедет до модели — тест обязан покраснеть.
        """
        chart = deepcopy(CLEAN_CHART)
        chart["western"]["planets"][0]["text"] = PII_FULL_NAME
        package = portrait_package(chart)
        assert find_personal_data(package) == []
        assert PLANET_INTERPRETATIONS["Sun"]["Aries"] in user_prompt(package)

    @pytest.mark.parametrize("field", ["name", "sign"])
    def test_unknown_planet_position_drops_block_and_keeps_pii_out(self, field):
        """Неизвестные имя или знак планеты → блок отброшен, ПДн не доезжают."""
        chart = deepcopy(CLEAN_CHART)
        chart["western"]["planets"][0][field] = PII_FULL_NAME
        blocks = build_interpretation_blocks(chart)
        assert len(blocks) == 4
        assert find_personal_data(portrait_package(chart)) == []


class TestPortraitRoutePrivacy:
    """Тот же пакет, но собранный настоящим маршрутом `GET /api/portrait/{user_id}`."""

    async def test_route_package_has_no_personal_data(self, monkeypatch):
        """Чистая карта: пакет, ушедший из маршрута в модель, без ПДн."""
        messages = await call_portrait_route(monkeypatch, chart_row(CLEAN_CHART))
        assert find_personal_data(messages) == []

    async def test_route_package_has_no_personal_data_from_card(self, monkeypatch):
        """ПДн в карте и `user_id` строки не должны доехать до пакета портрета."""
        row = chart_row(chart_with_identity(CLEAN_CHART))
        messages = await call_portrait_route(monkeypatch, row)
        assert find_personal_data(messages) == []

    async def test_route_package_is_not_empty(self, monkeypatch):
        """Маршрут отдаёт в модель непустой пакет — иначе приватность не проверена."""
        messages = await call_portrait_route(monkeypatch, chart_row(CLEAN_CHART))
        assert len(messages) == 2
        assert messages[0]["content"] == PORTRAIT_SYSTEM_PROMPT
        assert "число жизненного пути — 7" in user_prompt(messages)


# ── Критерий (б): пакет не пуст — в нём тексты планет и число пути ─────────


class TestPortraitPackageContent:
    def test_package_really_contains_planet_texts(self):
        """Пустой пакет тест пропускать не должен: тексты планет обязаны быть."""
        blocks = build_interpretation_blocks(CLEAN_CHART)
        prompt = user_prompt(portrait_package(CLEAN_CHART))
        # 5 планет с интерпретациями; Юпитер и Сатурн в PLANET_INTERPRETATIONS
        # не описаны — их блоки отбрасываются сборкой.
        assert len(blocks) == 5
        assert len(PLANET_LINE_RE.findall(prompt)) == 5
        for block in blocks:
            assert f"**{block['planet_ru']} в {block['sign_ru']}**: {block['text']}" in prompt

    def test_package_contains_canonical_interpretations(self):
        """Тексты в пакете — канонические, из `interpret/planets.py`."""
        prompt = user_prompt(portrait_package(CLEAN_CHART))
        signs = {
            planet["name"]: planet["sign"]
            for planet in CLEAN_CHART["western"]["planets"]
        }
        for planet in ("Sun", "Moon", "Venus", "Mercury", "Mars"):
            assert PLANET_INTERPRETATIONS[planet][signs[planet]] in prompt

    def test_package_contains_zodiac_and_numerology(self):
        """Год зверя, стихия дневного мастера и число жизненного пути — в пакете."""
        prompt = user_prompt(portrait_package(CLEAN_CHART))
        assert "год Крыса" in prompt
        assert "стихия дневного мастера — Дерево" in prompt
        assert "число жизненного пути — 7" in prompt

    def test_package_keeps_planet_order_of_the_chart(self):
        """Порядок блоков — порядок планет в карте (тексты не перемешаны)."""
        blocks = build_interpretation_blocks(CLEAN_CHART)
        prompt = user_prompt(portrait_package(CLEAN_CHART))
        positions = [prompt.index(f"**{b['planet_ru']} в {b['sign_ru']}**") for b in blocks]
        assert positions == sorted(positions)


# ── Критерий (в): чувствительность проверки ─────────────────────────────────


class TestDetectorSensitivity:
    @pytest.mark.parametrize("kind", sorted(PII_MARKERS))
    def test_detector_catches_personal_data_that_reached_the_package(self, kind):
        """Чувствительность: ПДн, дошедшие до пакета портрета, обязаны быть найдены.

        Подкладываем маркер в `chinese.year_animal` — значение, которое сборка
        подставляет в промпт дословно. Это ровно тот путь, которым ПДн доедут
        до модели, если карта или сборка изменятся.
        """
        chart = deepcopy(CLEAN_CHART)
        chart["chinese"]["year_animal"] = PII_MARKERS[kind]
        package = portrait_package(chart)
        assert kind in find_personal_data(package)
