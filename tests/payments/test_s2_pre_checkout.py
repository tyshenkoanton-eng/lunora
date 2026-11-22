"""S2 (§2.4b): pre_checkout_query обрабатывается синхронно и ВСЕГДА получает явный answer().

ok=True — только при валидном заказе и цене в XTR; иначе ok=False + error_message (текст на «вы»).
"""

from aiogram.methods import AnswerPreCheckoutQuery

from tests.payments.conftest import OTHER_USER_ID, USER_ID, pre_checkout_update


def _only_answer(tg) -> AnswerPreCheckoutQuery:
    answers = tg.calls_of(AnswerPreCheckoutQuery)
    assert len(answers) == 1, f"ожидался ровно один answerPreCheckoutQuery, было {len(answers)}"
    return answers[0]


async def test_valid_order_answers_ok(service, dp, bot, tg):
    inv = await service.create_invoice(USER_ID, "report_full")
    upd = pre_checkout_update(inv.payload, inv.price_xtr)
    await dp.feed_update(bot, upd)
    ans = _only_answer(tg)
    assert ans.ok is True
    assert ans.error_message is None
    assert ans.pre_checkout_query_id == upd.pre_checkout_query.id


async def _assert_rejected(dp, bot, tg, upd):
    await dp.feed_update(bot, upd)
    ans = _only_answer(tg)
    assert ans.ok is False
    assert ans.error_message and ans.error_message.strip(), "error_message обязателен при ok=False"
    return ans


async def test_unknown_payload_rejected(dp, bot, tg):
    await _assert_rejected(dp, bot, tg, pre_checkout_update("lunora:v1:not-an-order", 1))


async def test_unknown_order_uuid_rejected(dp, bot, tg):
    payload = "lunora:v1:00000000-0000-0000-0000-000000000000"
    await _assert_rejected(dp, bot, tg, pre_checkout_update(payload, 1))


async def test_wrong_amount_rejected(service, dp, bot, tg):
    inv = await service.create_invoice(USER_ID, "report_full")
    await _assert_rejected(dp, bot, tg, pre_checkout_update(inv.payload, inv.price_xtr - 1))


async def test_wrong_currency_rejected(service, dp, bot, tg):
    inv = await service.create_invoice(USER_ID, "report_full")
    await _assert_rejected(dp, bot, tg, pre_checkout_update(inv.payload, inv.price_xtr, "RUB"))


async def test_foreign_user_rejected(service, dp, bot, tg):
    inv = await service.create_invoice(USER_ID, "report_full")
    upd = pre_checkout_update(inv.payload, inv.price_xtr, user_id=OTHER_USER_ID)
    await _assert_rejected(dp, bot, tg, upd)


async def test_already_paid_order_rejected(service, dp, bot, tg):
    from lunora.payments.stars import PaymentSnapshot

    inv = await service.create_invoice(USER_ID, "report_full")
    await service.apply_payment(
        PaymentSnapshot("ch-paid", USER_ID, "XTR", inv.price_xtr, inv.payload), source="update"
    )
    await _assert_rejected(dp, bot, tg, pre_checkout_update(inv.payload, inv.price_xtr))


async def test_internal_error_still_answers(bot, tg):
    """Сбой внутри проверки — всё равно явный answer(ok=False), а не тишина до таймаута."""
    from aiogram import Dispatcher

    from lunora.payments.telegram import build_router

    class Broken:
        async def check_pre_checkout(self, *a, **kw):
            raise RuntimeError("БД недоступна")

    d = Dispatcher()
    d.include_router(build_router(Broken()))
    await _assert_rejected(d, bot, tg, pre_checkout_update("lunora:v1:x", 1))


async def test_error_text_is_polite_and_has_no_internals(service, dp, bot, tg):
    inv = await service.create_invoice(USER_ID, "report_full")
    ans = await _assert_rejected(dp, bot, tg, pre_checkout_update(inv.payload, 999))
    assert "вы" in ans.error_message.lower() or "ваш" in ans.error_message.lower()
    for leak in ("Traceback", "Error", inv.payload):
        assert leak not in ans.error_message
