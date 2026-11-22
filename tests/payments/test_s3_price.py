"""S3 (§2.4b): цена фиксируется в XTR в момент создания инвойса (price_snapshot — в Stars).

Платёж на другую сумму или валюту отклоняется: доступа нет, платёж — reconcile_needed.
"""

from aiogram.methods import AnswerPreCheckoutQuery, CreateInvoiceLink
from sqlalchemy import text

from tests.payments.conftest import USER_ID, pre_checkout_update, successful_payment_update


async def test_invoice_in_xtr_with_snapshot(service, session_factory, tg, catalog):
    inv = await service.create_invoice(USER_ID, "report_full")
    assert inv.price_xtr == catalog.get("report_full").price_xtr == 250
    assert inv.link.startswith("https://t.me/")

    calls = tg.calls_of(CreateInvoiceLink)
    assert len(calls) == 1
    call = calls[0]
    assert call.currency == "XTR"
    assert len(call.prices) == 1 and call.prices[0].amount == 250  # Stars: ровно одна позиция
    assert not call.provider_token  # для XTR токен провайдера пуст
    assert call.payload == inv.payload
    assert len(call.payload.encode()) <= 128  # лимит Bot API на payload

    async with session_factory() as s:
        row = (
            await s.execute(text("SELECT currency, price_xtr, status, sku FROM star_orders"))
        ).one()
    assert tuple(row) == ("XTR", 250, "awaiting_payment", "report_full")


async def test_payload_carries_no_pii(service):
    inv = await service.create_invoice(USER_ID, "report_full")
    assert str(USER_ID) not in inv.payload  # только непрозрачный id заказа


async def test_price_change_after_invoice_does_not_move_snapshot(service, dp, bot, tg, catalog):
    inv = await service.create_invoice(USER_ID, "report_full")
    catalog.set_price("report_full", 300)  # прайс поменялся после выставления
    await dp.feed_update(bot, pre_checkout_update(inv.payload, 250))
    assert tg.calls_of(AnswerPreCheckoutQuery)[-1].ok is True  # действует снимок

    await dp.feed_update(bot, successful_payment_update(inv.payload, 250, "ch-snap"))
    assert await service.has_access(USER_ID, "report_full") is True

    inv2 = await service.create_invoice(USER_ID, "report_full")
    assert inv2.price_xtr == 300  # новый инвойс — по новой цене


async def _mismatch(service, session_factory, dp, bot, amount, currency, charge):
    from lunora.payments.stars import ApplyOutcome, PaymentSnapshot

    inv = await service.create_invoice(USER_ID, "report_full")
    out = await service.apply_payment(
        PaymentSnapshot(charge, USER_ID, currency, amount, inv.payload), source="update"
    )
    assert out == ApplyOutcome.MISMATCH
    assert await service.has_access(USER_ID, "report_full") is False
    async with session_factory() as s:
        pay = (await s.execute(text("SELECT status FROM star_payments"))).scalar_one()
        order = (await s.execute(text("SELECT status FROM star_orders"))).scalar_one()
        grants = (await s.execute(text("SELECT count(*) FROM star_grants"))).scalar_one()
    assert pay == "reconcile_needed"  # деньги учтены, выдачи нет — разбор/возврат
    assert order == "awaiting_payment"
    assert grants == 0


async def test_underpayment_rejected(service, session_factory, dp, bot):
    await _mismatch(service, session_factory, dp, bot, 249, "XTR", "ch-under")


async def test_overpayment_rejected(service, session_factory, dp, bot):
    # у Stars нет частичного возврата разницы (§3.6) → переплату не исполняем молча
    await _mismatch(service, session_factory, dp, bot, 251, "XTR", "ch-over")


async def test_foreign_currency_rejected(service, session_factory, dp, bot):
    await _mismatch(service, session_factory, dp, bot, 250, "RUB", "ch-rub")


async def test_foreign_user_payment_rejected(service, session_factory):
    from lunora.payments.stars import ApplyOutcome, PaymentSnapshot

    inv = await service.create_invoice(USER_ID, "report_full")
    out = await service.apply_payment(
        PaymentSnapshot("ch-foreign", USER_ID + 1, "XTR", 250, inv.payload), source="update"
    )
    assert out == ApplyOutcome.MISMATCH
    assert await service.has_access(USER_ID, "report_full") is False
    assert await service.has_access(USER_ID + 1, "report_full") is False


async def test_unknown_sku_cannot_be_invoiced(service):
    import pytest
    from lunora.payments.catalog import UnknownProduct

    with pytest.raises(UnknownProduct):
        await service.create_invoice(USER_ID, "no_such_sku")


async def test_db_enforces_xtr_and_positive_price(session_factory):
    import uuid

    import pytest
    from sqlalchemy.exc import IntegrityError

    for cur, price in (("RUB", 10), ("XTR", 0)):
        async with session_factory() as s:
            with pytest.raises(IntegrityError):
                await s.execute(
                    text(
                        "INSERT INTO star_orders (id, telegram_user_id, sku, currency, price_xtr, "
                        "payload, status) VALUES (:id, 1, 'x', :c, :p, :pl, 'awaiting_payment')"
                    ),
                    {"id": uuid.uuid4(), "c": cur, "p": price, "pl": uuid.uuid4().hex},
                )
