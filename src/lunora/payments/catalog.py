"""Каталог продуктов для оплаты Stars. Цена — в XTR (целые звёзды), S3 §2.4b.

Реальные цены — `ПРАЙС §5` (бизнес-решение, вне G17-S3a); здесь только SKU спайка.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace


class UnknownProduct(KeyError):
    pass


@dataclass(frozen=True)
class StarProduct:
    sku: str
    title: str  # 1–32 символа (Bot API)
    description: str  # 1–255 символов (Bot API)
    price_xtr: int

    def __post_init__(self) -> None:
        if not isinstance(self.price_xtr, int) or self.price_xtr <= 0:
            raise ValueError(f"цена {self.sku!r} должна быть целым числом звёзд > 0")
        if not 1 <= len(self.title) <= 32 or not 1 <= len(self.description) <= 255:
            raise ValueError(f"title/description {self.sku!r} вне лимитов Bot API")


class Catalog:
    def __init__(self, products: Iterable[StarProduct]) -> None:
        self._items = {p.sku: p for p in products}

    def get(self, sku: str) -> StarProduct:
        try:
            return self._items[sku]
        except KeyError:
            raise UnknownProduct(sku) from None

    def set_price(self, sku: str, price_xtr: int) -> None:
        """Смена прайса: действует на новые инвойсы, выставленные заказы не трогает (S3)."""
        self._items[sku] = replace(self.get(sku), price_xtr=price_xtr)


DEFAULT_CATALOG = Catalog(
    [StarProduct("spike_smoke", "Проверка оплаты", "Тестовая покупка за 1 звезду", 1)]
)
