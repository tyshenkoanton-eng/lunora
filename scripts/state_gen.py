#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
state_gen — генерирует управляемый блок в docs/CURRENT_STATE.md из
docs/current/ROADMAP_STATUS.yaml.

Зачем: «где мы» должно жить в одном месте. Сейчас факт статуса хранится
в четырёх файлах (ROADMAP_STATUS.yaml, CURRENT_STATE.md, _SESSION.json,
16_roadmap.md), и это источник дрейфа. Решение: **записываемый дом один** —
`docs/current/ROADMAP_STATUS.yaml`; всё остальное — витрины.

`ROADMAP_BOARD.md` уже витрина (её собирает `board_gen.py`). Этот скрипт
собирает вторую: вход для человека. Механика та же — скрипт управляет
**только своим блоком** между маркерами, а проза вокруг (решения, что
разрешено/заблокировано, указатели) остаётся человеческой и не затирается.

Почему не генерировать файл целиком: в живой прозе есть то, чего нет в
статусе (NO-GO, решения, ссылки на ADR). Полная генерация либо потеряет
это, либо превратит витрину в ещё один файл для ручной синхронизации —
то есть в тот же дубль, ради устранения которого всё затевалось.

Запуск:
    python scripts/state_gen.py            # обновить управляемый блок
    python scripts/state_gen.py --check    # проверить: блок разошёлся с источником
    python scripts/state_gen.py --adopt    # вставить маркеры в существующий файл

`--check` ничего не пишет: он собирает блок в памяти и сравнивает с файлом.
Расхождение — ненулевой код возврата (fail-closed), дрейф ловится в CI,
а не глазами.

Зависимостей нет: минимальный парсер подмножества YAML (pyyaml не требуется).
Сам модуль копируется в проект как есть — он обязан быть самодостаточным.
"""
import argparse
import pathlib
import re
import sys

STATUS = pathlib.Path("docs/current/ROADMAP_STATUS.yaml")
OUT = pathlib.Path("docs/CURRENT_STATE.md")

BEGIN_MARK = "<!-- state_gen:begin -->"
END_MARK = "<!-- state_gen:end -->"

_NULL_VALUES = {"", "null", "~"}
_KEY_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.\-]+)\s*:\s*(?P<value>.*)$")
_BLOCK_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.\-]+)\s*:\s*(?P<style>[>|])[-+]?\d*\s*$")


def _strip_comment(line: str) -> str:
    """Убрать комментарий `#` (не трогая `#` внутри кавычек)."""
    out = []
    quote = None
    for index, char in enumerate(line):
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            continue
        if char == "#" and (index == 0 or line[index - 1] in " \t"):
            break
        out.append(char)
    return "".join(out).rstrip()


def _scalar(value: str):
    """Скаляр: снять кавычки; `null`/`~`/пусто → None."""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    if text.lower() in _NULL_VALUES:
        return None
    return text


def _flatten(text: str) -> list:
    """Разобрать текст в список пар (отступ, содержимое), склеив блоки `>`/`|`."""
    raw_lines = text.splitlines()
    result = []
    index = 0
    while index < len(raw_lines):
        line = _strip_comment(raw_lines[index])
        if not line.strip():
            index += 1
            continue
        indent = len(line) - len(line.lstrip())
        content = line.strip()
        block = _BLOCK_RE.match(content)
        if block:
            body = []
            cursor = index + 1
            while cursor < len(raw_lines):
                nxt = _strip_comment(raw_lines[cursor])
                if not nxt.strip():
                    cursor += 1
                    continue
                next_indent = len(nxt) - len(nxt.lstrip())
                if next_indent <= indent:
                    break
                body.append(nxt.strip())
                cursor += 1
            value = " ".join(part for part in body if part) if block.group("style") == ">" \
                else "\n".join(body).strip()
            result.append((indent, f"{block.group('key')}: {value}"))
            index = cursor
            continue
        result.append((indent, content))
        index += 1
    return result


def parse_status(text: str) -> dict:
    """Минимальный разбор подмножества YAML (как в board_gen.py)."""
    items = _flatten(text)
    root = {}
    stack = [(-1, root)]
    for indent, content in items:
        if content.startswith("- "):
            continue
        match = _KEY_RE.match(content)
        if match is None:
            continue
        key = match.group("key")
        value = match.group("value")
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]
        if value.strip() == "":
            child = {}
            container[key] = child
            stack.append((indent, child))
        else:
            container[key] = _scalar(value)
    for key, value in list(root.items()):
        if isinstance(value, dict) and not value:
            root[key] = None
    return root


def _value(mapping: dict, key: str) -> str:
    value = mapping.get(key)
    return "" if value is None else str(value)


def build_block(data: dict) -> str:
    """Собрать управляемый блок из разобранного статуса."""
    current = data.get("current")
    current = current if isinstance(current, dict) else {}
    project = _value(data, "project") or "—"
    level = _value(current, "level")
    gate = _value(current, "gate")
    slice_ = _value(current, "slice")
    status = _value(current, "slice_status")
    review = _value(current, "latest_review")
    verdict = _value(current, "latest_verdict")
    blocker = _value(current, "blocker")
    action = _value(current, "next_action")
    position = " · ".join(x for x in (level, gate, slice_) if x) or "—"
    return f"""{BEGIN_MARK}
<!-- СГЕНЕРИРОВАНО scripts/state_gen.py из docs/current/ROADMAP_STATUS.yaml.
     Этот блок руками не править: правь источник и прогони `make state`. -->

**Проект:** {project} · **Позиция:** {position} — {status or '—'}

| | |
|---|---|
| Последнее ревью | {review or '—'} ({verdict or '—'}) |
| Блокер | {blocker or '—'} |
| Следующий шаг | {action or '—'} |

Источник статуса — `docs/current/ROADMAP_STATUS.yaml`. Витрина карты — `ROADMAP_BOARD.md`.
{END_MARK}"""


SKELETON = """# {project} — текущее состояние

{BEGIN_MARK}
{END_MARK}

## Что разрешено / заблокировано

- Разрешено: <...>
- NO-GO: <...>

## Указатели

- Карта-индекс документов: `docs/00_index.md`
- Закрытые этапы: `docs/gates/`
- Летопись: `docs/changelog.md`
- Журнал слайса: `docs/current/WORKLOG.md`
"""


def _rendered(text: str, block: str) -> str:
    """Вставить или заменить управляемый блок, сохранив остальное содержимое."""
    begin = text.find(BEGIN_MARK)
    end = text.find(END_MARK)
    if begin >= 0 and end > begin:
        return text[:begin] + block + text[end + len(END_MARK):]
    # Файла нет — создаём скелет: блок плюс человеческие разделы.
    return SKELETON.format(project="<ПРОЕКТ>", BEGIN_MARK=BEGIN_MARK, END_MARK=END_MARK)


def _replace_block(text: str, block: str) -> str:
    """Заменить блок по маркерам; если маркеров нет — вставить после первого заголовка."""
    begin = text.find(BEGIN_MARK)
    end = text.find(END_MARK)
    if begin >= 0 and end > begin:
        return text[:begin] + block + text[end + len(END_MARK):]
    lines = text.splitlines()
    insert_at = 1 if lines and lines[0].startswith("#") else 0
    head = "\n".join(lines[:insert_at])
    tail = "\n".join(lines[insert_at:])
    parts = [head, "", block, ""]
    if tail.strip():
        parts.append(tail)
    return "\n".join(parts).rstrip() + "\n"


def _has_markers(text: str) -> bool:
    return BEGIN_MARK in text and END_MARK in text


def main() -> int:
    parser = argparse.ArgumentParser(prog="state_gen")
    parser.add_argument(
        "--check",
        action="store_true",
        help="не писать: проверить, что блок соответствует источнику",
    )
    parser.add_argument(
        "--adopt",
        action="store_true",
        help="вставить маркеры в существующий файл, не трогая содержимое",
    )
    args = parser.parse_args()

    if not STATUS.exists():
        print(f"state_gen: нет {STATUS} — нечего генерировать")
        return 1
    data = parse_status(STATUS.read_text(encoding="utf-8"))
    block = build_block(data)

    if not OUT.exists():
        if args.check:
            print(f"state_gen: {OUT} не найден — прогони `make state`")
            return 1
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(_rendered("", block), encoding="utf-8")
        print(f"state_gen: {OUT} создан")
        return 0

    current = OUT.read_text(encoding="utf-8")

    if args.check:
        if not _has_markers(current):
            print(f"state_gen: {OUT} не управляется state_gen — проверить нечего")
            return 0
        expected = _replace_block(current, block)
        if current == expected:
            print(f"state_gen: {OUT} соответствует источнику")
            return 0
        print(f"state_gen: {OUT} разошёлся с {STATUS} — прогони `make state`")
        return 1

    if args.adopt:
        if _has_markers(current):
            print(f"state_gen: {OUT} уже управляется state_gen")
            return 0
        OUT.write_text(_replace_block(current, block), encoding="utf-8")
        print(f"state_gen: маркеры вставлены в {OUT} (содержимое сохранено)")
        return 0

    if not _has_markers(current):
        print(f"state_gen: {OUT} не управляется state_gen — сначала `make state-adopt`")
        return 1
    OUT.write_text(_replace_block(current, block), encoding="utf-8")
    print(f"state_gen: {OUT} обновлён")
    return 0


if __name__ == "__main__":
    sys.exit(main())
