#!/usr/bin/env python3
"""Пересобирает docs/grillmax/screen-codes.md из реестра REG прототипа.

Запуск из корня репозитория:
    python3 docs/grillmax/spec/gen-screen-codes.py

Каталог экранов — зеркало реестра, вручную не правится. После изменений
в REG (добавили/переименовали экран) перегенерируйте этот файл.
"""
import re, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
PROTO = ROOT / "docs/grillmax/wireframes/02-report.html"
OUT = ROOT / "docs/grillmax/screen-codes.md"

src = PROTO.read_text(encoding="utf-8")
m = re.search(r"const REG = (\[.*?\]);", src, re.S)
REG = json.loads(m.group(1))

from collections import OrderedDict
groups = OrderedDict()
for r in REG:
    groups.setdefault(r.get("g", ""), []).append(r)


def note(r):
    parts = []
    if r.get("sheet"): parts.append("шторка")
    if r.get("info"): parts.append("подсказка")
    if r.get("open"): parts.append("инлайн-раскрытие")
    if r.get("s"): parts.append(", ".join(f"{k}={v}" for k, v in r["s"].items()))
    if r.get("tab"): parts.append("вкладка " + r["tab"][2])
    return "; ".join(parts)


out = []
w = out.append
w("# Каталог экранов")
w("")
w("**Обновлено:** сгенерировано из реестра `REG` прототипа (`wireframes/02-report.html`).")
w(f"**Всего экранов:** {len(REG)} в {len(groups)} группах.")
w("")
w("---")
w("")
w("## Как ссылаться на экран")
w("")
w("Адрес показан в шапке макета слева от названия. **Клик по нему копирует полную строку** — с состоянием экрана, если оно не обычное. Достаточно прислать эту строку и что не так; можно и короче («поправь Л-17», «на экране глубины»).")
w("")
w("⚠️ **Номера локальны внутри раздела** и не сдвигаются при добавлении экранов в другие разделы.")
w("")
w("Этот каталог — зеркало реестра прототипа и источник правды по кодам, названиям и ключам. При расхождении с другими документами прав прототип. Пересобирается скриптом `spec/gen-screen-codes.py` из `REG`, вручную не правится.")
w("")
w("Суффиксы кода: `-1/-2/...` — варианты состояния одного экрана; буква после номера (`Р-01а`) — вкладка. `Ф-*` — шторки, `Б-*` — сообщения бота.")
w("")
w("---")
w("")
for g, rows in groups.items():
    w(f"## {g}")
    w("")
    w("| Код | Экран | Ключ | Состояние / тип |")
    w("|---|---|---|---|")
    for r in rows:
        w(f"| `{r['n']}` | {r['t']} | `{r['k']}` | {note(r)} |")
    w("")

OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"{OUT.relative_to(ROOT)}: {len(REG)} экранов, {len(groups)} групп")
