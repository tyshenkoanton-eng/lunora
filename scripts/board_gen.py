#!/usr/bin/env python3
"""
board_gen — генерирует ROADMAP_BOARD.md (витрину) из docs/current/ROADMAP_STATUS.yaml.

Принцип Lunera: источник статуса один (ROADMAP_STATUS.yaml); витрина — производная,
не ведётся руками. Меньше руками-синхронизируемых артефактов — меньше дрейфа.

Запуск:
    python scripts/board_gen.py           # перегенерировать витрину
    python scripts/board_gen.py --check   # проверить, что витрина не разъехалась

--check ничего не пишет: он собирает витрину в памяти и сравнивает с файлом.
Если они разошлись — ненулевой код возврата (fail-closed) и подсказка, что делать.
Так дрейф ловится автоматически (в CI, в pre-commit), а не глазами.

Зависимостей нет: минимальный парсер подмножества YAML (pyyaml не требуется).
Сам модуль копируется в проект как есть — он обязан быть самодостаточным.

Путь к подробной карте берётся из ключа `roadmap_doc` в YAML. Если ключа нет,
ищется файл карты по списку типовых путей; если и его нет — в витрину пишется
«не указана», а не битая ссылка.
"""
import argparse
import pathlib
import re
import sys

STATUS = pathlib.Path("docs/current/ROADMAP_STATUS.yaml")
OUT = pathlib.Path("ROADMAP_BOARD.md")

#: Типовые пути подробной карты — ищем первый существующий.
ROADMAP_CANDIDATES = (
    "docs/05_roadmap.md",
    "docs/roadmap.md",
    "docs/current/05_roadmap.md",
    "docs/grillmax/16_roadmap.md",
    "docs/16_roadmap.md",
)

_NULL_VALUES = {"", "null", "~"}
_KEY_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.\-]+)\s*:\s*(?P<value>.*)$")
_BLOCK_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.\-]+)\s*:\s*(?P<style>[>|])[-+]?\d*\s*$")


def _strip_comment(line: str) -> str:
    """Убрать комментарий `#`, не трогая `#` внутри кавычек."""
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
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    if text.lower() in _NULL_VALUES:
        return None
    return text


def _flatten(text: str) -> list:
    """Разобрать текст в список пар (отступ, содержимое), склеив блоки `>`/`|`."""
    lines = text.splitlines()
    result = []
    index = 0
    while index < len(lines):
        line = _strip_comment(lines[index])
        if not line.strip():
            index += 1
            continue
        indent = len(line) - len(line.lstrip())
        content = line.strip()
        block = _BLOCK_RE.match(content)
        if block:
            body = []
            cursor = index + 1
            while cursor < len(lines):
                nxt = _strip_comment(lines[cursor])
                if not nxt.strip():
                    cursor += 1
                    continue
                if len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                body.append(nxt.strip())
                cursor += 1
            value = " ".join(body) if block.group("style") == ">" else "\n".join(body).strip()
            result.append((indent, f"{block.group('key')}: {value}"))
            index = cursor
            continue
        result.append((indent, content))
        index += 1
    return result


def parse_status(text: str) -> dict:
    """Разобрать подмножество YAML: плоские ключи + вложенный блок `current`."""
    root = {}
    stack = [(-1, root)]
    for indent, content in _flatten(text):
        if content.startswith("- "):
            continue  # списки статусом не описываются
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


def _roadmap_doc(data: dict) -> str:
    """Путь к подробной карте: из YAML, иначе — первый существующий кандидат."""
    declared = _value(data, "roadmap_doc").strip()
    if declared:
        return declared
    for candidate in ROADMAP_CANDIDATES:
        if pathlib.Path(candidate).exists():
            return candidate
    return ""


def build_board(data: dict) -> str:
    """Собрать текст витрины из разобранного статуса."""
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
    roadmap = _roadmap_doc(data)
    map_line = (
        f"Подробная карта — `{roadmap}`."
        if roadmap
        else "Подробная карта — путь не указан (ключ `roadmap_doc` в ROADMAP_STATUS.yaml)."
    )
    lvl = level or "—"
    gt = gate or "—"
    sl = slice_ or "—"
    st = status or "—"
    return f"""# {project} — дорожная карта (витрина)

<!-- СГЕНЕРИРОВАНО scripts/board_gen.py из docs/current/ROADMAP_STATUS.yaml.
     Руками не править: правь источник и прогони `make board`. -->

**Уровень:** {lvl} · **Гейт:** {gt} · **Слайс:** {sl} ({st})

| | |
|---|---|
| Последнее ревью | {review or '—'} ({verdict or '—'}) |
| Блокер | {blocker or '—'} |
| Следующий шаг | {action or '—'} |

{map_line} Источник статуса — `docs/current/ROADMAP_STATUS.yaml`.
"""


def main() -> int:
    parser = argparse.ArgumentParser(prog="board_gen")
    parser.add_argument(
        "--check",
        action="store_true",
        help="не писать: проверить, что витрина соответствует источнику",
    )
    args = parser.parse_args()

    if not STATUS.exists():
        print(f"board_gen: нет {STATUS} — нечего генерировать")
        return 1
    data = parse_status(STATUS.read_text(encoding="utf-8"))
    board = build_board(data)

    if args.check:
        if not OUT.exists():
            print(f"board_gen: витрина {OUT} не найдена — прогони `make board`")
            return 1
        current = OUT.read_text(encoding="utf-8")
        if current == board:
            print(f"board_gen: {OUT} соответствует источнику")
            return 0
        print(f"board_gen: {OUT} разошёлся с {STATUS} — прогони `make board`")
        return 1

    OUT.write_text(board, encoding="utf-8")
    print(f"board_gen: {OUT} обновлён")
    return 0


if __name__ == "__main__":
    sys.exit(main())
