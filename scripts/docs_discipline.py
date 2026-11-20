#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docs_discipline — принуждение дисциплины документов Lunera.

Кодирует правила LUNERA_STANDARDS §2 / §2.1 в автопроверку. Падает в CI при
нарушении — агент физически не может влить дрейф.

Запуск:   python3 scripts/docs_discipline.py [--docs docs] [--strict]
Выход:    0 — чисто (нет ошибок), 1 — есть ошибки.

ERRORS (валят CI всегда):
  - версия в имени файла (_v2, _v4, _amendment, _new, _old, _copy, ...)
  - битая относительная ссылка на .md
  - CURRENT_STATE.md толще порога (перестал быть тонким)
  - больше одного файла, похожего на роадмеп

WARNINGS (report; при --strict тоже валят CI):
  - у крупной папки нет карты-индекса
  - документ-сирота (не достижим из индекса)
  - монстр-файл сверх порога (кроме помеченных `<!-- reference -->`)

Переиспользуемо: копируется в scripts/ любого проекта. Настройки — ниже.
"""

import argparse
import pathlib
import re
import sys

# ── Настройки (проект может подправить) ──────────────────────────────────────
STATUS_FILES = ("CURRENT_STATE.md", "CURRENT_STATUS.md")   # тонкий статус-вход
THIN_MAX = 160                     # строк: выше — статус перестал быть тонким
FOLDER_INDEX_MIN = 5               # файлов в папке, при которых нужен индекс
MONSTER_LINES = 1500               # строк: выше — предупреждение о монстре
ROADMAP_RE = re.compile(r"roadmap", re.I)   # что считаем «похоже на роадмеп»
# Версия в имени = дрейф. Дата (ГГГГММДД) — НЕ версия: так именуют исторические
# records (аудиты, close-record'ы), это разрешено.
VERSIONED_RE = re.compile(
    r"_(v\d+([_.]\d+)*|rev\d+|amendment|copy|old|new)(\b|_|\.)", re.I
)
INDEX_RE = re.compile(r"(^|_|-)(index|readme)(\.|$)", re.I)
EXCLUDE_DIRS = {"archive", "evidence", "reviews", ".git"}
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# ─────────────────────────────────────────────────────────────────────────────


def is_index(p: pathlib.Path) -> bool:
    return bool(INDEX_RE.search(p.stem)) or p.name.startswith("00_")


def rel(p: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def collect(docs: pathlib.Path):
    out = []
    for p in sorted(docs.rglob("*.md")):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def links_from(p: pathlib.Path):
    """Относительные .md-цели из markdown-ССЫЛОК (для проверки битых ссылок)."""
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    targets = []
    for m in MD_LINK_RE.finditer(text):
        t = m.group(1).split("#")[0].split(" ")[0].strip()
        if not t or t.startswith(("http://", "https://", "mailto:")):
            continue
        if not t.endswith(".md"):
            continue
        targets.append((p.parent / t).resolve())
    return targets


MENTION_RE = re.compile(r"[`(\[]([^`)\]\s]+\.md)[`)\]]")


def references_from(p: pathlib.Path, docs: pathlib.Path):
    """Все упоминания .md для достижимости: ссылки + пути в бэктиках/таблицах.
    Документ, упомянутый по пути в индексе, — находим, даже без markdown-ссылки."""
    refs = list(links_from(p))
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return refs
    for m in MENTION_RE.finditer(text):
        t = m.group(1).strip()
        if t.startswith(("http", "mailto")):
            continue
        # путь может быть от корня репо (docs/...) или относительный к файлу
        for base in (p.parent, docs.parent, docs):
            cand = (base / t).resolve()
            if cand.exists():
                refs.append(cand)
                break
    return refs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default="docs")
    ap.add_argument("--strict", action="store_true",
                    help="warnings тоже валят CI")
    args = ap.parse_args()

    repo = pathlib.Path(".").resolve()
    docs = (repo / args.docs).resolve()
    if not docs.exists():
        print(f"docs_discipline: папка {args.docs} не найдена")
        return 1

    files = collect(docs)
    errors, warnings = [], []

    # 1. версии в именах
    for p in files:
        if VERSIONED_RE.search(p.stem):
            errors.append(f"версия в имени: {rel(p, repo)} "
                          f"(живое правится на месте, версии — в git)")

    # 2. битые относительные ссылки
    all_resolved = {p.resolve() for p in files}
    for p in files:
        for t in links_from(p):
            if t.suffix == ".md" and t not in all_resolved and not t.exists():
                errors.append(f"битая ссылка: {rel(p, repo)} → "
                              f"{rel(t, repo)}")

    # 3. тонкий CURRENT_STATE
    for name in STATUS_FILES:
        f = docs / name
        if f.exists():
            n = sum(1 for _ in f.open(encoding="utf-8", errors="ignore"))
            if n > THIN_MAX:
                errors.append(f"{name} растолстел: {n} строк > {THIN_MAX} "
                              f"(статус-вход должен быть тонким)")

    # 4. один роадмеп
    roadmaps = [p for p in files if ROADMAP_RE.search(p.stem)
                and not is_index(p)]
    if len(roadmaps) > 1:
        errors.append("больше одного роадмеп-файла: "
                      + ", ".join(rel(p, repo) for p in roadmaps)
                      + " (роадмеп — один живой документ)")

    # 5. крупная папка без индекса
    by_dir: dict[pathlib.Path, list[pathlib.Path]] = {}
    for p in files:
        by_dir.setdefault(p.parent, []).append(p)
    for d, ps in by_dir.items():
        if len(ps) >= FOLDER_INDEX_MIN and not any(is_index(p) for p in ps):
            warnings.append(f"крупная папка без карты-индекса: "
                            f"{rel(d, repo)}/ ({len(ps)} файлов)")

    # 6. сироты (не достижимы из индексов/входов)
    roots = [p for p in files if is_index(p) or p.name in STATUS_FILES]
    for extra in ("CLAUDE.md", "AGENTS.md"):
        if (repo / extra).exists():
            roots.append(repo / extra)
    reached = set()
    queue = list(roots)
    while queue:
        cur = queue.pop()
        r = cur.resolve()
        if r in reached:
            continue
        reached.add(r)
        for t in references_from(cur, docs):
            if t not in reached:
                queue.append(t)
    for p in files:
        if p.resolve() not in reached and not is_index(p):
            warnings.append(f"сирота (не достижим из индекса): {rel(p, repo)}")

    # 7. монстры
    for p in files:
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "<!-- reference -->" in head[:400]:
            continue
        n = head.count("\n") + 1
        if n > MONSTER_LINES:
            warnings.append(f"монстр-файл: {rel(p, repo)} ({n} строк) — "
                            f"разбей или пометь `<!-- reference -->`")

    # ── отчёт ────────────────────────────────────────────────────────────────
    if args.strict:
        errors += warnings
        warnings = []
    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  FAIL  {e}")
    total = f"{len(files)} докумен(та/тов)"
    if errors:
        print(f"docs_discipline: {len(errors)} ошибок, "
              f"{len(warnings)} предупреждений ({total})")
        return 1
    print(f"docs_discipline: OK ({total}"
          + (f", {len(warnings)} предупреждений" if warnings else "") + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
