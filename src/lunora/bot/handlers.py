from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я Лунора — твой персональный AI-астролог.\n\n"
        "Рассчитаю натальную карту по 4 системам бесплатно.\n"
        "Скоро здесь появится кнопка для расчёта 🌙"
    )
