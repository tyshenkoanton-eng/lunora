#!/usr/bin/env python3
"""golden_audit — проверка формата golden-кейсов (G17, ARCHITECTURE.md §6.2 + versions B12).

Не считает карты: проверяет, что каждый кейс прослеживаем до внешнего эталона.
  - active   → reference {source, settings, captured_at, captured_by, evidence_file}
               (файл-доказательство существует), versions {tz, ephemeris, reference_service},
               непустой expected, у каждого ожидания path + value + (tolerance | exact: true);
  - disputed / known_gap → обязательны notes; не блокируют, но не удаляются.

Запуск:  python scripts/spike/golden_audit.py tests/golden [--require-active]
Выход:   0 — чисто, 1 — есть ошибки.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from dataclasses import dataclass, field

import yaml

LAYERS = {"timeplace", "ephemeris", "western", "vedic", "bazi", "numerology", "consensus"}
STATUSES = {"active", "disputed", "known_gap"}
REFERENCE_FIELDS = ("source", "settings", "captured_at", "captured_by", "evidence_file")
VERSION_FIELDS = ("tz", "ephemeris", "reference_service")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def _check_case(case: object, name: str, root: pathlib.Path, rep: Report) -> str | None:
    if not isinstance(case, dict):
        rep.errors.append(f"{name}: кейс должен быть словарём")
        return None
    cid = case.get("id")
    where = f"{name} [{cid}]"
    if not cid:
        rep.errors.append(f"{name}: нет id")
    if case.get("layer") not in LAYERS:
        rep.errors.append(f"{where}: неизвестный layer {case.get('layer')!r}")
    status = case.get("status")
    if status not in STATUSES:
        rep.errors.append(f"{where}: неизвестный status {status!r}")
        return cid
    rep.counts[status] = rep.counts.get(status, 0) + 1

    if status != "active":
        if not str(case.get("notes") or "").strip():
            rep.errors.append(f"{where}: для {status} обязательны notes (почему не блокирует)")
        return cid

    ref = case.get("reference") or {}
    for f in REFERENCE_FIELDS:
        if not ref.get(f):
            rep.errors.append(f"{where}: reference.{f} обязателен для active")
    ev = ref.get("evidence_file")
    if ev and not (root / ev).is_file():
        rep.errors.append(f"{where}: evidence-файл не найден: {ev}")

    versions = case.get("versions") or {}
    for f in VERSION_FIELDS:
        if not versions.get(f):
            rep.errors.append(f"{where}: versions.{f} обязателен")

    expected = case.get("expected")
    if not expected:
        rep.errors.append(f"{where}: expected пуст")
        return cid
    for i, exp in enumerate(expected):
        if not isinstance(exp, dict) or "path" not in exp or "value" not in exp:
            rep.errors.append(f"{where}: expected[{i}] нужны path и value")
            continue
        if exp.get("exact") is not True and exp.get("tolerance") is None:
            rep.errors.append(f"{where}: expected[{i}] ({exp['path']}) нужен tolerance или exact")
    return cid


def audit(root: pathlib.Path, require_active: bool = False) -> Report:
    rep = Report()
    seen: dict[str, str] = {}
    files = sorted(p for p in root.rglob("*.y*ml") if "evidence" not in p.parts)
    for path in files:
        name = str(path.relative_to(root))
        try:
            docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]
        except yaml.YAMLError as exc:
            rep.errors.append(f"{name}: YAML не читается: {exc.__class__.__name__}")
            continue
        for case in docs:
            cid = _check_case(case, name, root, rep)
            if cid:
                if cid in seen:
                    rep.errors.append(f"{name}: дубликат id {cid!r} (уже в {seen[cid]})")
                seen[cid] = name
    if require_active and not rep.counts.get("active"):
        rep.errors.append("нет ни одного active-кейса — слайсу нечем доказывать корректность")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", type=pathlib.Path)
    ap.add_argument("--require-active", action="store_true")
    args = ap.parse_args()
    rep = audit(args.root, require_active=args.require_active)
    for e in rep.errors:
        print(f"  ERROR  {e}")
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(rep.counts.items())) or "кейсов нет"
    print(f"golden_audit: {'FAIL' if rep.errors else 'OK'} ({summary})")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
