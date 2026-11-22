<!-- reference -->
# Close-record G17-S3a — адаптер оплаты Telegram Stars (S1–S5)

**Дата:** 2026-11-22 · **Слайс:** G17-S3a (оплата Stars; остаток спайка ядра) ·
**Вердикт:** PASS (офлайн-доказательство). **Живой смоук — открытый пункт** (ручной, с Антоном).
**Критерий:** зелёные `make verify` (773 passed, 46 skipped) и `make slice-check`
(накопительно S1 + S2a + S2c + S2b + S2d + S2e + S3a; `slice-check-s3a` — 44 passed на
настоящей PostgreSQL). Карточка — [../current/G17-S3-план.md](../current/G17-S3-план.md).
Контракт — `docs/grillmax/TRANSACTIONS-КОНТРАКТЫ.md` §2.4b.

## Что сделано

- **Миграция `002_star_payments`** — пять таблиц `star_*`; гарантии идемпотентности в схеме:
  `star_processed_events UNIQUE(kind, event_key)`, `star_payments UNIQUE(telegram_payment_charge_id)`,
  `star_grants UNIQUE(order_id)`, `star_refunds UNIQUE(payment_id)`; `star_orders`:
  `CHECK currency='XTR'`, `CHECK price_xtr>0`. Прототипные `payment_orders`/`entitlements` не тронуты.
- **`lunora.payments`** — `catalog` (SKU в XTR; в рантайме только `spike_smoke` = 1 ⭐),
  `stars.StarsService` + `AiogramStarsApi`, `telegram.build_router` (aiogram), `smoke` (CLI ручного
  смоука). Роутер Stars подключён в `bot/setup.py` раньше общего catch-all;
  `LUNORA_TELEGRAM_TEST_ENV=1` переводит бота в тестовую среду Telegram (`/bot<token>/test/…`).

## Доказательство S1–S5 (офлайн, `tests/payments`, 44 теста)

Настоящие `aiogram.Bot` и `Dispatcher.feed_update`, подменена только HTTP-сессия Bot API
(записывает вызовы, ведёт журнал Stars, на повторный возврат отвечает `CHARGE_ALREADY_REFUNDED`).
PostgreSQL — временный кластер (`initdb`/`pg_ctl`) или `LUNORA_TEST_PG_DSN`; схема —
`alembic upgrade head`. В `slice-check` без PostgreSQL тесты **падают** (`LUNORA_REQUIRE_PG=1`),
в `verify` — пропускаются.

| Правило | Что доказано |
|---|---|
| **S2** | на каждый `pre_checkout_query` — ровно один `answerPreCheckoutQuery`: `ok=True` при валидном заказе и цене в XTR; `ok=False` + текст на «вы» без внутренностей — неизвестный/битый payload, чужой пользователь, другая сумма, другая валюта, уже оплачен, **внутренний сбой** проверки (бюджет 7 с из ~10 с) |
| **S1** | 3 последовательных и 2/8 параллельных `successful_payment` с одним charge_id → 1 платёж, 1 доступ, заказ `active`; 5 параллельных `apply_payment` → 1 `GRANTED` + 4 `DUPLICATE`; уникальные индексы есть в `pg_indexes`; дубль, вставленный **в обход кода**, отвергает PostgreSQL (`IntegrityError`); второй charge на тот же заказ → `paid_late`, второго доступа нет. **Мутация:** без уникальных индексов 6 из 7 тестов S1 красные — гарантия в индексе, не в коде |
| **S3** | `createInvoiceLink`: `XTR`, одна позиция, без `provider_token`, payload ≤128 байт и без ПДн; снимок `price_xtr` в заказе; смена прайса после инвойса снимок не двигает; недоплата/переплата/`RUB`/чужой пользователь → `reconcile_needed`, доступа нет; `CHECK` в БД отвергает не-XTR и цену ≤0 |
| **S4** | потерянный `successful_payment` найден по `getStarTransactions` и засчитан (`source=reconcile`); повтор сверки и запоздалое обновление — no-op; пагинация по 100 (offset 0/100/200), чужие платежи игнорируются; несовпадение суммы в журнале — не засчитано; возврат, видимый в журнале, применяется без повторного `refundStarPayment` |
| **S5** | у `RefundStarPayment` нет параметра суммы (только `user_id`, `telegram_payment_charge_id`); возврат — один вызов API, `amount_xtr` = полной сумме, платёж `refunded_full`, заказ `refunded`, доступ `revoked`; повтор и 5 параллельных возвратов → один вызов API; неизвестный charge → без вызова; сбой сети → возврат не засчитан, доступ сохраняется, повтор доводит; `CHARGE_ALREADY_REFUNDED` = возврат состоялся; `refunded_payment` из Telegram снимает доступ; после возврата возможна новая покупка |

## Микрорешения

- **Переплата в Stars не исполняется молча** (`reconcile_needed`): вернуть разницу у Stars нельзя
  (§3.6, только полный возврат) — отличие от ЮKassa §3.3, где переплата исполняется и разница
  возвращается.
- **`refund` держит `FOR UPDATE` на платеже на время `refundStarPayment`** — «ровно один успешный
  вызов» без отдельной очереди; операция редкая.
- **Сверка идёт по журналу от старых к новым** — возврат применяется после своего платежа.
- **`migrations/env.py`**: ruff 0.16 (I001) валил `make verify` уже на main — длинные
  `noqa`-комментарии укорочены, смысл сохранён.

## Открыто

- **Живой смоук** — протокол и шаги: [../current/spike/payment_smoke.md](../current/spike/payment_smoke.md).
  Сначала тестовая среда Telegram (по документации Bot API Stars там можно тестировать без реальных
  звёзд), иначе 1 ⭐ в боевой с возвратом. Проводит Антон; агент не запускает.
- **Документация Bot API** (core.telegram.org) из облачной среды закрыта — вывод о тестовой среде
  сделан по выдаче поиска и докстрингам aiogram (зеркало Bot API); детали пополнения баланса в
  тестовой среде проверить на смоуке.
- **Оракулы в этой среде не поставились** (`make setup-oracle`: сборка `pyswisseph` падает на
  Python 3.13/setuptools) — дифф-тесты прошлых слайсов в `slice-check` пропущены (skip), не
  красные. К S3a не относится.

## Вне scope (held)

G17-S3b — стоимость LLM (ждёт решения Антона по модели). ЮKassa/СБП (§2.4a). Чеки/налоги по
Stars (юрист+бухгалтер). Реальные цены (`ПРАЙС §5`). Авто-возврат `paid_late`/дубля/
`reconcile_needed` (§4) — состояние и алерт в логе есть, сам авто-возврат — при продуктовом
переносе. Алерт «charge без исхода старше порога» (S4) — с мониторингом. Уведомление пользователю
об оплате — через outbox (§6), позже.
