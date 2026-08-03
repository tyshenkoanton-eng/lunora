from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from lunora.config import settings

session = None
if settings.telegram_proxy:
    session = AiohttpSession(proxy=settings.telegram_proxy)

bot = Bot(token=settings.bot_token or "placeholder", session=session)
dp = Dispatcher()
