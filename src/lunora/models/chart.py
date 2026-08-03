import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
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
    input_hash: Mapped[str] = mapped_column(String(64))
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
