import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from lunora.models.base import Base, TimestampMixin, UUIDPrimaryKey


class NatalChart(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "natal_charts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    western: Mapped[dict] = mapped_column(JSONB, default=dict)
    vedic: Mapped[dict] = mapped_column(JSONB, default=dict)
    chinese: Mapped[dict] = mapped_column(JSONB, default=dict)
    numerology: Mapped[dict] = mapped_column(JSONB, default=dict)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)


class CalculationRun(Base, UUIDPrimaryKey):
    __tablename__ = "calculation_runs"

    chart_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("natal_charts.id"), index=True)
    engine_version: Mapped[str] = mapped_column(String(50))
    zodiac_type: Mapped[str] = mapped_column(String(20))
    ayanamsa: Mapped[str | None] = mapped_column(String(30), nullable=True)
    house_system: Mapped[str] = mapped_column(String(20))
    # F07: полное происхождение входа (пояс, точность/допуск, place_id, UTC-гипотезы, версии).
    # input_hash — HMAC(server_pepper, …), а не голый SHA-256 входа (ARCHITECTURE §3.2: голый
    # хеш раскрывает ПДн и даёт межпользовательскую дедупликацию).
    input_hash: Mapped[str] = mapped_column(String(64))
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    precision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tolerance_minutes: Mapped[int | None] = mapped_column(nullable=True)
    place_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dispute_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # provenance: гипотезы UTC, версии данных/движка
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
