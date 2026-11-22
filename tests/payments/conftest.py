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
import glob
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import uuid
from collections.abc import AsyncIterator, Iterator
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


def _pg_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    cands = sorted(glob.glob(f"/usr/lib/postgresql/*/bin/{name}"))
    return cands[-1] if cands else None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _unavailable(reason: str):
    if os.environ.get("LUNORA_REQUIRE_PG") == "1":
        pytest.fail(f"PostgreSQL обязателен (LUNORA_REQUIRE_PG=1): {reason}", pytrace=False)
    pytest.skip(f"нет PostgreSQL для тестов оплаты: {reason}")


@pytest.fixture(scope="session")
def pg_dsn() -> Iterator[str]:
    dsn = os.environ.get("LUNORA_TEST_PG_DSN")
    if dsn:
        yield dsn
        return

    initdb, pg_ctl = _pg_bin("initdb"), _pg_bin("pg_ctl")
    if not (initdb and pg_ctl):
        _unavailable("initdb/pg_ctl не найдены и LUNORA_TEST_PG_DSN не задан")

    as_root = os.geteuid() == 0
    prefix: list[str] = []
    if as_root:
        runuser = shutil.which("runuser")
        if not runuser:
            _unavailable("запуск под root без runuser")
        prefix = [runuser, "-u", "postgres", "--"]

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="lunora-pg-"))
    data = tmp / "data"
    if as_root:
        shutil.chown(tmp, "postgres")
    port = _free_port()
    run = lambda args: subprocess.run(  # noqa: E731
        prefix + args, check=True, capture_output=True, text=True
    )
    try:
        run([initdb, "-D", str(data), "-A", "trust", "-U", "postgres", "-E", "UTF8"])
        run(
            [
                pg_ctl, "-D", str(data), "-w", "-l", str(tmp / "pg.log"), "-o",
                f"-p {port} -k {tmp} -c listen_addresses=127.0.0.1 -c fsync=off",
                "start",
            ]
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - среда без PG
        _unavailable(f"кластер не поднялся: {exc.stderr.strip()[:300]}")
    try:
        subprocess.run(
            prefix + [_pg_bin("createdb") or "createdb", "-h", "127.0.0.1", "-p", str(port),
                      "-U", "postgres", "lunora_test"],
            check=True, capture_output=True, text=True,
        )
        yield f"postgresql+asyncpg://postgres@127.0.0.1:{port}/lunora_test"
    finally:
        subprocess.run(prefix + [pg_ctl, "-D", str(data), "-m", "immediate", "stop"],
                       capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def migrated_dsn(pg_dsn: str) -> str:
    """Схема — настоящая миграция (alembic upgrade head) на чистой базе."""
    env = {**os.environ, "LUNORA_DATABASE_URL": pg_dsn}
    for cmd in (["downgrade", "base"], ["upgrade", "head"]):
        res = subprocess.run(
            [sys.executable, "-m", "alembic", *cmd], cwd=ROOT, env=env,
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            pytest.fail(f"alembic {' '.join(cmd)}: {res.stderr[-2000:]}", pytrace=False)
    return pg_dsn


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
