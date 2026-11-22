# Живой смоук оплаты Telegram Stars (G17-S3a) — протокол

**Статус:** НЕ ПРОВЕДЁН — ручной, с Антоном, вне CI. Агент сам не запускает.
**Код:** `python -m lunora.payments.smoke` (`src/lunora/payments/smoke.py`), SKU `spike_smoke` = 1 ⭐.

## Где проводить

1. **Сначала — тестовая среда Telegram** (без реальных звёзд). Документация Bot API
   (core.telegram.org/bots/payments-stars): платежи Stars можно свободно тестировать, подключив
   бота к выделенной тестовой среде. Запросы — `https://api.telegram.org/bot<token>/test/<method>`.
   Нужны: аккаунт в тестовой среде Telegram и бот, созданный у @BotFather **внутри** неё.
   Не подтверждено (core.telegram.org закрыт из облачной среды): как пополняется баланс Stars
   в тестовой среде и отдаёт ли там `getStarTransactions` те же записи — проверим на месте.
2. **Если тестовая среда не даёт пройти сценарий** — боевая среда, 1 ⭐, сразу возврат.

## Шаги (окружение: `.env` с `LUNORA_BOT_TOKEN`, `LUNORA_DATABASE_URL`; тестовая среда — `LUNORA_TELEGRAM_TEST_ENV=1`)

1. `alembic upgrade head` на базе смоука.
2. `python -m lunora.payments.smoke poll` — бот принимает `pre_checkout_query`/`successful_payment`.
3. `python -m lunora.payments.smoke invoice --user-id <ваш Telegram id>` → ссылка на инвойс 1 ⭐.
4. Оплатить по ссылке. Ожидание: `answerPreCheckoutQuery(ok)`, в логе `stars.granted`.
5. `python -m lunora.payments.smoke reconcile` → платёж виден, `duplicates=1`, новых выдач 0.
6. `python -m lunora.payments.smoke refund --charge <telegram_payment_charge_id>` → `refunded`;
   повтор → `already_refunded` (S5).
7. `python -m lunora.payments.smoke reconcile` → журнал показывает платёж и возврат.

## Протокол (заполняется по факту; без ПДн — без имени, username, номера)

| Поле | Значение |
| --- | --- |
| Дата/время (UTC) | — |
| Среда | тестовая / боевая |
| `telegram_payment_charge_id` | — |
| Сумма | — ⭐ |
| pre_checkout ok | — |
| Доступ выдан (`stars.granted`) | — |
| Возврат `refundStarPayment` | — |
| Повторный возврат = no-op | — |
| `getStarTransactions`: платёж + возврат | — |
| Скриншот | SHA-256: — (сам скриншот в git не кладём) |
