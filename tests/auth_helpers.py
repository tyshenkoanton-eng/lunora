"""Хелпер: собрать корректно подписанную Telegram initData для тестов авторизации."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

TEST_BOT_TOKEN = "123456:TEST-bot-token-for-signing"  # noqa: S105 — тестовый, не секрет


def build_init_data(
    telegram_id: int,
    *,
    bot_token: str = TEST_BOT_TOKEN,
    auth_date: int | None = None,
    extra_user: dict | None = None,
    tamper: bool = False,
) -> str:
    """Собрать подписанную initData. `tamper=True` портит подпись (для негативных тестов)."""
    user = {"id": telegram_id, "first_name": "Тест"}
    if extra_user:
        user.update(extra_user)
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAB",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if tamper:
        signature = ("0" * len(signature))[:-1] + ("1" if signature[-1] != "1" else "2")
    return urlencode({**fields, "hash": signature})
