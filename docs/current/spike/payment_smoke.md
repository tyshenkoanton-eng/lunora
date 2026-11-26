# Живой смоук оплаты Telegram Stars (G17-S3a) — протокол

**Статус:** ПРОВЕДЁН — PASS, 2026-11-26. Боевая среда, 1 ⭐, оплата и возврат на живом боте.
**Код:** `python -m lunora.payments.smoke` (`src/lunora/payments/smoke.py`), SKU `spike_smoke` = 1 ⭐.

## Где проводили

Тестовая среда Telegram не подошла: вход в тест-DC в клиенте не нашёлся, отдельного тестового
бота у @BotFather в тест-среде нет. Пошли по запасному плану из карточки — **боевая среда, 1 ⭐
с немедленным возвратом**. Бот — боевой, оплата настоящая, звезда возвращена полностью.

**Запуск — из облачной среды проекта** (у исполнителя нет локального окружения; на Mac — нет):
в сетевой доступ среды добавлен хост `api.telegram.org`; токен боевого бота — в переменной
среды `LUNORA_BOT_TOKEN` (в чат не попадал); PostgreSQL поднят разово в контейнере,
схема — `alembic upgrade head`; бот запущен `smoke poll` (long polling через агент-прокси,
`LUNORA_TELEGRAM_PROXY`), боевой DC (без `LUNORA_TELEGRAM_TEST_ENV`). Оплату 1 ⭐ Антон провёл
со своего Telegram; исполнитель разобрал логи и состояние БД.

## Шаги (как прошли)

1. `alembic upgrade head` на базе смоука — ОК (до ревизии 003).
2. `smoke poll` — бот `@lunerabrainbot` слушает.
3. `smoke invoice --user-id <id Антона>` → ссылка на инвойс 1 ⭐ (заказ привязан к плательщику).
4. Оплата по ссылке → `answerPreCheckoutQuery(ok)`, в логе `stars.granted` (доступ выдан).
5. `smoke reconcile` → платёж найден в `getStarTransactions`, `duplicates=1`, новых выдач 0.
6. `smoke refund --charge <id>` → `refunded`; повтор → `already_refunded` без второго списания.
7. `smoke reconcile` → идемпотентно, двойного учёта нет.

## Протокол (без ПДн — без имени, username, номера, Telegram id плательщика)

| Поле | Значение |
| --- | --- |
| Дата/время (UTC) | 2026-11-26 ~15:54 |
| Среда | боевая (боевой бот `@lunerabrainbot`, настоящая 1 ⭐) |
| Запуск | облачная среда проекта (host `api.telegram.org` открыт, токен в `LUNORA_BOT_TOKEN`) |
| `telegram_payment_charge_id` | `stx-8s7DfcLxcuPjvfQp61CF1fcLIew0DszK_Rr9vPa1XVbYnUUsxMUlqpD4UXerX0HA39OHy3wJEnX_6s3X48Mn6PzF_3pnjgDXOuZlWhZiVP-ozqvwn8lkhgAXT_4vgtw` |
| Сумма | 1 ⭐ (`XTR`, `total_amount=1`) |
| pre_checkout ok | да (оплата прошла → `stars.granted`) — S2 |
| Цена зафиксирована в XTR | да (`price_xtr=1`, платёж совпал) — S3 |
| Доступ выдан (`stars.granted`) | да, один (заказ `active`, один грант) — S1 |
| Сверка `getStarTransactions` | платёж найден, `duplicates=1`, `granted=0` — S4 |
| Возврат `refundStarPayment` | `refunded` (полная сумма 1 ⭐) — S5 |
| Повторный возврат = no-op | `already_refunded`, без второго вызова API — S5 |
| Итог в БД | заказ `refunded`, платёж `refunded_full`, грант `revoked`, возврат `succeeded` origin `bot` |
| Скриншот | не прикладывали (ПДн в UI оплаты); факты — из логов и БД |

## Вывод

Все пять правил S1–S5 подтверждены на живом платеже в боевой среде. Звезда возвращена
плательщику полностью. G17-S3a закрыт полностью (офлайн + живой смоук).
