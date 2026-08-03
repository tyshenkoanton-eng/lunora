import logging
from datetime import date, datetime, timezone

from sqlalchemy import select

from lunora.db import async_session
from lunora.llm.client import generate_response
from lunora.models.chart import NatalChart
from lunora.models.forecast import DailyForecast
from lunora.models.user import User

log = logging.getLogger(__name__)

FORECAST_QUESTION = (
    "Составь краткий прогноз на сегодня ({date}) на основе натальной карты. "
    "Учти текущие транзиты планет. Формат: 2-3 абзаца, тёплый дружеский тон."
)


async def generate_daily_forecasts(target_date: date | None = None):
    target = target_date or date.today()
    question = FORECAST_QUESTION.format(date=target.isoformat())

    async with async_session() as session:
        users = await session.execute(
            select(User).where(User.is_deleted == False)  # noqa: E712
        )

        for user in users.scalars().all():
            existing = await session.execute(
                select(DailyForecast).where(
                    DailyForecast.user_id == user.id,
                    DailyForecast.forecast_date == target,
                )
            )
            if existing.scalar_one_or_none():
                continue

            chart_row = await session.execute(
                select(NatalChart)
                .where(NatalChart.user_id == user.id)
                .order_by(NatalChart.created_at.desc())
                .limit(1)
            )
            chart = chart_row.scalar_one_or_none()
            if not chart:
                continue

            chart_data = {
                "western": chart.western,
                "vedic": chart.vedic,
                "chinese": chart.chinese,
                "numerology": chart.numerology,
            }

            try:
                answer, _ = await generate_response(
                    question=question,
                    chart_data=chart_data,
                    precision=user.birth_time_precision.value,
                )
                forecast = DailyForecast(
                    user_id=user.id,
                    forecast_date=target,
                    content=answer,
                )
                session.add(forecast)
                await session.commit()
                log.info("Forecast generated for user %s", user.id)
            except Exception:
                log.exception("Failed to generate forecast for user %s", user.id)
