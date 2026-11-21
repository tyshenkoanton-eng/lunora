"""Минимальный контракт результата движка (G17-S2, решение Антона №5).

Одна величина движка — `Result`:
  - `value` — посчитанное значение (без округления для отображения), либо `None`;
  - `rule` — идентификатор правила спеки и его версия (semver; `0.x` до подписи практика,
    ENGINE-SPEC §1.3);
  - `stability` — тег ARCHITECTURE §4.5 (`stable` / `range` / `undetermined`) или
    `convention`, если значение зависит от выбора метода;
  - `not_computed` — причина из ENGINE-SPEC §1.2, если величина не считается. Тогда
    `value is None`: частичный результат под видом полного не выдаётся (fail closed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

NOT_COMPUTED_REASONS = frozenset(
    {
        "no_birth_time",
        "no_place",
        "no_sex",
        "not_applicable_latitude",
        "rule_not_formalized",
        "out_of_v1",
        "table_not_verified",
    }
)
STABILITY_TAGS = frozenset({"stable", "range", "undetermined", "convention"})
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True, slots=True)
class Rule:
    """Правило расчёта: ID из спеки и его версия (semver)."""

    id: str
    version: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("rule id пуст")
        if not _SEMVER.match(self.version):
            raise ValueError(f"версия правила не semver: {self.version!r}")


@dataclass(frozen=True, slots=True)
class Result:
    """Одна величина движка: значение по правилу либо `not_computed` с причиной."""

    rule: Rule
    value: Any = None
    stability: str = "stable"
    not_computed: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.stability not in STABILITY_TAGS:
            raise ValueError(f"неизвестный тег stability: {self.stability!r}")
        if self.not_computed is not None:
            if self.not_computed not in NOT_COMPUTED_REASONS:
                raise ValueError(f"неизвестная причина not_computed: {self.not_computed!r}")
            if self.value is not None:
                raise ValueError("у not_computed не может быть значения")

    @classmethod
    def computed(
        cls, rule: Rule, value: Any, *, stability: str = "stable", **detail: Any
    ) -> Result:
        return cls(rule=rule, value=value, stability=stability, detail=dict(detail))

    @classmethod
    def missing(cls, rule: Rule, reason: str, **detail: Any) -> Result:
        return cls(rule=rule, not_computed=reason, detail=dict(detail))

    @property
    def is_computed(self) -> bool:
        return self.not_computed is None
