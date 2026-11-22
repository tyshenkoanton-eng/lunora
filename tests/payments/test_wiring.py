"""Рантайм: роутер Stars подключён к боту раньше общего catch-all; тестовая среда — /test/."""


def test_stars_router_before_catch_all():
    from lunora.bot.setup import dp

    names = [r.name for r in dp.sub_routers]
    assert names[0] == "stars_payments", names


def test_test_env_server_url():
    from aiogram.client.telegram import TEST

    assert TEST.api_url("T", "getMe").endswith("/botT/test/getMe")


def test_default_catalog_smoke_is_one_star():
    from lunora.payments.catalog import DEFAULT_CATALOG

    assert DEFAULT_CATALOG.get("spike_smoke").price_xtr == 1
