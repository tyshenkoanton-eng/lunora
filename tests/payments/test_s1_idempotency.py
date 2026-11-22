"""S1 (§2.4b): подтверждение = successful_payment; идемпотентность по telegram_payment_charge_id.

Гарантия «один платёж → один оплаченный заказ → один доступ» даёт УНИКАЛЬНЫЙ ИНДЕКС БД,
а не проверка в коде: тесты проверяют и поведение (в т.ч. параллельно), и наличие индексов,
и то, что дубль, прошедший мимо кода, отвергает сама база.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.payments.conftest import USER_ID, counts, successful_payment_update


async def _paid_once(service, session_factory, inv, charge_id):
    c = await counts(session_factory)
    assert c["star_payments"] == 1
    assert c["star_grants"] == 1
    assert c["star_processed_events"] == 1
    assert await service.has_access(USER_ID, "report_full") is True
    async with session_factory() as s:
        st = (await s.execute(text("SELECT status FROM star_orders"))).scalar_one()
    assert st == "active"


async def test_sequential_duplicate_update(service, session_factory, dp, bot):
    inv = await service.create_invoice(USER_ID, "report_full")
    upd = successful_payment_update(inv.payload, inv.price_xtr, "ch-seq-1")
    for _ in range(3):
        await dp.feed_update(bot, upd)
    await _paid_once(service, session_factory, inv, "ch-seq-1")


@pytest.mark.parametrize("n", [2, 8])
async def test_parallel_duplicate_updates(service, session_factory, dp, bot, n):
    inv = await service.create_invoice(USER_ID, "report_full")
    charge = f"ch-par-{n}"
    upds = [successful_payment_update(inv.payload, inv.price_xtr, charge) for _ in range(n)]
    await asyncio.gather(*(dp.feed_update(bot, u) for u in upds))
    await _paid_once(service, session_factory, inv, charge)


async def test_parallel_apply_outcomes(service, session_factory):
    from lunora.payments.stars import ApplyOutcome, PaymentSnapshot

    inv = await service.create_invoice(USER_ID, "report_full")
    snap = PaymentSnapshot("ch-out", USER_ID, "XTR", inv.price_xtr, inv.payload)
    res = await asyncio.gather(*(service.apply_payment(snap, source="update") for _ in range(5)))
    assert sorted(res) == sorted([ApplyOutcome.GRANTED] + [ApplyOutcome.DUPLICATE] * 4)


async def test_unique_indexes_exist(session_factory):
    """Гарантия — в схеме: уникальные индексы на ключах идемпотентности."""
    q = text(
        "SELECT tablename, indexdef FROM pg_indexes WHERE tablename LIKE 'star_%' "
        "AND indexdef LIKE 'CREATE UNIQUE INDEX%'"
    )
    async with session_factory() as s:
        rows = [(t, d) for t, d in (await s.execute(q)).all()]
    defs = " | ".join(d for _, d in rows)
    assert any(t == "star_payments" and "(telegram_payment_charge_id)" in d for t, d in rows), defs
    assert any(t == "star_grants" and "(order_id)" in d for t, d in rows), defs
    assert any(t == "star_processed_events" and "(kind, event_key)" in d for t, d in rows), defs
    assert any(t == "star_refunds" and "(payment_id)" in d for t, d in rows), defs


async def test_db_rejects_duplicate_charge_bypassing_code(service, session_factory):
    """Дубль, вставленный мимо сервиса, отвергает сама PostgreSQL."""
    from lunora.payments.stars import PaymentSnapshot

    inv = await service.create_invoice(USER_ID, "report_full")
    await service.apply_payment(
        PaymentSnapshot("ch-raw", USER_ID, "XTR", inv.price_xtr, inv.payload), source="update"
    )
    async with session_factory() as s:
        order_id = (await s.execute(text("SELECT id FROM star_orders"))).scalar_one()
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO star_payments (id, order_id, telegram_payment_charge_id, "
                    "telegram_user_id, currency, total_amount, source, status) VALUES "
                    "(:id, :o, 'ch-raw', :u, 'XTR', :a, 'update', 'succeeded')"
                ),
                {"id": uuid.uuid4(), "o": order_id, "u": USER_ID, "a": inv.price_xtr},
            )
        await s.rollback()
        with pytest.raises(IntegrityError):
            await s.execute(
                text(
                    "INSERT INTO star_grants (id, order_id, telegram_user_id, sku, status) "
                    "VALUES (:id, :o, :u, 'report_full', 'active')"
                ),
                {"id": uuid.uuid4(), "o": order_id, "u": USER_ID},
            )
        await s.rollback()


async def test_second_charge_same_order_no_second_access(service, session_factory):
    """Другой charge_id на уже оплаченный заказ: деньги учтены (paid_late), доступ один."""
    from lunora.payments.stars import ApplyOutcome, PaymentSnapshot

    inv = await service.create_invoice(USER_ID, "report_full")
    a = await service.apply_payment(
        PaymentSnapshot("ch-a", USER_ID, "XTR", inv.price_xtr, inv.payload), source="update"
    )
    b = await service.apply_payment(
        PaymentSnapshot("ch-b", USER_ID, "XTR", inv.price_xtr, inv.payload), source="update"
    )
    assert (a, b) == (ApplyOutcome.GRANTED, ApplyOutcome.PAID_LATE)
    c = await counts(session_factory)
    assert c["star_payments"] == 2 and c["star_grants"] == 1
    async with session_factory() as s:
        q = text("SELECT telegram_payment_charge_id, status FROM star_payments")
        st = dict((await s.execute(q)).all())
    assert st == {"ch-a": "succeeded", "ch-b": "paid_late"}
