"""Таблицы адаптера Telegram Stars (TRANSACTIONS-КОНТРАКТЫ §2.4b, оси §3.1).

Гарантии идемпотентности — в схеме, а не в коде (S1):
- ``star_processed_events (kind, event_key)`` — событие «пришёл платёж charge_id» учтено один раз;
- ``star_payments.telegram_payment_charge_id`` — одна запись на платёж Stars;
- ``star_grants.order_id`` — один доступ на заказ;
- ``star_refunds.payment_id`` — один (полный) возврат на платёж (S5).
ПДн нет: только синтетический/телеграмный числовой id пользователя, SKU и суммы в XTR.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from lunora.models.base import Base, UUIDPrimaryKey

ORDER_STATUSES = ("awaiting_payment", "active", "refunded")
PAYMENT_STATUSES = ("succeeded", "reconcile_needed", "paid_late", "unknown_order", "refunded_full")
GRANT_STATUSES = ("active", "revoked")
REFUND_STATUSES = ("requested", "succeeded", "failed")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class _Stamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StarOrder(Base, UUIDPrimaryKey, _Stamped):
    """Заказ как намерение покупки; цена — снимок в XTR в момент инвойса (S3)."""

    __tablename__ = "star_orders"
    __table_args__ = (
        CheckConstraint("currency = 'XTR'", name="star_orders_currency_xtr"),
        CheckConstraint("price_xtr > 0", name="star_orders_price_positive"),
        CheckConstraint(_in("status", ORDER_STATUSES), name="star_orders_status"),
    )

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    sku: Mapped[str] = mapped_column(String(64))
    currency: Mapped[str] = mapped_column(String(3), default="XTR")
    price_xtr: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="awaiting_payment")


class StarProcessedEvent(Base, UUIDPrimaryKey):
    __tablename__ = "star_processed_events"
    __table_args__ = (UniqueConstraint("kind", "event_key", name="star_processed_events_key"),)

    kind: Mapped[str] = mapped_column(String(40))
    event_key: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StarPayment(Base, UUIDPrimaryKey, _Stamped):
    """Факт денег Stars. Источник подтверждения — successful_payment или журнал (S1, S4)."""

    __tablename__ = "star_payments"
    __table_args__ = (
        CheckConstraint(_in("status", PAYMENT_STATUSES), name="star_payments_status"),
        CheckConstraint(_in("source", ("update", "reconcile")), name="star_payments_source"),
    )

    order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("star_orders.id"), nullable=True, index=True
    )
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(200), unique=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8))
    total_amount: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))


class StarGrant(Base, UUIDPrimaryKey):
    """Доступ, выданный по заказу. Один на заказ — уникальный индекс (S1)."""

    __tablename__ = "star_grants"
    __table_args__ = (CheckConstraint(_in("status", GRANT_STATUSES), name="star_grants_status"),)

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("star_orders.id"), unique=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    sku: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StarRefund(Base, UUIDPrimaryKey, _Stamped):
    """Возврат Stars — только полный (S5): один на платёж, сумма = сумме платежа."""

    __tablename__ = "star_refunds"
    __table_args__ = (
        CheckConstraint(_in("status", REFUND_STATUSES), name="star_refunds_status"),
        CheckConstraint(_in("origin", ("bot", "telegram")), name="star_refunds_origin"),
        CheckConstraint("amount_xtr > 0", name="star_refunds_amount_positive"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("star_payments.id"), unique=True)
    amount_xtr: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    origin: Mapped[str] = mapped_column(String(20))
