"""Форма запроса `_call_llm` к модели (хвост S3b → фикс рантайма).

Замер S3b вскрыл: у Claude 5.5 «мышление» не выключается и тарифицируется как выход;
при `max_tokens=1000` оно съедало весь бюджет → finish_reason=length, content=None —
пустой ответ в чате/прогнозе. Фикс: max_tokens из конфига (запас) + минимальный
ризонинг (effort=low), и None-ответ не роняет вызов. Эти тесты фиксируют контракт.
"""

import asyncio

import httpx

from lunora.llm import client as llm_client


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Записывает тело запроса и отдаёт заранее заданный ответ, без сети."""

    captured: dict = {}

    def __init__(self, payload, *args, **kwargs):
        self._payload = payload

    def _bind(self, payload):
        self._payload = payload
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeAsyncClient.captured = dict(json or {})
        return _FakeResponse(self._payload)


def _patch_network(monkeypatch, response_payload):
    monkeypatch.setattr(llm_client.settings, "llm_api_key", "test-key", raising=False)

    def _factory(*args, **kwargs):
        return _FakeAsyncClient(response_payload)

    monkeypatch.setattr(httpx, "AsyncClient", _factory)


_OK_PAYLOAD = {"choices": [{"message": {"content": "ответ"}}]}
_MESSAGES = [
    {"role": "system", "content": "Ты — Лунора."},
    {"role": "user", "content": "Вопрос без ПДн."},
]


def test_request_carries_max_tokens_and_reasoning(monkeypatch):
    """Тело запроса несёт max_tokens из конфига и минимальный ризонинг."""
    _patch_network(monkeypatch, _OK_PAYLOAD)
    monkeypatch.setattr(llm_client.settings, "llm_max_tokens", 3000, raising=False)
    monkeypatch.setattr(llm_client.settings, "llm_reasoning_effort", "low", raising=False)

    out = asyncio.run(llm_client._call_llm(list(_MESSAGES)))

    assert out == "ответ"
    body = _FakeAsyncClient.captured
    assert body["max_tokens"] == 3000
    assert body["reasoning"] == {"effort": "low"}


def test_max_tokens_not_hardcoded_to_1000(monkeypatch):
    """Регресс: лимит не зашит в 1000 (из-за чего мышление Claude 5.5 рубило ответ)."""
    _patch_network(monkeypatch, _OK_PAYLOAD)
    monkeypatch.setattr(llm_client.settings, "llm_max_tokens", 4096, raising=False)
    monkeypatch.setattr(llm_client.settings, "llm_reasoning_effort", "low", raising=False)

    asyncio.run(llm_client._call_llm(list(_MESSAGES)))
    assert _FakeAsyncClient.captured["max_tokens"] == 4096


def test_empty_reasoning_effort_omits_field(monkeypatch):
    """Пустой effort → поле reasoning не слать (модели/провайдеры без ризонинга)."""
    _patch_network(monkeypatch, _OK_PAYLOAD)
    monkeypatch.setattr(llm_client.settings, "llm_reasoning_effort", "", raising=False)

    asyncio.run(llm_client._call_llm(list(_MESSAGES)))
    assert "reasoning" not in _FakeAsyncClient.captured


def test_none_content_does_not_crash(monkeypatch):
    """content=None (ответ обрезан на лимите) → пустая строка, а не TypeError."""
    _patch_network(monkeypatch, {"choices": [{"message": {"content": None}}]})
    monkeypatch.setattr(llm_client.settings, "llm_reasoning_effort", "low", raising=False)

    out = asyncio.run(llm_client._call_llm(list(_MESSAGES)))
    assert out == ""
