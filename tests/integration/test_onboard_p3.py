"""Сквозной онбординг на настоящей PostgreSQL (G17-S2f): F02 (спорные пояса через API →
хранимую модель), F07 (полное происхождение в calculation_runs), В-1 (отказ на латиницу).

Схема — `alembic upgrade head` (миграция 003), как уйдёт в прод. Нет PostgreSQL → skip;
при LUNORA_REQUIRE_PG=1 (make slice-check) — fail.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from lunora.api import routes
from lunora.api.schemas import NamePayload, OnboardRequest
from lunora.models.chart import CalculationRun, NatalChart
from lunora.models.user import User

_APP_TABLES = ("calculation_runs", "natal_charts", "messages", "threads", "users")


@pytest.fixture
async def session_factory(migrated_dsn: str, monkeypatch) -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine(migrated_dsn)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(_APP_TABLES)} CASCADE"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(routes, "async_session", factory)
    yield factory
    await engine.dispose()


def _req(**kw) -> OnboardRequest:
    base = dict(
        telegram_id=700_100_001, name="Иван", birth_date="1985-06-01", birth_time="12:00",
        birth_time_precision="exact", birth_city="Джизак", birth_lat=40.1, birth_lon=67.84,
        timezone="Asia/Samarkand", sex="m",
        name_birth=NamePayload(surname="Петров", given="Иван", patronymic="Сергеевич"),
        init_data="stub",
    )
    base.update(kw)
    return OnboardRequest(**base)


async def test_f02_disputed_zone_through_onboard_yields_two_hypotheses(session_factory):
    # Джизак (TZD-001): place_id ведёт к реестру спорных поясов — в провенансе две гипотезы UTC
    resp = await routes.onboard(_req(place_id="geonames:1513886"))
    async with session_factory() as s:
        user = (await s.execute(select(User).where(User.telegram_id == 700_100_001))).scalar_one()
        assert user.place_id == "geonames:1513886"
        assert user.sex == "m" and user.name_surname == "Петров"
        run = (await s.execute(select(CalculationRun))).scalars().first()
    assert run.dispute_id == "TZD-001"
    assert run.place_id == "geonames:1513886"
    assert len(run.provenance["utc_hypotheses"]) == 2
    assert resp.user_id


async def test_f02_tiraspol_region_dispute_through_onboard(session_factory):
    # Приднестровье (TZD-002): правило по региону admin1; окно 1990-05-06…1991-03-30
    await routes.onboard(_req(
        telegram_id=700_100_002, birth_date="1990-09-01", birth_city="Тирасполь",
        birth_lat=46.84, birth_lon=29.61, timezone="Europe/Chisinau",
        place_id="geonames:617239", region="geonames-admin1:MD.58",
    ))
    async with session_factory() as s:
        run = (await s.execute(select(CalculationRun))).scalars().first()
    assert run.dispute_id == "TZD-002"
    assert len(run.provenance["utc_hypotheses"]) == 2


async def test_f07_calculation_run_records_full_provenance(session_factory):
    await routes.onboard(_req(birth_time_precision="approximate_60"))
    async with session_factory() as s:
        run = (await s.execute(select(CalculationRun))).scalars().first()
    prov = run.provenance
    assert run.timezone == "Asia/Samarkand"
    assert run.precision == "approximate_60"
    assert run.tolerance_minutes == 60
    assert prov["tz_build"]  # версия IANA
    assert prov["ephemeris"]  # SHA/версии эфемерид
    assert set(prov["engine_versions"]) == {"western", "vedic", "bazi", "numerology"}
    # F07/ARCH §3.2: input_hash — HMAC (не голый sha256 входа)
    import hashlib
    naive = hashlib.sha256(
        f"{run.chart_id}".encode()
    ).hexdigest()
    assert run.input_hash != naive and len(run.input_hash) == 64


async def test_v1_latin_name_onboard_rejected_and_chart_not_saved(session_factory):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await routes.onboard(_req(
            telegram_id=700_100_003,
            name_birth=NamePayload(surname="Smith", given="John", patronymic=None),
        ))
    assert exc.value.status_code == 422
    detail = exc.value.detail
    # В-1: отказ несёт человекочитаемое предупреждение, привязанное к полю ввода,
    # а не только машинный код — «введите ФИО кириллицей».
    assert detail["error"] == "name_rejected"
    assert detail["code"] == "latin_not_supported"
    assert detail["field"] == "surname"
    assert "кириллиц" in detail["message"].lower()
    assert "фамилия" in detail["message"].lower()
    async with session_factory() as s:
        q = select(User).where(User.telegram_id == 700_100_003)
        users = (await s.execute(q)).scalars().all()
        charts = (await s.execute(select(NatalChart))).scalars().all()
    assert users == []  # карта и пользователь не созданы
    assert charts == []


async def test_name_contour_stored_in_chart(session_factory):
    await routes.onboard(_req(telegram_id=700_100_004,
                              name_birth=NamePayload(surname="Куликов", given="Роман",
                                                     patronymic="Николаевич")))
    async with session_factory() as s:
        chart = (await s.execute(select(NatalChart))).scalars().first()
    nn = chart.numerology["name_numbers"]
    assert nn["expression"]["value"] is not None
    assert nn["maturity"]["value"] is not None
