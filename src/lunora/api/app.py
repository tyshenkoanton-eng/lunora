from contextlib import asynccontextmanager

from fastapi import FastAPI

from lunora.bot.setup import bot, dp
from lunora.config import settings
from lunora.db import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.bot_token:
        await bot.delete_webhook(drop_pending_updates=True)
        webhook_url = f"{settings.webhook_base_url}/webhook" if settings.webhook_base_url else ""
        if webhook_url:
            await bot.set_webhook(webhook_url)
    yield
    if settings.bot_token:
        await bot.session.close()
    await engine.dispose()


app = FastAPI(title="Lunora", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}
