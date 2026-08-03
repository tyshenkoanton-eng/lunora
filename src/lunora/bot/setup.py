from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from lunora.config import settings

session = None
if settings.telegram_proxy:
    session = AiohttpSession(proxy=settings.telegram_proxy)

_DUMMY_TOKEN = "0000000000:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAaaa"
bot = Bot(token=settings.bot_token or _DUMMY_TOKEN, session=session)
dp = Dispatcher()
