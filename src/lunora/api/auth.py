"""Аутентификация Telegram Mini App по подписи initData (Broken Object Level Authorization).

Telegram подписывает initData HMAC-SHA256, где ключ = HMAC-SHA256("WebAppData", bot_token).
Сервер проверяет подпись на каждом запросе и достаёт telegram_id из поля `user` — это
единственный доверенный источник владельца. `user_id` из пути/тела нельзя считать за право
доступа: любой UUID иначе отдаёт чужую карту (IDOR). См. docs/gates — фикс авторизации.

Токен бота — секрет (переменная окружения LUNORA_BOT_TOKEN), в код/логи/чат не попадает.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from lunora.config import settings

# Окно свежести initData: Telegram кладёт auth_date (unix-время выдачи). Старее суток — отказ,
# чтобы перехваченная строка не работала вечно.
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60


class InitDataError(Exception):
    """Невалидная initData. `code` — машинный, `message` — человекочитаемый."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _data_check_string(pairs: list[tuple[str, str]]) -> str:
    # Все пары, кроме hash, отсортированы по ключу и склеены "\n" (спец. Telegram WebApp).
    return "\n".join(f"{k}={v}" for k, v in sorted(pairs) if k != "hash")


def verify_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int | None = DEFAULT_MAX_AGE_SECONDS,
    now: float | None = None,
) -> dict[str, str]:
    """Проверить подпись initData и (опц.) свежесть. Вернуть разобранные поля или бросить."""
    if not bot_token:
        # Пустой токен = сервер не настроен. Fail-closed: лучше отказать, чем пустить всех.
        raise InitDataError("server_misconfigured", "токен бота не настроен на сервере")
    if not init_data:
        raise InitDataError("missing", "initData отсутствует")

    pairs = parse_qsl(init_data, keep_blank_values=True)
    data = dict(pairs)
    provided_hash = data.get("hash")
    if not provided_hash:
        raise InitDataError("no_hash", "в initData нет подписи")

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(
        secret_key, _data_check_string(pairs).encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(computed, provided_hash):
        raise InitDataError("bad_signature", "подпись initData не сошлась")

    if max_age_seconds is not None:
        auth_date = data.get("auth_date", "")
        if not auth_date.isdigit():
            raise InitDataError("no_auth_date", "в initData нет auth_date")
        age = (now if now is not None else time.time()) - int(auth_date)
        if age > max_age_seconds:
            raise InitDataError("expired", "initData просрочена")

    return data


def telegram_id_from_init_data(
    init_data: str,
    bot_token: str | None = None,
    *,
    max_age_seconds: int | None = DEFAULT_MAX_AGE_SECONDS,
) -> int:
    """Проверить initData и достать telegram_id из поля `user`."""
    token = settings.bot_token if bot_token is None else bot_token
    data = verify_init_data(init_data, token, max_age_seconds=max_age_seconds)
    user_raw = data.get("user")
    if not user_raw:
        raise InitDataError("no_user", "в initData нет пользователя")
    try:
        user = json.loads(user_raw)
        return int(user["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InitDataError("bad_user", "пользователь в initData не разобран") from exc


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(401, {"error": "unauthorized", "code": code, "message": message})


async def require_telegram_id(authorization: str | None = Header(default=None)) -> int:
    """FastAPI-зависимость: достаёт и проверяет initData из заголовка `Authorization: tma <...>`.

    Возвращает доверенный telegram_id или бросает 401. Это единственный источник владельца —
    маршруты сверяют с ним user_id из пути/тела и дают 403 при несовпадении.
    """
    if not authorization:
        raise _unauthorized("missing_auth", "нужен заголовок Authorization с initData")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "tma" or not token:
        raise _unauthorized("bad_scheme", "ожидается схема 'tma <initData>'")
    try:
        return telegram_id_from_init_data(token)
    except InitDataError as exc:
        raise _unauthorized(exc.code, exc.message) from exc
