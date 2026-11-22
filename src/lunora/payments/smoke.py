"""Живой смоук Stars (G17-S3a) — запускает ЧЕЛОВЕК, вручную, вне CI.

Сначала тестовая среда Telegram (``LUNORA_TELEGRAM_TEST_ENV=1``, бот из тестового @BotFather),
иначе — 1 ⭐ в боевой среде с возвратом. Протокол — ``docs/current/spike/payment_smoke.md``.

    python -m lunora.payments.smoke poll                     # бот принимает оплату (long polling)
    python -m lunora.payments.smoke invoice --user-id <id>   # ссылка на инвойс spike_smoke (1 ⭐)
    python -m lunora.payments.smoke refund --charge <id>     # полный возврат (S5)
    python -m lunora.payments.smoke reconcile                # сверка по getStarTransactions (S4)
"""

from __future__ import annotations

import argparse
import asyncio
import logging


async def _run(args: argparse.Namespace) -> None:
    from lunora.bot.setup import bot, dp, stars

    try:
        if args.cmd == "poll":
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(
                bot, allowed_updates=["message", "pre_checkout_query", "callback_query"]
            )
        elif args.cmd == "invoice":
            inv = await stars.create_invoice(args.user_id, args.sku)
            print(f"order_id={inv.order_id} price_xtr={inv.price_xtr}\n{inv.link}")
        elif args.cmd == "refund":
            print((await stars.refund(args.charge)).value)
        elif args.cmd == "reconcile":
            rep = await stars.reconcile()
            print(
                f"pages={rep.pages} granted={rep.granted} duplicates={rep.duplicates} "
                f"mismatched={rep.mismatched} refunded={rep.refunded} ignored={rep.ignored}"
            )
            for charge, outcome in rep.outcomes:
                print(f"  {charge} {outcome}")
    finally:
        await bot.session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(prog="lunora.payments.smoke")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("poll")
    inv = sub.add_parser("invoice")
    inv.add_argument("--user-id", type=int, required=True)
    inv.add_argument("--sku", default="spike_smoke")
    rf = sub.add_parser("refund")
    rf.add_argument("--charge", required=True)
    sub.add_parser("reconcile")
    asyncio.run(_run(p.parse_args()))


if __name__ == "__main__":
    main()
