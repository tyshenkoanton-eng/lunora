# Лунора

Мультисистемный астрологический оракул — Telegram Mini App.

Персональные разборы по 4 системам: западная астрология, ведическая (Джйотиш), китайская (Ба-Цзы), нумерология.

## Стек

- Python 3.12, FastAPI, aiogram 3
- PostgreSQL, Redis
- Docker Compose, Caddy

## Запуск

```bash
cp .env.example .env
# заполнить LUNORA_BOT_TOKEN
docker compose up --build
```

## Лицензия

AGPL-3.0
