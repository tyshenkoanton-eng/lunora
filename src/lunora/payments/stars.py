"""Адаптер Telegram Stars (TRANSACTIONS-КОНТРАКТЫ §2.4b, D-121).

S1 — подтверждение оплаты = ``successful_payment``; идемпотентность по
     ``telegram_payment_charge_id`` держат уникальные индексы БД (см. ``models``).
S2 — ``check_pre_checkout`` даёт ответ для явного ``answerPreCheckoutQuery`` (роутер в
     ``telegram.py`` отвечает всегда, в т.ч. при сбое).
S3 — цена фиксируется в XTR в момент инвойса (``star_orders.price_xtr``); другая сумма/валюта
     → выдачи нет, ``reconcile_needed``.
S4 — реконсиляция по ``getStarTransactions`` тем же обработчиком, что и обновления.
S5 — возврат ``refundStarPayment`` только полный, один раз; повтор — no-op.

Это не ЮKassa (§2.4a): нет вебхука, нет ``GET`` по платежу, нет ``provider_key``, валюта XTR.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import LabeledPrice, StarTransaction, TransactionPartnerUser
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lunora.payments.catalog import Catalog
from lunora.payments.models import (
    StarGrant,
    StarOrder,
    StarPayment,
    StarProcessedEvent,
    StarRefund,
)

log = logging.getLogger("lunora.payments.stars")

XTR = "XTR"
PAYLOAD_PREFIX = "lunora:v1:"
Source = Literal["update", "reconcile"]

# Тексты для пользователя — на «вы», без внутренностей (S2).
MSG_ORDER_NOT_FOUND = (
    "Не удалось найти этот заказ. Вы можете оформить покупку заново в приложении — "
    "звёзды не списаны."
)
MSG_PRICE_CHANGED = (
    "Сумма или валюта не совпадают с заказом. Вы можете оформить покупку заново — "
    "звёзды не списаны."
)
MSG_ALREADY_PAID = "Этот заказ вы уже оплатили — повторно платить не нужно."
MSG_INTERNAL = (
    "Не получилось проверить заказ. Попробуйте, пожалуйста, ещё раз через минуту — "
    "звёзды у вас не списаны."
)


class ApplyOutcome(StrEnum):
    GRANTED = "granted"  # оплата засчитана, доступ выдан
    DUPLICATE = "duplicate"  # этот charge_id уже учтён — no-op
    MISMATCH = "mismatch"  # сумма/валюта/пользователь ≠ заказ → reconcile_needed, выдачи нет
    PAID_LATE = "paid_late"  # второй платёж на уже оплаченный/закрытый заказ
    UNKNOWN_ORDER = "unknown_order"  # payload не ведёт к нашему заказу


class RefundOutcome(StrEnum):
    REFUNDED = "refunded"
    ALREADY_REFUNDED = "already_refunded"
    NOT_FOUND = "not_found"


class StarsRefundError(RuntimeError):
    """refundStarPayment не подтвердился (сеть/ошибка API): возврат не засчитан, повторяемо."""


@dataclass(frozen=True)
class PaymentSnapshot:
    """Проверенное состояние платежа Stars: из successful_payment или из журнала Stars."""

    telegram_payment_charge_id: str
    telegram_user_id: int
    currency: str
    total_amount: int
    invoice_payload: str


@dataclass(frozen=True)
class Invoice:
    order_id: uuid.UUID
    payload: str
    price_xtr: int
    link: str


@dataclass
class ReconcileReport:
    granted: int = 0
    duplicates: int = 0
    mismatched: int = 0
    paid_late: int = 0
    unknown_order: int = 0
    refunded: int = 0
    ignored: int = 0
    pages: int = 0
    outcomes: list[tuple[str, str]] = field(default_factory=list)


class StarsApi(Protocol):
    async def create_invoice_link(
        self, *, title: str, description: str, payload: str, price_xtr: int
    ) -> str: ...

    async def refund_star_payment(self, *, user_id: int, telegram_payment_charge_id: str) -> None:
        """Возвращает платёж целиком. Уже возвращённый — успех (идемпотентно)."""

    async def get_star_transactions(self, *, offset: int, limit: int) -> list[StarTransaction]: ...


class AiogramStarsApi:
    """Bot API через aiogram. Для смоука в тестовой среде — Bot с ``TelegramAPIServer`` TEST."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def create_invoice_link(
        self, *, title: str, description: str, payload: str, price_xtr: int
    ) -> str:
        # Stars: currency XTR, ровно одна позиция, provider_token пустой (не передаём).
        return await self.bot.create_invoice_link(
            title=title,
            description=description,
            payload=payload,
            currency=XTR,
            prices=[LabeledPrice(label=title, amount=price_xtr)],
        )

    async def refund_star_payment(self, *, user_id: int, telegram_payment_charge_id: str) -> None:
        try:
            await self.bot.refund_star_payment(
                user_id=user_id, telegram_payment_charge_id=telegram_payment_charge_id
            )
        except TelegramBadRequest as exc:
            if "CHARGE_ALREADY_REFUNDED" in str(exc):
                return  # возврат уже состоялся — повторно звёзды не уйдут
            raise

    async def get_star_transactions(self, *, offset: int, limit: int) -> list[StarTransaction]:
        res = await self.bot.get_star_transactions(offset=offset, limit=limit)
        return list(res.transactions)


def make_payload(order_id: uuid.UUID) -> str:
    return f"{PAYLOAD_PREFIX}{order_id}"  # непрозрачный id заказа, без ПДн; ≤ 128 байт


def parse_payload(payload: str) -> uuid.UUID | None:
    if not payload.startswith(PAYLOAD_PREFIX):
        return None
    try:
        return uuid.UUID(payload[len(PAYLOAD_PREFIX) :])
    except ValueError:
        return None


class StarsService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        api: StarsApi,
        catalog: Catalog,
    ) -> None:
        self.sessions = session_factory
        self.api = api
        self.catalog = catalog

    # ------------------------------------------------------------------ инвойс (S3)
    async def create_invoice(self, telegram_user_id: int, sku: str) -> Invoice:
        product = self.catalog.get(sku)
        order_id = uuid.uuid4()
        payload = make_payload(order_id)
        # Заказ записывается ДО обращения к Telegram (idempotency.md §5): цена — снимок в XTR.
        async with self.sessions() as s, s.begin():
            s.add(
                StarOrder(
                    id=order_id,
                    telegram_user_id=telegram_user_id,
                    sku=product.sku,
                    currency=XTR,
                    price_xtr=product.price_xtr,
                    payload=payload,
                    status="awaiting_payment",
                )
            )
        link = await self.api.create_invoice_link(
            title=product.title,
            description=product.description,
            payload=payload,
            price_xtr=product.price_xtr,
        )
        log.info("stars.invoice order_id=%s sku=%s price_xtr=%s", order_id, sku, product.price_xtr)
        return Invoice(order_id=order_id, payload=payload, price_xtr=product.price_xtr, link=link)

    # ------------------------------------------------------------------ pre_checkout (S2)
    async def check_pre_checkout(
        self, telegram_user_id: int, currency: str, total_amount: int, payload: str
    ) -> str | None:
        """None — можно принимать оплату; иначе текст ошибки для answerPreCheckoutQuery."""
        order_id = parse_payload(payload)
        if order_id is None:
            return MSG_ORDER_NOT_FOUND
        async with self.sessions() as s:
            order = await s.get(StarOrder, order_id)
        if order is None or order.telegram_user_id != telegram_user_id:
            return MSG_ORDER_NOT_FOUND
        if order.status != "awaiting_payment":
            return MSG_ALREADY_PAID
        if currency != XTR or total_amount != order.price_xtr:
            log.warning("stars.pre_checkout.mismatch order_id=%s", order_id)
            return MSG_PRICE_CHANGED
        return None

    # ------------------------------------------------------------------ платёж (S1, S3)
    async def apply_payment(self, snap: PaymentSnapshot, *, source: Source) -> ApplyOutcome:
        """Единый обработчик проверенного состояния (§3.3 для Stars): обновление и сверка."""
        async with self.sessions() as s, s.begin():
            # S1: событие учитывается один раз — уникальный индекс (kind, event_key).
            # Параллельный дубль ждёт на индексе до коммита первого и получает 0 строк.
            fresh = await s.scalar(
                insert(StarProcessedEvent)
                .values(
                    id=uuid.uuid4(),
                    kind="stars_payment",
                    event_key=snap.telegram_payment_charge_id,
                    source=source,
                )
                .on_conflict_do_nothing(index_elements=["kind", "event_key"])
                .returning(StarProcessedEvent.id)
            )
            if fresh is None:
                return ApplyOutcome.DUPLICATE

            order_id = parse_payload(snap.invoice_payload)
            order = None
            if order_id is not None:
                order = await s.scalar(
                    select(StarOrder).where(StarOrder.id == order_id).with_for_update()
                )

            def payment(status: str) -> StarPayment:
                return StarPayment(
                    id=uuid.uuid4(),
                    order_id=order.id if order is not None else None,
                    telegram_payment_charge_id=snap.telegram_payment_charge_id,
                    telegram_user_id=snap.telegram_user_id,
                    currency=snap.currency,
                    total_amount=snap.total_amount,
                    source=source,
                    status=status,
                )

            if order is None:
                s.add(payment("unknown_order"))
                log.error("stars.alert unknown_order charge=%s", snap.telegram_payment_charge_id)
                return ApplyOutcome.UNKNOWN_ORDER

            # S3: сверка денег в валюте заказа (XTR) против снимка цены.
            if (
                snap.currency != XTR
                or snap.total_amount != order.price_xtr
                or snap.telegram_user_id != order.telegram_user_id
            ):
                s.add(payment("reconcile_needed"))
                log.error(
                    "stars.alert mismatch order_id=%s charge=%s",
                    order.id,
                    snap.telegram_payment_charge_id,
                )
                return ApplyOutcome.MISMATCH

            if order.status != "awaiting_payment":
                s.add(payment("paid_late"))
                log.error(
                    "stars.alert paid_late order_id=%s charge=%s",
                    order.id,
                    snap.telegram_payment_charge_id,
                )
                return ApplyOutcome.PAID_LATE

            s.add(payment("succeeded"))
            order.status = "active"
            await s.flush()
            s.add(
                StarGrant(
                    id=uuid.uuid4(),
                    order_id=order.id,
                    telegram_user_id=order.telegram_user_id,
                    sku=order.sku,
                    status="active",
                )
            )
        log.info("stars.granted order_id=%s source=%s", order.id, source)
        return ApplyOutcome.GRANTED

    # ------------------------------------------------------------------ возврат (S5)
    async def refund(self, telegram_payment_charge_id: str) -> RefundOutcome:
        """Полный возврат платежа. API вызывается не более одного успешного раза."""
        async with self.sessions() as s:
            # Блокировка строки платежа на время вызова API: параллельный возврат ждёт и
            # видит refunded_full → no-op (S5). Операция редкая (оператор/авто-возврат).
            pay = await s.scalar(
                select(StarPayment)
                .where(StarPayment.telegram_payment_charge_id == telegram_payment_charge_id)
                .with_for_update()
            )
            if pay is None:
                await s.rollback()
                return RefundOutcome.NOT_FOUND
            if pay.status == "refunded_full":
                await s.rollback()
                return RefundOutcome.ALREADY_REFUNDED

            refund_id = await self._upsert_refund(s, pay, status="requested", origin="bot")
            try:
                await self.api.refund_star_payment(
                    user_id=pay.telegram_user_id,
                    telegram_payment_charge_id=pay.telegram_payment_charge_id,
                )
            except Exception as exc:
                await s.execute(
                    update(StarRefund).where(StarRefund.id == refund_id).values(status="failed")
                )
                await s.commit()
                log.error("stars.alert refund_failed charge=%s", telegram_payment_charge_id)
                raise StarsRefundError(str(exc)) from exc

            await self._mark_refunded(s, pay, refund_id)
            await s.commit()
        log.info("stars.refunded charge=%s", telegram_payment_charge_id)
        return RefundOutcome.REFUNDED

    async def apply_refund_state(self, telegram_payment_charge_id: str) -> bool:
        """Возврат уже состоялся у Telegram (refunded_payment / журнал Stars). True — применён."""
        async with self.sessions() as s, s.begin():
            pay = await s.scalar(
                select(StarPayment)
                .where(StarPayment.telegram_payment_charge_id == telegram_payment_charge_id)
                .with_for_update()
            )
            if pay is None or pay.status == "refunded_full":
                return False
            refund_id = await self._upsert_refund(s, pay, status="succeeded", origin="telegram")
            await self._mark_refunded(s, pay, refund_id)
        log.info("stars.refund_observed charge=%s", telegram_payment_charge_id)
        return True

    async def _upsert_refund(
        self, s: AsyncSession, pay: StarPayment, *, status: str, origin: str
    ) -> uuid.UUID:
        # Один возврат на платёж (UNIQUE payment_id), сумма — всегда полная сумма платежа.
        stmt = insert(StarRefund).values(
            id=uuid.uuid4(),
            payment_id=pay.id,
            amount_xtr=pay.total_amount,
            status=status,
            origin=origin,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["payment_id"],
            set_={"status": status, "updated_at": func.now()},
        ).returning(StarRefund.id)
        return (await s.execute(stmt)).scalar_one()

    async def _mark_refunded(
        self, s: AsyncSession, pay: StarPayment, refund_id: uuid.UUID
    ) -> None:
        await s.execute(
            update(StarRefund).where(StarRefund.id == refund_id).values(status="succeeded")
        )
        was_granting = pay.status == "succeeded"
        pay.status = "refunded_full"
        if was_granting and pay.order_id is not None:
            # Полный возврат → доступ снимается (§3.6); повторная покупка возможна новым заказом.
            await s.execute(
                update(StarGrant)
                .where(StarGrant.order_id == pay.order_id, StarGrant.status == "active")
                .values(status="revoked", revoked_at=func.now())
            )
            await s.execute(
                update(StarOrder)
                .where(StarOrder.id == pay.order_id, StarOrder.status == "active")
                .values(status="refunded")
            )

    # ------------------------------------------------------------------ сверка (S4)
    async def reconcile(self, *, page_size: int = 100, max_pages: int = 1000) -> ReconcileReport:
        """Сверка по журналу Stars: потерянные платежи засчитываются, возвраты применяются.

        Журнал отдаётся от новых к старым; обрабатываем от старых к новым, чтобы возврат
        применялся после платежа, к которому относится.
        """
        rep = ReconcileReport()
        txs: list[StarTransaction] = []
        offset = 0
        while rep.pages < max_pages:
            page = await self.api.get_star_transactions(offset=offset, limit=page_size)
            rep.pages += 1
            txs.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

        for tx in reversed(txs):
            src: Any = tx.source
            dst: Any = tx.receiver
            if (
                isinstance(src, TransactionPartnerUser)
                and src.transaction_type == "invoice_payment"
                and parse_payload(src.invoice_payload or "") is not None
            ):
                out = await self.apply_payment(
                    PaymentSnapshot(
                        telegram_payment_charge_id=tx.id,
                        telegram_user_id=src.user.id,
                        currency=XTR,
                        total_amount=tx.amount,
                        invoice_payload=src.invoice_payload or "",
                    ),
                    source="reconcile",
                )
                rep.outcomes.append((tx.id, out.value))
                if out is ApplyOutcome.GRANTED:
                    rep.granted += 1
                elif out is ApplyOutcome.DUPLICATE:
                    rep.duplicates += 1
                elif out is ApplyOutcome.MISMATCH:
                    rep.mismatched += 1
                elif out is ApplyOutcome.PAID_LATE:
                    rep.paid_late += 1
                else:
                    rep.unknown_order += 1
            elif isinstance(dst, TransactionPartnerUser) and await self.apply_refund_state(tx.id):
                rep.refunded += 1
            elif not isinstance(dst, TransactionPartnerUser):
                rep.ignored += 1
        log.info(
            "stars.reconcile pages=%s granted=%s mismatched=%s refunded=%s",
            rep.pages,
            rep.granted,
            rep.mismatched,
            rep.refunded,
        )
        return rep

    # ------------------------------------------------------------------ доступ
    async def has_access(self, telegram_user_id: int, sku: str) -> bool:
        async with self.sessions() as s:
            n = await s.scalar(
                select(func.count())
                .select_from(StarGrant)
                .where(
                    StarGrant.telegram_user_id == telegram_user_id,
                    StarGrant.sku == sku,
                    StarGrant.status == "active",
                )
            )
        return bool(n)
