from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import PRODUCTION, TEST

from lunora.config import settings

# тестовая среда Telegram — для смоука оплаты Stars без реальных звёзд (G17-S3a)
_api = TEST if settings.telegram_test_env else PRODUCTION
session = AiohttpSession(api=_api, proxy=settings.telegram_proxy or None)

_DUMMY_TOKEN = "0000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAaaa"
bot = Bot(token=settings.bot_token or _DUMMY_TOKEN, session=session)
dp = Dispatcher()

from lunora.bot.handlers import router  # noqa: E402
from lunora.db import async_session  # noqa: E402
from lunora.payments.catalog import DEFAULT_CATALOG  # noqa: E402
from lunora.payments.stars import AiogramStarsApi, StarsService  # noqa: E402
from lunora.payments.telegram import build_router  # noqa: E402

stars = StarsService(async_session, AiogramStarsApi(bot), DEFAULT_CATALOG)
# оплата — раньше общего роутера: catch-all handle_text иначе съест служебные сообщения
dp.include_router(build_router(stars))
dp.include_router(router)
