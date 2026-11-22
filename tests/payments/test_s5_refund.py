"""S5 (§2.4b): возврат — refundStarPayment, только ПОЛНЫЙ (параметра суммы нет).

Вызов API — один раз; повторный возврат — no-op без вызова API; доступ снят.
"""

import asyncio

import pytest
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import RefundStarPayment
from sqlalchemy import text

from tests.payments.conftest import USER_ID, refunded_payment_update, successful_payment_update


async def _paid(service, dp, bot, charge):
    inv = await service.create_invoice(USER_ID, "report_full")
    await dp.feed_update(bot, successful_payment_update(inv.payload, inv.price_xtr, charge))
    assert await service.has_access(USER_ID, "report_full") is True
    return inv


def test_refund_method_has_no_amount():
    """Bot API: refundStarPayment возвращает платёж целиком — параметра суммы нет."""
    assert set(RefundStarPayment.model_fields) == {"user_id", "telegram_payment_charge_id"}


async def test_refund_once_full_and_revokes(service, session_factory, dp, bot, tg):
    from lunora.payments.stars import RefundOutcome

    inv = await _paid(service, dp, bot, "ch-r1")
    assert await service.refund("ch-r1") == RefundOutcome.REFUNDED
    calls = tg.calls_of(RefundStarPayment)
    assert len(calls) == 1
    assert (calls[0].user_id, calls[0].telegram_payment_charge_id) == (USER_ID, "ch-r1")
    assert await service.has_access(USER_ID, "report_full") is False
    async with session_factory() as s:
        amount, st = (await s.execute(text("SELECT amount_xtr, status FROM star_refunds"))).one()
        pay = (await s.execute(text("SELECT status FROM star_payments"))).scalar_one()
        order = (await s.execute(text("SELECT status FROM star_orders"))).scalar_one()
        grant = (await s.execute(text("SELECT status FROM star_grants"))).scalar_one()
    assert (amount, st) == (inv.price_xtr, "succeeded")  # полная сумма
    assert (pay, order, grant) == ("refunded_full", "refunded", "revoked")


async def test_repeat_refund_is_noop(service, dp, bot, tg):
    from lunora.payments.stars import RefundOutcome

    await _paid(service, dp, bot, "ch-r2")
    await service.refund("ch-r2")
    assert await service.refund("ch-r2") == RefundOutcome.ALREADY_REFUNDED
    assert await service.refund("ch-r2") == RefundOutcome.ALREADY_REFUNDED
    assert len(tg.calls_of(RefundStarPayment)) == 1
    assert await service.has_access(USER_ID, "report_full") is False


async def test_parallel_refunds_call_api_once(service, session_factory, dp, bot, tg):
    from lunora.payments.stars import RefundOutcome

    await _paid(service, dp, bot, "ch-r3")
    tg.refund_delay = 0.05
    res = await asyncio.gather(*(service.refund("ch-r3") for _ in range(5)))
    assert sorted(res) == sorted([RefundOutcome.REFUNDED] + [RefundOutcome.ALREADY_REFUNDED] * 4)
    assert len(tg.calls_of(RefundStarPayment)) == 1
    async with session_factory() as s:
        assert (await s.execute(text("SELECT count(*) FROM star_refunds"))).scalar_one() == 1


async def test_refund_unknown_charge_does_not_call_api(service, tg):
    from lunora.payments.stars import RefundOutcome

    assert await service.refund("ch-nope") == RefundOutcome.NOT_FOUND
    assert not tg.calls_of(RefundStarPayment)


async def test_refund_network_failure_then_retry(service, dp, bot, tg):
    """Сбой сети: возврат не засчитан, доступ ещё есть; повтор доводит до конца."""
    from lunora.payments.stars import RefundOutcome, StarsRefundError

    await _paid(service, dp, bot, "ch-r4")
    tg.fail_next[RefundStarPayment] = TelegramNetworkError(method=None, message="timeout")
    with pytest.raises(StarsRefundError):
        await service.refund("ch-r4")
    assert await service.has_access(USER_ID, "report_full") is True
    assert await service.refund("ch-r4") == RefundOutcome.REFUNDED
    assert await service.has_access(USER_ID, "report_full") is False


async def test_refund_already_done_at_telegram_is_accepted(service, dp, bot, tg):
    """Telegram уже вернул (CHARGE_ALREADY_REFUNDED) — фиксируем возврат, второй раз не платим."""
    from lunora.payments.stars import RefundOutcome

    await _paid(service, dp, bot, "ch-r5")
    tg.refunded.add("ch-r5")  # возврат случился, а мы не успели записать
    assert await service.refund("ch-r5") == RefundOutcome.REFUNDED
    assert await service.has_access(USER_ID, "report_full") is False


async def test_refunded_payment_update_after_refund_is_noop(service, session_factory, dp, bot, tg):
    inv = await _paid(service, dp, bot, "ch-r6")
    await service.refund("ch-r6")
    await dp.feed_update(bot, refunded_payment_update(inv.payload, inv.price_xtr, "ch-r6"))
    async with session_factory() as s:
        assert (await s.execute(text("SELECT count(*) FROM star_refunds"))).scalar_one() == 1
    assert len(tg.calls_of(RefundStarPayment)) == 1


async def test_refunded_payment_update_revokes_access(service, session_factory, dp, bot, tg):
    """Возврат, сделанный не нами (обновление refunded_payment), тоже снимает доступ."""
    inv = await _paid(service, dp, bot, "ch-r7")
    await dp.feed_update(bot, refunded_payment_update(inv.payload, inv.price_xtr, "ch-r7"))
    assert await service.has_access(USER_ID, "report_full") is False
    assert not tg.calls_of(RefundStarPayment)


async def test_repurchase_after_refund_possible(service, dp, bot):
    await _paid(service, dp, bot, "ch-r8")
    await service.refund("ch-r8")
    await _paid(service, dp, bot, "ch-r9")  # новый заказ — новый доступ (§3.6)
