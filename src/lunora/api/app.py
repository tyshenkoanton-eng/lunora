import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from lunora.bot.setup import bot, dp
from lunora.config import settings
from lunora.api.routes import router
from lunora.db import engine

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    polling_task = None
    if settings.bot_token:
        await bot.delete_webhook(drop_pending_updates=True)
        if settings.webhook_base_url:
            webhook_url = f"{settings.webhook_base_url}/webhook"
            await bot.set_webhook(webhook_url)
            log.info("Webhook set: %s", webhook_url)
        else:
            polling_task = asyncio.create_task(dp.start_polling(bot))
            log.info("Started polling mode")
    yield
    if polling_task is not None:
        dp.shutdown.set()
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    if settings.bot_token:
        await bot.session.close()
    await engine.dispose()


app = FastAPI(title="Lunora", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}


_static = Path(__file__).resolve().parent.parent.parent.parent / "static"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="static")
