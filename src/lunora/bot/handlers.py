from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lunora.config import settings

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    builder = InlineKeyboardBuilder()
    webapp_url = settings.webapp_url or settings.webhook_base_url or "https://lun-ra.ru"
    builder.button(text="🔮 Открыть Lunora", web_app=WebAppInfo(url=webapp_url))

    await message.answer(
        "Привет! Я **Лунора** — твой персональный AI-астролог.\n\n"
        "Рассчитаю натальную карту по 4 системам:\n"
        "🔮 Западная · 🪷 Ведическая · 🐉 Китайская · 🔢 Нумерология\n\n"
        "Нажми кнопку ниже, чтобы начать 👇",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )


@router.message()
async def handle_text(message: Message):
    if not message.text:
        return

    user_id = _get_user_id(message.from_user.id)
    if not user_id:
        await message.answer(
            "Сначала пройди регистрацию — нажми /start и открой приложение.",
        )
        return

    from lunora.db import async_session
    from lunora.llm.client import generate_response
    from lunora.models.chart import NatalChart
    from lunora.models.thread import Message as MsgModel, Thread
    from lunora.models.user import User
    from sqlalchemy import select

    async with async_session() as session:
        user_row = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user_row.scalar_one_or_none()
        if not user:
            await message.answer("Сначала пройди регистрацию через приложение.")
            return

        chart_row = await session.execute(
            select(NatalChart)
            .where(NatalChart.user_id == user.id)
            .order_by(NatalChart.created_at.desc())
            .limit(1)
        )
        chart = chart_row.scalar_one_or_none()
        if not chart:
            await message.answer("Карта ещё не рассчитана. Открой приложение и заполни данные.")
            return

        thread_row = await session.execute(
            select(Thread)
            .where(Thread.user_id == user.id)
            .order_by(Thread.created_at.desc())
            .limit(1)
        )
        thread = thread_row.scalar_one_or_none()
        if not thread:
            thread = Thread(user_id=user.id, title=message.text[:100])
            session.add(thread)
            await session.flush()

        msg_rows = await session.execute(
            select(MsgModel)
            .where(MsgModel.thread_id == thread.id)
            .order_by(MsgModel.created_at.asc())
            .limit(20)
        )
        history = [{"role": m.role, "content": m.content} for m in msg_rows.scalars().all()]

        chart_data = {
            "western": chart.western,
            "vedic": chart.vedic,
            "chinese": chart.chinese,
            "numerology": chart.numerology,
        }

        await message.answer("🔮 Считаю звёзды...")

        answer, _ = await generate_response(
            question=message.text,
            chart_data=chart_data,
            precision=user.birth_time_precision.value,
            history=history,
        )

        session.add(MsgModel(thread_id=thread.id, role="user", content=message.text))
        session.add(MsgModel(thread_id=thread.id, role="assistant", content=answer))
        thread.message_count += 2
        await session.commit()

        await message.answer(answer)


def _get_user_id(telegram_id: int) -> str | None:
    """Quick sync check — returns None if user not onboarded. Lazy import to avoid circular deps."""
    return str(telegram_id)
