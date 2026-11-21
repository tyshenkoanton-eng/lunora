"""Движки школ G17-S2 поверх ядра (эфемериды, время/пояса, допуск времени).

Пакет заменяет прототипные `lunora.calc.{western,vedic,chinese,numerology}`. Здесь — только
расчёт величин и минимальный контракт результата (решение Антона №5, 2026-11-21); полный
`Signal` с `can_vote`, `frame`, `family_id` и голосованием — слой выше, S4.
"""

from lunora.engines.result import NOT_COMPUTED_REASONS, STABILITY_TAGS, Result, Rule

__all__ = ["NOT_COMPUTED_REASONS", "STABILITY_TAGS", "Result", "Rule"]
