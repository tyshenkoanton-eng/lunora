import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from lunora.models.base import Base, TimestampMixin, UUIDPrimaryKey


class DailyForecast(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "daily_forecasts"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    forecast_date: Mapped[date] = mapped_column(Date, index=True)
    content: Mapped[str] = mapped_column(Text)
    sent: Mapped[bool] = mapped_column(default=False)
