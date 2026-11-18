#!/usr/bin/env python3
"""Пересобирает docs/grillmax/screen-codes.md из ЛИТЕРАЛА `const REG` прототипа.

⚠️ УСТАРЕЛО как источник каталога (ревью v9, F-03): читает только литерал REG
и НЕ видит 22 детальных экрана Нумерологии/Ба-Цзы, которые прототип добавляет
в REG при загрузке (`catalogDetailScreens` → REG.splice). Канонический
генератор — `tools/gen-screen-codes-live.py` (снимает живой реестр из браузера,
310 экранов). Этот скрипт — быстрый фолбэк без браузера; он НЕ перезаписывает
каталог, собранный живым генератором (защита от регрессии ниже).

Запуск (из любого места — пути считаются от самого скрипта):
    python3 spec/gen-screen-codes.py
"""
import re, json, pathlib

# Скрипт лежит в grillmax/spec/ — корень пакета это его дед.
# Работает и в плоском пакете, и в полном репозитории.
GRILLMAX = pathlib.Path(__file__).resolve().parents[1]
PROTO = GRILLMAX / "wireframes/02-report.html"
OUT = GRILLMAX / "screen-codes.md"

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

# Защита от регрессии: не затираем каталог, собранный живым генератором.
if OUT.exists() and "gen-screen-codes-live.py" in OUT.read_text(encoding="utf-8"):
    print(f"⚠️ {OUT.relative_to(GRILLMAX)} собран живым генератором (включает рантайм-экраны). "
          f"Статический скрипт даёт {len(REG)} вместо полного набора и НЕ перезаписывает его. "
          f"Пересобирайте через tools/gen-screen-codes-live.py.")
    raise SystemExit(0)
OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"{OUT.relative_to(GRILLMAX)}: {len(REG)} экранов, {len(groups)} групп (ЛИТЕРАЛ REG; детальные рантайм-экраны не включены — см. gen-screen-codes-live.py)")
