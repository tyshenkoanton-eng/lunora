"""Роутер aiogram для Telegram Stars: pre_checkout_query, successful_payment, refunded_payment.

Подключать ДО общего роутера сообщений: иначе служебные сообщения об оплате съест catch-all.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

from lunora.payments.stars import MSG_INTERNAL, PaymentSnapshot

log = logging.getLogger("lunora.payments.telegram")

# Telegram ждёт answerPreCheckoutQuery ~10 с (§2.4b); проверке даём меньше, чтобы успеть ответить.
PRE_CHECKOUT_BUDGET_S = 7.0


def build_router(service: Any) -> Router:
    router = Router(name="stars_payments")

    @router.pre_checkout_query()
    async def on_pre_checkout(query: PreCheckoutQuery) -> None:
        # S2: явный answer() — всегда, при любом исходе проверки, включая сбой и таймаут.
        try:
            error = await asyncio.wait_for(
                service.check_pre_checkout(
                    query.from_user.id, query.currency, query.total_amount, query.invoice_payload
                ),
                timeout=PRE_CHECKOUT_BUDGET_S,
            )
        except Exception:
            log.exception("stars.pre_checkout.failed")
            error = MSG_INTERNAL
        if error is None:
            await query.answer(ok=True)
        else:
            await query.answer(ok=False, error_message=error)

    @router.message(F.successful_payment)
    async def on_successful_payment(message: Message) -> None:
        sp = message.successful_payment
        assert sp is not None and message.from_user is not None
        # S1: successful_payment — это и есть проверенное состояние; отдельного fetch нет.
        await service.apply_payment(
            PaymentSnapshot(
                telegram_payment_charge_id=sp.telegram_payment_charge_id,
                telegram_user_id=message.from_user.id,
                currency=sp.currency,
                total_amount=sp.total_amount,
                invoice_payload=sp.invoice_payload,
            ),
            source="update",
        )

    @router.message(F.refunded_payment)
    async def on_refunded_payment(message: Message) -> None:
        rp = message.refunded_payment
        assert rp is not None
        await service.apply_refund_state(rp.telegram_payment_charge_id)

    return router
