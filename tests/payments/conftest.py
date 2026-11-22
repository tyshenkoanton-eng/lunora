"""Фикстуры G17-S3a: настоящая PostgreSQL + фейковая сессия Bot API (§2.4b, S1–S5).

PostgreSQL:
- ``LUNORA_TEST_PG_DSN`` (``postgresql+asyncpg://…``) — готовый сервер, база будет очищена;
- иначе — временный кластер ``initdb``/``pg_ctl`` (под root — от пользователя ``postgres``).
Схема — ``alembic upgrade head``: гарантии S1 (уникальные индексы) проверяются на той же
миграции, что уйдёт в прод, а не на ``metadata.create_all``.

Нет PostgreSQL → тесты пропускаются; при ``LUNORA_REQUIRE_PG=1`` (``make slice-check``) —
падают (fail closed: доказательство S1–S5 без настоящей БД не засчитывается).

Bot API: настоящий ``aiogram.Bot`` и ``Dispatcher.feed_update``; подменена только HTTP-сессия
(``FakeTelegramSession``), которая записывает вызовы методов и ведёт журнал Stars.
"""

from __future__ import annotations

import asyncio
import pathlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerPreCheckoutQuery,
    CreateInvoiceLink,
    GetStarTransactions,
    RefundStarPayment,
    TelegramMethod,
)
from aiogram.types import (
    Chat,
    Message,
    PreCheckoutQuery,
    RefundedPayment,
    StarTransaction,
    StarTransactions,
    SuccessfulPayment,
    TransactionPartnerUser,
    Update,
    User,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
STAR_TABLES = (
    "star_refunds",
    "star_grants",
    "star_payments",
    "star_processed_events",
    "star_orders",
)
USER_ID = 700_000_001  # синтетический Telegram id, не ПДн
OTHER_USER_ID = 700_000_002


# --------------------------------------------------------------------------- PostgreSQL
# Кластер PostgreSQL + схема (`pg_dsn`, `migrated_dsn`) — общие фикстуры из tests/conftest.py.


@pytest.fixture
async def session_factory(migrated_dsn: str) -> AsyncIterator[Any]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(migrated_dsn, pool_size=10)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {', '.join(STAR_TABLES)} CASCADE"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


# --------------------------------------------------------------------------- Bot API


class FakeTelegramSession(BaseSession):
    """Сессия Bot API без сети: пишет вызовы, ведёт журнал Stars как Telegram.

    ``refundStarPayment`` по уже возвращённому платежу отвечает ошибкой
    ``CHARGE_ALREADY_REFUNDED`` — так ведёт себя Bot API.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.ledger: list[StarTransaction] = []  # новые — в начале (как getStarTransactions)
        self.refunded: set[str] = set()
        self.fail_next: dict[type, Exception] = {}
        self.refund_delay = 0.0

    def calls_of(self, kind: type) -> list[Any]:
        return [c for c in self.calls if isinstance(c, kind)]

    async def close(self) -> None:
        return None

    async def stream_content(self, *a: Any, **kw: Any):  # pragma: no cover
        raise NotImplementedError
        yield b""

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ):
        self.calls.append(method)
        exc = self.fail_next.pop(type(method), None)
        if exc is not None:
            raise exc
        if isinstance(method, AnswerPreCheckoutQuery):
            return True
        if isinstance(method, CreateInvoiceLink):
            return f"https://t.me/$fake_{method.payload[-8:]}"
        if isinstance(method, RefundStarPayment):
            if self.refund_delay:
                await asyncio.sleep(self.refund_delay)
            if method.telegram_payment_charge_id in self.refunded:
                raise TelegramBadRequest(
                    method=method, message="Bad Request: CHARGE_ALREADY_REFUNDED"
                )
            self.refunded.add(method.telegram_payment_charge_id)
            return True
        if isinstance(method, GetStarTransactions):
            off = method.offset or 0
            lim = method.limit or 100
            return StarTransactions(transactions=self.ledger[off : off + lim])
        raise AssertionError(f"неожиданный вызов Bot API: {type(method).__name__}")

    # --- журнал Stars ------------------------------------------------------------------
    def ledger_incoming(self, charge_id: str, user_id: int, amount: int, payload: str) -> None:
        self.ledger.insert(
            0,
            StarTransaction(
                id=charge_id, amount=amount, date=datetime.now(UTC),
                source=TransactionPartnerUser(
                    transaction_type="invoice_payment",
                    user=User(id=user_id, is_bot=False, first_name="Тест"),
                    invoice_payload=payload,
                ),
            ),
        )

    def ledger_refund(self, charge_id: str, user_id: int, amount: int) -> None:
        self.ledger.insert(
            0,
            StarTransaction(
                id=charge_id, amount=amount, date=datetime.now(UTC),
                receiver=TransactionPartnerUser(
                    transaction_type="invoice_payment",
                    user=User(id=user_id, is_bot=False, first_name="Тест"),
                ),
            ),
        )


@pytest.fixture
def tg() -> FakeTelegramSession:
    return FakeTelegramSession()


@pytest.fixture
async def bot(tg: FakeTelegramSession) -> AsyncIterator[Bot]:
    b = Bot(token="42:TEST", session=tg)
    yield b


# --------------------------------------------------------------------------- сервис


@pytest.fixture
def catalog():
    from lunora.payments.catalog import Catalog, StarProduct

    return Catalog(
        [
            StarProduct("spike_smoke", "Проверка оплаты", "1 звезда", price_xtr=1),
            StarProduct("report_full", "Разбор", "Полный разбор", price_xtr=250),
        ]
    )


@pytest.fixture
def service(session_factory, bot, catalog):
    from lunora.payments.stars import AiogramStarsApi, StarsService

    return StarsService(session_factory, AiogramStarsApi(bot), catalog)


@pytest.fixture
def dp(service) -> Dispatcher:
    from lunora.payments.telegram import build_router

    d = Dispatcher()
    d.include_router(build_router(service))
    return d


# --------------------------------------------------------------------------- обновления


_update_seq = iter(range(1, 10**9))


def tg_user(user_id: int = USER_ID) -> User:
    return User(id=user_id, is_bot=False, first_name="Тест")


def pre_checkout_update(payload: str, amount: int, currency: str = "XTR",
                        user_id: int = USER_ID) -> Update:
    return Update(
        update_id=next(_update_seq),
        pre_checkout_query=PreCheckoutQuery(
            id=uuid.uuid4().hex, from_user=tg_user(user_id), currency=currency,
            total_amount=amount, invoice_payload=payload,
        ),
    )


def successful_payment_update(payload: str, amount: int, charge_id: str,
                              currency: str = "XTR", user_id: int = USER_ID) -> Update:
    return Update(
        update_id=next(_update_seq),
        message=Message(
            message_id=next(_update_seq), date=datetime.now(UTC),
            chat=Chat(id=user_id, type="private"), from_user=tg_user(user_id),
            successful_payment=SuccessfulPayment(
                currency=currency, total_amount=amount, invoice_payload=payload,
                telegram_payment_charge_id=charge_id, provider_payment_charge_id="",
            ),
        ),
    )


def refunded_payment_update(payload: str, amount: int, charge_id: str,
                            user_id: int = USER_ID) -> Update:
    return Update(
        update_id=next(_update_seq),
        message=Message(
            message_id=next(_update_seq), date=datetime.now(UTC),
            chat=Chat(id=user_id, type="private"), from_user=tg_user(user_id),
            refunded_payment=RefundedPayment(
                total_amount=amount, invoice_payload=payload, telegram_payment_charge_id=charge_id,
            ),
        ),
    )


async def counts(session_factory) -> dict[str, int]:
    from sqlalchemy import text

    async with session_factory() as s:
        out = {}
        for t in STAR_TABLES:
            out[t] = (await s.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one()
        return out
