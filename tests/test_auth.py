"""Юнит-тесты авторизации Telegram Mini App (проверка подписи initData).

IDOR-фикс: без доверенного telegram_id из подписанной initData любой UUID отдавал чужую карту.
"""

from __future__ import annotations

import time

import pytest

from lunora.api.auth import (
    InitDataError,
    telegram_id_from_init_data,
    verify_init_data,
)
from tests.auth_helpers import TEST_BOT_TOKEN, build_init_data


def test_valid_init_data_passes_and_yields_telegram_id():
    init = build_init_data(700_100_777)
    data = verify_init_data(init, TEST_BOT_TOKEN)
    assert data["hash"]
    assert telegram_id_from_init_data(init, TEST_BOT_TOKEN) == 700_100_777


def test_tampered_signature_rejected():
    init = build_init_data(700_100_777, tamper=True)
    with pytest.raises(InitDataError) as e:
        verify_init_data(init, TEST_BOT_TOKEN)
    assert e.value.code == "bad_signature"


def test_wrong_bot_token_rejected():
    init = build_init_data(700_100_777, bot_token="999:OTHER")
    with pytest.raises(InitDataError) as e:
        verify_init_data(init, TEST_BOT_TOKEN)
    assert e.value.code == "bad_signature"


def test_empty_bot_token_fails_closed():
    init = build_init_data(700_100_777)
    with pytest.raises(InitDataError) as e:
        verify_init_data(init, "")
    assert e.value.code == "server_misconfigured"


def test_missing_init_data_rejected():
    with pytest.raises(InitDataError) as e:
        verify_init_data("", TEST_BOT_TOKEN)
    assert e.value.code == "missing"


def test_no_hash_rejected():
    with pytest.raises(InitDataError) as e:
        verify_init_data("auth_date=1&user=%7B%7D", TEST_BOT_TOKEN)
    assert e.value.code == "no_hash"


def test_expired_init_data_rejected():
    old = int(time.time()) - 10 * 24 * 60 * 60
    init = build_init_data(700_100_777, auth_date=old)
    with pytest.raises(InitDataError) as e:
        verify_init_data(init, TEST_BOT_TOKEN, max_age_seconds=86400)
    assert e.value.code == "expired"


def test_fresh_within_window_passes():
    recent = int(time.time()) - 60
    init = build_init_data(700_100_777, auth_date=recent)
    data = verify_init_data(init, TEST_BOT_TOKEN, max_age_seconds=86400, now=time.time())
    assert data


def test_signature_covers_user_field_tampering():
    # Подпись должна покрывать user: подменённый id ломает проверку.
    init = build_init_data(700_100_777)
    forged = init.replace("700100777", "700100000")
    with pytest.raises(InitDataError) as e:
        verify_init_data(forged, TEST_BOT_TOKEN)
    assert e.value.code == "bad_signature"
