"""Сквозная авторизация API на настоящей PostgreSQL (IDOR-фикс).

До фикса GET /api/chart/{user_id}, /api/portrait/{user_id} и POST /api/ask отдавали карту по
любому UUID без проверки — любой мог читать чужую карту и жечь LLM-бюджет. Теперь владелец =
telegram_id из подписанной Telegram initData (заголовок `Authorization: tma <initData>`),
а user_id из пути/тела должен ему принадлежать (иначе 403), без подписи — 401.

Схема — `alembic upgrade head`. Нет PostgreSQL → skip; при LUNORA_REQUIRE_PG=1 — fail.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import lunora.api.auth as auth_mod
from lunora.api import routes
from lunora.api.app import app
from lunora.api.schemas import NamePayload, OnboardRequest
from lunora.models.user import User
from tests.auth_helpers import TEST_BOT_TOKEN, build_init_data

_APP_TABLES = ("calculation_runs", "natal_charts", "messages", "threads", "users")


@pytest.fixture
async def client(migrated_dsn: str, monkeypatch) -> AsyncIterator[httpx.AsyncClient]:
    engine = create_async_engine(migrated_dsn)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(_APP_TABLES)} CASCADE"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(routes, "async_session", factory)
    # Подпись initData проверяется этим токеном; бот не стартует (lifespan не входим).
    monkeypatch.setattr(auth_mod.settings, "bot_token", TEST_BOT_TOKEN)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await engine.dispose()


def _onboard_body(telegram_id: int, **kw) -> dict:
    base = dict(
        telegram_id=telegram_id, name="Иван", birth_date="1985-06-01", birth_time="12:00",
        birth_time_precision="exact", birth_city="Джизак", birth_lat=40.1, birth_lon=67.84,
        timezone="Asia/Samarkand", sex="m",
        name_birth=NamePayload(surname="Петров", given="Иван", patronymic="Сергеевич"),
        init_data="unused-body-field",
    )
    base.update(kw)
    return json.loads(OnboardRequest(**base).model_dump_json())


def _auth(telegram_id: int, **kw) -> dict:
    return {"Authorization": f"tma {build_init_data(telegram_id, **kw)}"}


async def _make_user(client: httpx.AsyncClient, telegram_id: int) -> str:
    r = await client.post(
        "/api/onboard", json=_onboard_body(telegram_id), headers=_auth(telegram_id)
    )
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


async def test_onboard_requires_valid_init_data(client):
    r = await client.post("/api/onboard", json=_onboard_body(700_200_001))
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "missing_auth"


async def test_onboard_bad_signature_rejected(client):
    headers = {"Authorization": f"tma {build_init_data(700_200_001, tamper=True)}"}
    r = await client.post("/api/onboard", json=_onboard_body(700_200_001), headers=headers)
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "bad_signature"


async def test_onboard_body_telegram_id_must_match_signature(client):
    # Тело заявляет чужой telegram_id, подпись — на другого: 403 (анти-спуф).
    r = await client.post(
        "/api/onboard", json=_onboard_body(700_200_999), headers=_auth(700_200_001)
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "telegram_id_mismatch"


async def test_chart_without_auth_is_401(client):
    user_id = await _make_user(client, 700_200_010)
    r = await client.get(f"/api/chart/{user_id}")
    assert r.status_code == 401


async def test_owner_reads_own_chart(client):
    uid = await _make_user(client, 700_200_020)
    r = await client.get(f"/api/chart/{uid}", headers=_auth(700_200_020))
    assert r.status_code == 200
    assert set(r.json()) >= {"western", "vedic", "chinese", "numerology"}


async def test_idor_other_user_chart_forbidden(client):
    victim = await _make_user(client, 700_200_030)
    await _make_user(client, 700_200_031)  # attacker onboarded
    # Атакующий аутентифицирован своей подписью, но просит UUID жертвы → 403, не 200.
    r = await client.get(f"/api/chart/{victim}", headers=_auth(700_200_031))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_owner"


async def test_idor_other_user_portrait_forbidden(client):
    victim = await _make_user(client, 700_200_040)
    await _make_user(client, 700_200_041)
    r = await client.get(f"/api/portrait/{victim}", headers=_auth(700_200_041))
    assert r.status_code == 403


async def test_portrait_without_auth_is_401(client):
    uid = await _make_user(client, 700_200_050)
    r = await client.get(f"/api/portrait/{uid}")
    assert r.status_code == 401


async def test_ask_requires_auth(client):
    uid = await _make_user(client, 700_200_060)
    r = await client.post("/api/ask", json={"user_id": uid, "question": "привет"})
    assert r.status_code == 401


async def test_ask_other_user_forbidden(client):
    victim = await _make_user(client, 700_200_070)
    await _make_user(client, 700_200_071)
    r = await client.post(
        "/api/ask",
        json={"user_id": victim, "question": "чужой вопрос"},
        headers=_auth(700_200_071),
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_owner"


async def test_authenticated_unknown_user_is_404(client):
    # Подпись валидна, но пользователь не онбордился: 404, не раскрываем чужие карты.
    import uuid as _uuid

    some_uuid = str(_uuid.uuid4())
    r = await client.get(f"/api/chart/{some_uuid}", headers=_auth(700_200_080))
    assert r.status_code == 404
    async with routes.async_session() as s:
        row = await s.execute(select(User).where(User.telegram_id == 700_200_080))
        assert row.scalar_one_or_none() is None
