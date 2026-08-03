import logging
from datetime import date

from sqlalchemy import select

from lunora.bot.setup import bot
from lunora.db import async_session
from lunora.models.forecast import DailyForecast
from lunora.models.user import User

log = logging.getLogger(__name__)


async def send_daily_forecasts(target_date: date | None = None):
    target = target_date or date.today()

    async with async_session() as session:
        rows = await session.execute(
            select(DailyForecast, User)
            .join(User, DailyForecast.user_id == User.id)
            .where(
                DailyForecast.forecast_date == target,
                DailyForecast.sent == False,  # noqa: E712
                User.is_deleted == False,  # noqa: E712
            )
        )

        for forecast, user in rows.all():
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"🌅 Прогноз на {target.strftime('%d.%m.%Y')}\n\n{forecast.content}",
                )
                forecast.sent = True
                await session.commit()
                log.info("Forecast sent to user %s", user.id)
            except Exception:
                log.exception("Failed to send forecast to user %s", user.id)
