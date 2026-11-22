"""S4 (§2.4b): реконсиляция после падения — по getStarTransactions (не GET по id).

Платёж, чей successful_payment потерян, находится в журнале Stars и засчитывается один раз;
повторная сверка и запоздалое обновление — no-op.
"""

from aiogram.methods import GetStarTransactions, RefundStarPayment
from sqlalchemy import text

from tests.payments.conftest import USER_ID, counts, successful_payment_update


async def test_lost_update_found_by_reconcile(service, session_factory, tg):
    inv = await service.create_invoice(USER_ID, "report_full")
    tg.ledger_incoming("ch-lost", USER_ID, inv.price_xtr, inv.payload)  # обновление не пришло

    assert await service.has_access(USER_ID, "report_full") is False
    rep = await service.reconcile()
    assert rep.granted == 1
    assert tg.calls_of(GetStarTransactions), "сверка обязана идти через getStarTransactions"
    assert await service.has_access(USER_ID, "report_full") is True
    async with session_factory() as s:
        src = (await s.execute(text("SELECT source FROM star_payments"))).scalar_one()
    assert src == "reconcile"


async def test_reconcile_twice_and_late_update_count_once(service, session_factory, dp, bot, tg):
    inv = await service.create_invoice(USER_ID, "report_full")
    tg.ledger_incoming("ch-once", USER_ID, inv.price_xtr, inv.payload)
    r1 = await service.reconcile()
    r2 = await service.reconcile()
    await dp.feed_update(bot, successful_payment_update(inv.payload, inv.price_xtr, "ch-once"))
    assert (r1.granted, r2.granted) == (1, 0)
    c = await counts(session_factory)
    assert c["star_payments"] == 1 and c["star_grants"] == 1


async def test_update_then_reconcile_is_noop(service, session_factory, dp, bot, tg):
    inv = await service.create_invoice(USER_ID, "report_full")
    await dp.feed_update(bot, successful_payment_update(inv.payload, inv.price_xtr, "ch-upd"))
    tg.ledger_incoming("ch-upd", USER_ID, inv.price_xtr, inv.payload)
    rep = await service.reconcile()
    assert rep.granted == 0
    c = await counts(session_factory)
    assert c["star_payments"] == 1 and c["star_grants"] == 1


async def test_reconcile_paginates_and_ignores_foreign(service, session_factory, tg):
    inv = await service.create_invoice(USER_ID, "report_full")
    tg.ledger_incoming("ch-deep", USER_ID, inv.price_xtr, inv.payload)  # самый старый
    for i in range(230):  # чужие платежи (другой бот/продукт) поверх — за пределами 1-й страницы
        tg.ledger_incoming(f"foreign-{i}", USER_ID, 5, f"other:{i}")
    rep = await service.reconcile()
    assert rep.granted == 1
    assert rep.ignored == 230
    offsets = [c.offset or 0 for c in tg.calls_of(GetStarTransactions)]
    assert offsets[:3] == [0, 100, 200]
    assert all((c.limit or 100) <= 100 for c in tg.calls_of(GetStarTransactions))
    assert (await counts(session_factory))["star_payments"] == 1


async def test_reconcile_mismatched_amount_not_granted(service, tg):
    inv = await service.create_invoice(USER_ID, "report_full")
    tg.ledger_incoming("ch-bad", USER_ID, inv.price_xtr - 1, inv.payload)
    rep = await service.reconcile()
    assert rep.granted == 0 and rep.mismatched == 1
    assert await service.has_access(USER_ID, "report_full") is False


async def test_reconcile_applies_refund_seen_in_ledger(service, session_factory, dp, bot, tg):
    """Возврат прошёл, а запись о нём потерялась (падение после refundStarPayment)."""
    inv = await service.create_invoice(USER_ID, "report_full")
    await dp.feed_update(bot, successful_payment_update(inv.payload, inv.price_xtr, "ch-rf"))
    tg.ledger_incoming("ch-rf", USER_ID, inv.price_xtr, inv.payload)
    tg.ledger_refund("ch-rf", USER_ID, inv.price_xtr)
    rep = await service.reconcile()
    assert rep.refunded == 1
    assert await service.has_access(USER_ID, "report_full") is False
    assert not tg.calls_of(RefundStarPayment)  # деньги уже вернулись — повторно не дёргаем
    rep2 = await service.reconcile()
    assert rep2.refunded == 0
