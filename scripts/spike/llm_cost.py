#!/usr/bin/env python3
"""llm_cost — сверка артефакта замера стоимости LLM с порогами R-05 (гейт G17-S3b).

Офлайн: ни сети, ни ключей. Режим --check проверяет артефакт
docs/current/spike/llm_cost.json по схеме scripts/spike/llm_cost.schema.json
(валидация на стандартной библиотеке, без новых зависимостей) и сверяет его
с порогами scripts/spike/llm_cost_thresholds.json. Числа порогов берутся только
из файла порогов — в коде их нет.

Единица артефакта (интерфейс для живого замера, задача S3b-04):
  cost_rub — распределение (медиана и p90) себестоимости ОДНОГО вызова модели
  по сценарию; usage.input_tokens/output_tokens — то же распределение по токенам.
  Периодные пороги пересчитываются через calls_per_card артефакта: диалог —
  25 вопросов в сутки, документ — 1 документ, прогноз — 7 дней в месяц
  (описание поля calls_per_card в scripts/spike/llm_cost.schema.json;
  docs/grillmax/05_business.md §3.1 и §3.5). Если артефакт записан в другой
  единице, чекер падает с превышением порога, а не проходит молча.

Запуск:  python scripts/spike/llm_cost.py --check [--root <корень репозитория>]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any, NamedTuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACT = pathlib.Path("docs/current/spike/llm_cost.json")
SCHEMA = pathlib.Path("scripts/spike/llm_cost.schema.json")
THRESHOLDS = pathlib.Path("scripts/spike/llm_cost_thresholds.json")

# Сколько вызовов модели на карту фиксирует методика замера (описание поля
# calls_per_card в scripts/spike/llm_cost.schema.json; 05_business.md §3.1/§3.5).
# Единицы периодных порогов выведены из этих чисел, поэтому артефакт проверяется.
CALLS_PER_CARD = {"dialog": 25, "document": 1, "forecast": 7}

# (сценарий, метрика порога) → (единица измерения, множитель). Множитель "calls" —
# это calls_per_card артефакта, "one" — цена одного вызова без пересчёта.
CASES = {
    ("dialog", "max_rub_per_day"): ("₽/сутки", "calls"),
    ("dialog", "max_rub_per_question"): ("₽/вопрос", "one"),
    ("document", "max_rub"): ("₽/документ", "calls"),
    ("forecast", "max_rub_per_user_month"): ("₽/пользователь/мес", "calls"),
}

# ── Валидация по схеме (подмножество JSON Schema 2020-12 на stdlib) ──────────

# Аннотации не ограничивают значение — их просто пропускаем.
ANNOTATION_KEYWORDS = {
    "$comment",
    "$id",
    "$schema",
    "default",
    "deprecated",
    "description",
    "examples",
    "readOnly",
    "title",
    "writeOnly",
}

# Ограничения, которые валидатор действительно проверяет.
CONSTRAINT_KEYWORDS = {
    "$defs",
    "$ref",
    "additionalProperties",
    "const",
    "enum",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "items",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "pattern",
    "properties",
    "required",
    "type",
}


def _same(left: Any, right: Any) -> bool:
    """Равенство как в JSON: true и 1 — разные значения."""
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return left == right


def _is_type(value: Any, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        return isinstance(value, float) and value.is_integer()
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _resolve_ref(ref: str, root: dict) -> Any:
    """Разрешить локальный $ref вида #/$defs/dist; иначе None."""
    if not ref.startswith("#/"):
        return None
    node: Any = root
    for part in ref[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _validate(instance: Any, schema: Any, root: dict, path: str, errors: list[str]) -> None:
    if not isinstance(schema, dict):
        errors.append(f"{path}: схема задана не объектом — проверка невозможна")
        return
    for keyword in sorted(set(schema) - CONSTRAINT_KEYWORDS - ANNOTATION_KEYWORDS):
        errors.append(f"{path}: неподдерживаемое ключевое слово схемы {keyword!r}")
    ref = schema.get("$ref")
    if ref is not None:
        target = _resolve_ref(str(ref), root)
        if target is None:
            errors.append(f"{path}: не найден $ref {ref!r}")
            return
        _validate(instance, target, root, path, errors)
    types = schema.get("type")
    if types is not None:
        names = types if isinstance(types, list) else [types]
        if not any(_is_type(instance, str(name)) for name in names):
            errors.append(f"{path}: тип {type(instance).__name__} не соответствует {types}")
            return
    if "enum" in schema and not any(_same(instance, item) for item in schema["enum"]):
        errors.append(f"{path}: значение {instance!r} не входит в {schema['enum']}")
    if "const" in schema and not _same(instance, schema["const"]):
        errors.append(f"{path}: значение {instance!r} ≠ const {schema['const']!r}")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: строка короче minLength={schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: строка длиннее maxLength={schema['maxLength']}")
        pattern = schema.get("pattern")
        if pattern is not None and re.search(str(pattern), instance) is None:
            errors.append(f"{path}: строка не совпадает с шаблоном {pattern!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: значение {instance} < minimum={schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: значение {instance} > maximum={schema['maximum']}")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append(
                f"{path}: значение {instance} ≤ exclusiveMinimum={schema['exclusiveMinimum']}"
            )
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            errors.append(
                f"{path}: значение {instance} ≥ exclusiveMaximum={schema['exclusiveMaximum']}"
            )
    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}: нет обязательного поля {name!r}")
        if schema.get("additionalProperties") is False:
            for name in instance:
                if name not in properties:
                    errors.append(f"{path}: лишнее поле {name!r}")
        for name, sub in properties.items():
            if name in instance:
                _validate(instance[name], sub, root, f"{path}.{name}", errors)
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: элементов {len(instance)} < minItems={schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: элементов {len(instance)} > maxItems={schema['maxItems']}")
        items = schema.get("items")
        if items is not None:
            for index, item in enumerate(instance):
                _validate(item, items, root, f"{path}[{index}]", errors)


def validate(instance: Any, schema: dict) -> list[str]:
    """Ошибки артефакта по схеме; пустой список — артефакт валиден."""
    errors: list[str] = []
    _validate(instance, schema, schema, "$", errors)
    return errors


# ── Сверка с порогами ────────────────────────────────────────────────────────


def _fmt(value: float) -> str:
    if value == 0:
        return "0"
    if 1e-4 <= abs(value) < 1e7:
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{value:g}"


def _load_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


class Check(NamedTuple):
    lines: list[str]
    failed: bool
    summary: str


def compare(artifact: dict, thresholds: dict) -> tuple[list[str], bool, str]:
    """Строки отчёта, признак провала и номер варианта порогов."""
    lines: list[str] = []
    verdict = artifact.get("verdict", {})
    variant = str(verdict.get("threshold_variant", "?"))
    variants = thresholds.get("variants", {})
    if variant not in variants:
        lines.append(f"FAIL  в файле порогов нет варианта {variant!r}")
        return lines, True, variant
    label = str(variants[variant].get("label", ""))
    lines.append(f"OK    пороги: {THRESHOLDS} — вариант {variant} ({label})")
    if thresholds.get("schema_version") != artifact.get("schema_version"):
        lines.append(
            f"FAIL  версия схемы: артефакт {artifact.get('schema_version')!r}, "
            f"файл порогов {thresholds.get('schema_version')!r}"
        )
        return lines, True, variant
    threshold_set = variants[variant].get("thresholds", {})
    ids = [str(scenario.get("id")) for scenario in artifact.get("scenarios", [])]
    if sorted(ids) != sorted(CALLS_PER_CARD):
        lines.append(f"FAIL  состав сценариев {ids} — ожидается {sorted(CALLS_PER_CARD)}")
        return lines, True, variant

    over_budget = False
    broken = False
    for scenario in artifact["scenarios"]:
        sid = str(scenario["id"])
        entry = threshold_set.get(sid)
        if not isinstance(entry, dict):
            lines.append(f"FAIL  в порогах варианта {variant} нет сценария {sid!r}")
            broken = True
            continue
        calls = scenario.get("calls_per_card")
        expected = CALLS_PER_CARD[sid]
        if calls != expected:
            lines.append(
                f"FAIL  {sid}: calls_per_card={calls!r}, а пороги варианта {variant} "
                f"рассчитаны на {expected} вызовов "
                "(методика: scripts/spike/llm_cost.schema.json, поле calls_per_card)"
            )
            broken = True
            continue
        for metric, limit in entry.items():
            case = CASES.get((sid, metric))
            if case is None:
                lines.append(
                    f"FAIL  {sid}: неизвестная метрика порога {metric!r} — сверка невозможна"
                )
                broken = True
                continue
            unit, mode = case
            if limit is None:
                lines.append(
                    f"SKIP  {sid} · {unit}: порог не пересчитан (null) — вариант {variant}"
                )
                continue
            factor = calls if mode == "calls" else 1
            for stat in ("median", "p90"):
                value = float(scenario["cost_rub"][stat]) * factor
                if value > limit:
                    over_budget = True
                    lines.append(
                        f"FAIL  {sid} · {unit} ({stat}): {_fmt(value)} > {_fmt(limit)}"
                        f" — вариант {variant}"
                    )
                else:
                    lines.append(
                        f"OK    {sid} · {unit} ({stat}): {_fmt(value)} ≤ {_fmt(limit)}"
                        f" — вариант {variant}"
                    )

    r05 = threshold_set.get("r05")
    if isinstance(r05, dict):
        for metric, limit in r05.items():
            if limit is None:
                lines.append(
                    f"SKIP  r05 · {metric}: порог не пересчитан (null) — вариант {variant}"
                )
            else:
                lines.append(
                    f"SKIP  r05 · {metric} ({_fmt(float(limit))} ₽/мес): офлайн не сверяется — "
                    "экстраполяция на 5 000 MAU требует долей и активности из расчёта G1 §4.3"
                )

    claimed = verdict.get("within_budget")
    if isinstance(claimed, bool) and not broken and claimed == over_budget:
        lines.append(
            f"FAIL  verdict.within_budget={str(claimed).lower()}, а сверка по порогам "
            f"варианта {variant} даёт {'превышение' if over_budget else 'бюджет не превышен'}"
        )
        broken = True
    return lines, over_budget or broken, variant


def check(root: pathlib.Path) -> Check:
    """Проверить артефакт по схеме и порогам. Ни сети, ни ключей, ни записи."""
    root = pathlib.Path(root)
    lines: list[str] = []

    schema = _load_json(root / SCHEMA)
    if schema is None:
        lines.append(f"FAIL  нет схемы {SCHEMA}")
        return Check(lines, True, "нет схемы")
    thresholds = _load_json(root / THRESHOLDS)
    if thresholds is None:
        lines.append(f"FAIL  нет файла порогов {THRESHOLDS}")
        return Check(lines, True, "нет файла порогов")

    artifact_path = root / ARTIFACT
    if not artifact_path.is_file():
        lines.append(
            f"FAIL  нет артефакта {ARTIFACT} — живой замер не выполнен (задача S3b-04)"
        )
        return Check(lines, True, "артефакта нет")
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        lines.append(f"FAIL  артефакт {ARTIFACT} не разбирается как JSON: {exc}")
        return Check(lines, True, "артефакт не разбирается")
    except OSError as exc:
        lines.append(f"FAIL  артефакт {ARTIFACT} не читается: {exc}")
        return Check(lines, True, "артефакт не читается")

    schema_errors = validate(artifact, schema)
    if schema_errors:
        lines.extend(f"FAIL  схема: {error}" for error in schema_errors)
        return Check(lines, True, f"артефакт невалиден по схеме ({len(schema_errors)} ошибок)")

    budget_lines, failed, variant = compare(artifact, thresholds)
    lines.extend(budget_lines)
    if failed:
        return Check(lines, True, f"артефакт вне бюджета варианта {variant}")
    return Check(lines, False, f"артефакт в бюджете, вариант {variant}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Сверка артефакта замера стоимости LLM с порогами R-05 (гейт G17-S3b)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="проверить артефакт замера по схеме и порогам (офлайн, без ключей и сети)",
    )
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=ROOT,
        help="корень репозитория (по умолчанию — корень этого скрипта)",
    )
    args = parser.parse_args(argv)
    if not args.check:
        parser.print_help()
        print("llm_cost: нужен режим --check (живой замер --measure — задача S3b-04)")
        return 2
    result = check(args.root)
    for line in result.lines:
        print(line)
    print(f"llm_cost --check: {'FAIL' if result.failed else 'OK'} ({result.summary})")
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
