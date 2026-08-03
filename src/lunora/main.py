import asyncio
import logging

import uvicorn
from aiogram.types import Update
from fastapi import Request

from lunora.api.app import app
from lunora.bot.handlers import router
from lunora.bot.setup import bot, dp
from lunora.config import settings

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)

dp.include_router(router)


@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


def main():
    uvicorn.run(
        "lunora.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
