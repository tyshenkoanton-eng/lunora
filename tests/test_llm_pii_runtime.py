"""Рантайм-страж ПДн (152-ФЗ): активная проверка пакета ПЕРЕД отправкой в модель.

Регресс-тесты сборки (`test_llm_privacy`, `test_llm_portrait_privacy`) фиксируют,
что пакет собирается чистым. Здесь — активный предохранитель в рантайме: единая
точка перед сетевым вызовом (`_call_llm`), которая находит ПДн в служебной части
пакета и, если находит, НЕ отправляет (fail-closed). Защита в глубину: даже если
сборка однажды начнёт пропускать ПДн, в сеть он не уйдёт.

Что проверяем:
1. Детектор `find_pii` ловит e-mail и российский мобильный телефон (их не было в
   закрытом списке прошлого детектора), а также прежние формы (ISO/ДД.ММ.ГГГГ дата,
   uuid, telegram-подобный id).
2. Детектор НЕ краснеет на служебном тексте: телефон доверия 8-800-… в аддендуме
   кризиса не должен приниматься за ПДн (иначе страж рубил бы каждый кризисный
   вопрос).
3. `service_text` вычленяет служебную часть пакета (системный промпт + данные
   карты) из обоих путей — чат (`build_messages`) и портрет — и НЕ включает слова
   пользователя (вопрос, история).
4. `guard_package` поднимает `PiiInPackageError` на грязном пакете и молчит на
   чистом; `_call_llm` зовёт страж ДО сети (fail-closed) — при ПДн сеть не трогается.

Все данные в фикстурах вымышленные.
"""

import asyncio
from copy import deepcopy

import httpx
import pytest

from lunora.interpret.portrait import PORTRAIT_SYSTEM_PROMPT
from lunora.llm import client as llm_client
from lunora.llm.client import build_messages
from lunora.llm.pii import (
    PiiInPackageError,
    find_pii,
    guard_package,
    service_text,
)

# Чистая карта: только градусы, знаки, дома, текст (повтор минимального набора).
CLEAN_CHART = {
    "western": {
        "planets": [
            {"name": "Луна", "sign": "Скорпион", "degree_in_sign": 13.42, "house": 3,
             "stability": "stable"},
            {"name": "Солнце", "sign": "Овен", "degree_in_sign": 15.2, "house": 11,
             "stability": "stable"},
        ],
        "aspects": [
            {"planet1": "Марс", "planet2": "Венера", "aspect_type": "соединение",
             "angle": 0.0, "orb": 1.1},
        ],
    },
    "vedic": {
        "planets": [{"name": "Луна", "sign": "Скорпион", "degree_in_sign": 13.42}],
        "moon_nakshatra": {"name": "Пурва Пудар", "pada": 2, "lord": "Дхарма"},
        "dasha_periods": [
            {"planet": "Луна", "start_year": 2016.0, "end_year": 2026.0, "years": 10.0},
        ],
    },
    "chinese": {
        "year_pillar": {"stem": "Динь", "branch": "Хай", "element": "Вода", "yin_yang": "ян"},
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

GOLDEN_QUESTION = "Что мне поставить в фокус на этот месяц?"
CRISIS_QUESTION = "Не хочу жить"  # вытягивает аддендум кризиса с телефоном доверия


# ── 1. Детектор: e-mail и российский телефон (новые) + прежние формы ─────────


class TestFindPii:
    @pytest.mark.parametrize(
        "value",
        [
            "ivanova.maria@example.com",
            "m.ivanova+astro@mail.ru",
            "a_b-c@sub.domain.co",
        ],
    )
    def test_catches_email(self, value):
        assert "e-mail" in find_pii(f"связь: {value}, ещё текст")

    @pytest.mark.parametrize(
        "value",
        [
            "+79161234567",
            "89161234567",
            "+7 916 123-45-67",
            "8 (916) 123-45-67",
            "8-916-123-45-67",
        ],
    )
    def test_catches_russian_mobile(self, value):
        assert "телефон (РФ)" in find_pii(f"мой номер {value} звоните")

    @pytest.mark.parametrize(
        ("value", "kind"),
        [
            ("2003-11-07", "дата (ISO)"),
            ("31.12.1999", "дата (ДД.ММ.ГГГГ)"),
            ("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "uuid"),
            ("987654321", "telegram-подобный id"),
        ],
    )
    def test_keeps_previous_forms(self, value, kind):
        assert kind in find_pii(f"служебное поле: {value}")

    def test_clean_astro_text_is_empty(self):
        """Градусы, годы даш и орбы — не ПДн; детектор молчит."""
        text = (
            "- Луна: 13.42° Скорпион (3 дом)\n"
            "- Текущая Mahadasha: Луна (2016–2026)\n"
            "- Ключевые аспекты: Марс соединение Венера (1.1°)\n"
            "- Число жизненного пути: 7"
        )
        assert find_pii(text) == []

    def test_helpline_is_not_a_phone(self):
        """Телефон доверия 8-800-2000-122 — служебный, не персональный номер.

        8-800 — не мобильный код (мобильные начинаются с 9). Иначе страж рубил бы
        каждый кризисный вопрос, где аддендум содержит этот телефон.
        """
        assert find_pii("Телефон доверия: 8-800-2000-122 (бесплатно).") == []


# ── 2. service_text: служебная часть обоих путей, без слов пользователя ──────


class TestServiceText:
    def test_chat_excludes_question_and_history(self):
        """Чат: вопрос и история исключены, данные карты — в служебной части."""
        history = [
            {"role": "user", "content": "Меня зовут Иванова Мария, пишите на m@ex.com"},
            {"role": "assistant", "content": "Привет!"},
        ]
        messages = build_messages(
            "А мой телефон 8 916 123-45-67 — когда перемены?",
            CLEAN_CHART,
            "exact",
            history,
        )
        service = service_text(messages)
        assert "Иванова Мария" not in service
        assert "m@ex.com" not in service
        assert "123-45-67" not in service
        assert "13.42° Скорпион" in service  # данные карты на месте

    def test_portrait_whole_user_prompt_is_service(self):
        """Портрет: слов пользователя нет, весь промпт — служебный."""
        messages = [
            {"role": "system", "content": PORTRAIT_SYSTEM_PROMPT},
            {"role": "user", "content": "Вот интерпретации: Солнце в Овне — инициатива."},
        ]
        service = service_text(messages)
        assert "Солнце в Овне" in service

    def test_chart_message_found_even_after_retry_appends(self):
        """После дозаписей ретрая сообщение карты всё равно попадает в проверку."""
        messages = build_messages(GOLDEN_QUESTION, CLEAN_CHART, "exact")
        messages.append({"role": "assistant", "content": "черновой ответ"})
        messages.append({"role": "user", "content": "Твой ответ не прошёл валидацию."})
        assert "13.42° Скорпион" in service_text(messages)


# ── 3. guard_package: fail-closed на грязном, тишина на чистом ───────────────


def _poison_chart(value: str) -> dict:
    chart = deepcopy(CLEAN_CHART)
    chart["western"]["planets"][0]["name"] = value
    return chart


class TestGuardPackage:
    def test_clean_chat_package_passes(self):
        guard_package(build_messages(GOLDEN_QUESTION, CLEAN_CHART, "exact"))

    def test_crisis_package_passes_despite_helpline(self):
        """Кризисный вопрос тянет телефон доверия в системный промпт — но это не ПДн."""
        guard_package(build_messages(CRISIS_QUESTION, CLEAN_CHART, "exact"))

    def test_clean_portrait_package_passes(self):
        guard_package([
            {"role": "system", "content": PORTRAIT_SYSTEM_PROMPT},
            {"role": "user", "content": "Вот интерпретации: Солнце в Овне — инициатива."},
        ])

    @pytest.mark.parametrize(
        ("value", "kind"),
        [
            ("ivanova@example.com", "e-mail"),
            ("+79161234567", "телефон (РФ)"),
            ("2003-11-07", "дата (ISO)"),
            ("31.12.1999", "дата (ДД.ММ.ГГГГ)"),
            ("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "uuid"),
            ("987654321", "telegram-подобный id"),
        ],
    )
    def test_pii_in_chart_blocks(self, value, kind):
        with pytest.raises(PiiInPackageError) as exc:
            guard_package(build_messages(GOLDEN_QUESTION, _poison_chart(value), "exact"))
        assert kind in exc.value.kinds

    def test_pii_only_in_user_words_does_not_block(self):
        """ПДн в вопросе и истории пользователя — его слова, страж их пропускает."""
        history = [{"role": "user", "content": "Я Иванова, m@ex.com, +79161234567"}]
        messages = build_messages(
            "Меня зовут Иванова Мария, телефон +79161234567 — когда перемены?",
            CLEAN_CHART,
            "exact",
            history,
        )
        guard_package(messages)  # не поднимает

    def test_pii_in_portrait_prompt_blocks(self):
        with pytest.raises(PiiInPackageError):
            guard_package([
                {"role": "system", "content": PORTRAIT_SYSTEM_PROMPT},
                {"role": "user", "content": "Клиент ivanova@example.com, портрет."},
            ])

    def test_error_names_kinds_not_values(self):
        """В сообщении об ошибке — виды ПДн, не сами значения (не утечь в лог)."""
        with pytest.raises(PiiInPackageError) as exc:
            guard_package(build_messages(GOLDEN_QUESTION, _poison_chart("ivanova@example.com"),
                                         "exact"))
        assert "ivanova@example.com" not in str(exc.value)
        assert "e-mail" in str(exc.value)


# ── 4. _call_llm: страж срабатывает ДО сети (fail-closed) ────────────────────


class TestCallLlmGuards:
    def test_guard_runs_before_network(self, monkeypatch):
        """Грязный пакет: _call_llm поднимает PiiInPackageError и не идёт в сеть.

        httpx.AsyncClient рушится при создании — если бы страж не сработал первым,
        тест упал бы с другой ошибкой. Ключ API намеренно задан, чтобы проверка
        ключа не перехватила управление раньше стража.
        """
        class _NoNetwork:
            def __init__(self, *args, **kwargs):
                raise AssertionError("_call_llm не должен ходить в сеть при ПДн")

        monkeypatch.setattr(httpx, "AsyncClient", _NoNetwork)
        monkeypatch.setattr(llm_client.settings, "llm_api_key", "test-key", raising=False)

        messages = build_messages(GOLDEN_QUESTION, _poison_chart("ivanova@example.com"), "exact")
        with pytest.raises(PiiInPackageError):
            asyncio.run(llm_client._call_llm(messages))

    def test_guard_blocks_even_without_api_key(self, monkeypatch):
        """Fail-closed не зависит от конфига: без ключа страж всё равно рубит ПДн."""
        monkeypatch.setattr(llm_client.settings, "llm_api_key", "", raising=False)
        messages = build_messages(GOLDEN_QUESTION, _poison_chart("+79161234567"), "exact")
        with pytest.raises(PiiInPackageError):
            asyncio.run(llm_client._call_llm(messages))
