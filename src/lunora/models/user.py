import uuid
from datetime import date, datetime, time
from enum import StrEnum

from sqlalchemy import BigInteger, Date, Enum, String, Time, Text
from sqlalchemy.orm import Mapped, mapped_column

from lunora.models.base import Base, TimestampMixin, UUIDPrimaryKey


class BirthTimePrecision(StrEnum):
    EXACT = "exact"
    APPROXIMATE_30 = "approximate_30"
    APPROXIMATE_60 = "approximate_60"
    APPROXIMATE = "approximate"
    UNKNOWN = "unknown"


class User(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    birth_date: Mapped[date] = mapped_column(Date)
    birth_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    birth_time_precision: Mapped[BirthTimePrecision] = mapped_column(
        Enum(BirthTimePrecision), default=BirthTimePrecision.UNKNOWN
    )
    birth_city: Mapped[str] = mapped_column(String(200))
    birth_lat: Mapped[float]
    birth_lon: Mapped[float]
    timezone: Mapped[str] = mapped_column(String(50))

    referral_code: Mapped[str] = mapped_column(String(20), unique=True)
    referred_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    consent_given_at: Mapped[datetime]
    is_deleted: Mapped[bool] = mapped_column(default=False)
