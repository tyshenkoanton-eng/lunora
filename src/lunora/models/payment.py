import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from lunora.models.base import Base, TimestampMixin, UUIDPrimaryKey


class PaymentStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentOrder(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "payment_orders"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.PENDING
    )
    provider: Mapped[str] = mapped_column(String(20))
    provider_payment_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )


class Entitlement(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "entitlements"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(30))
    payment_order_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_orders.id"), nullable=True
    )


class Referral(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "referrals"

    referrer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    referred_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="registered")
    bonus_granted: Mapped[bool] = mapped_column(default=False)
