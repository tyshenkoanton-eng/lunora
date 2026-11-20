#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
board_gen — генерирует ROADMAP_BOARD.md (витрину) из docs/current/ROADMAP_STATUS.yaml.

Принцип Lunera: источник статуса один (ROADMAP_STATUS.yaml); витрина — производная,
не ведётся руками. Меньше руками-синхронизируемых артефактов — меньше дрейфа.

Запуск:  python3 scripts/board_gen.py
Зависимостей нет (минимальный парсер плоских ключей; pyyaml не требуется).
"""
import pathlib
import re
import sys

STATUS = pathlib.Path("docs/current/ROADMAP_STATUS.yaml")
OUT = pathlib.Path("ROADMAP_BOARD.md")


def val(text: str, key: str) -> str:
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*(?:#.*)?$", text, re.M)
    if not m:
        return ""
    v = m.group(1).strip().strip("\"'")
    return "" if v in ("", "null", "~") else v


def main() -> int:
    if not STATUS.exists():
        print(f"board_gen: нет {STATUS} — нечего генерировать")
        return 1
    t = STATUS.read_text(encoding="utf-8")
    project = val(t, "project")
    level, gate, slice_ = val(t, "level"), val(t, "gate"), val(t, "slice")
    st = val(t, "slice_status")
    blocker, nxt = val(t, "blocker"), val(t, "next_action")
    verdict = val(t, "latest_verdict")
    review = val(t, "latest_review")
    board = f"""# {project} — дорожная карта (витрина)

<!-- СГЕНЕРИРОВАНО scripts/board_gen.py из docs/current/ROADMAP_STATUS.yaml.
     Руками не править: правь источник и прогони `make board`. -->

**Уровень:** {level or '—'} · **Гейт:** {gate or '—'} · **Слайс:** {slice_ or '—'} ({st or '—'})

| | |
|---|---|
| Последнее ревью | {review or '—'} ({verdict or '—'}) |
| Блокер | {blocker or '—'} |
| Следующий шаг | {nxt or '—'} |

Подробная карта — `docs/05_roadmap.md`. Источник статуса — `docs/current/ROADMAP_STATUS.yaml`.
"""
    OUT.write_text(board, encoding="utf-8")
    print(f"board_gen: {OUT} обновлён")
    return 0


if __name__ == "__main__":
    sys.exit(main())
