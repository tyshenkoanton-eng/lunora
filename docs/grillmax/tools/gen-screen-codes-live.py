#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Пересобирает screen-codes.md из ЖИВОГО реестра REG прототипа.

Отличие от spec/gen-screen-codes.py: тот читает литерал `const REG` и теряет
22 детальных экрана Нумерологии/Ба-Цзы, которые прототип добавляет в REG при
загрузке (IIFE catalogDetailScreens → REG.splice). Этот генератор открывает
02-report.html в headless-Chromium и снимает REG после исполнения скриптов —
то есть ровно то, что видит пользователь (ревью v9, F-03).

Запуск:   python3 tools/gen-screen-codes-live.py           # пересобрать
          python3 tools/gen-screen-codes-live.py --check   # CI: упасть, если каталог отстал
Требует: playwright + chromium (в облачной среде предустановлены).
Фолбэк: если браузер недоступен — печатает инструкцию и выходит с кодом 3,
        не трогая каталог (чтобы не записать усечённую статическую версию).
"""
import sys, pathlib, json, subprocess
from collections import OrderedDict

GRILLMAX = pathlib.Path(__file__).resolve().parents[1]
PROTO = GRILLMAX / "wireframes/02-report.html"
OUT = GRILLMAX / "screen-codes.md"
CHECK = '--check' in sys.argv

# Снятие живого реестра идёт через Node-playwright (в облачной среде
# предустановлен; python-playwright может отсутствовать). REG выводится как JSON.
_NODE = (
    "const {chromium}=require('playwright');"
    "(async()=>{const b=await chromium.launch({args:['--no-sandbox']});"
    "const p=await b.newPage();await p.goto('file://'+process.argv[1]);"
    "const r=await p.evaluate(()=>JSON.stringify(REG));await b.close();"
    "process.stdout.write(r);})().catch(e=>{console.error(e);process.exit(4);});"
)


def read_live_reg():
    try:
        out = subprocess.run(["node", "-e", _NODE, str(PROTO)],
                             capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        print("⛔ node недоступен; каталог не тронут. Нужен node + playwright (chromium).", file=sys.stderr)
        sys.exit(3)
    if out.returncode != 0 or not out.stdout.strip():
        print(f"⛔ не удалось снять живой REG (код {out.returncode}); каталог не тронут.\n{out.stderr[:400]}", file=sys.stderr)
        sys.exit(3)
    return json.loads(out.stdout)


def build_md(REG):
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
    w("**Обновлено:** сгенерировано из **живого** реестра `REG` прототипа (`wireframes/02-report.html`, headless-браузер — включает рантайм-экраны `catalogDetailScreens`).")
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
    w("Этот каталог — зеркало **живого** реестра прототипа и источник правды по кодам, названиям и ключам. При расхождении с другими документами прав прототип. Пересобирается скриптом `tools/gen-screen-codes-live.py` из `REG`, вручную не правится.")
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
    return "\n".join(out) + "\n", len(REG), len(groups)


REG = read_live_reg()
md, n_screens, n_groups = build_md(REG)

if CHECK:
    current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    if current != md:
        print(f"⛔ screen-codes.md отстал от живого реестра ({n_screens} экранов). Пересоберите: python3 tools/gen-screen-codes-live.py", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Каталог актуален: {n_screens} экранов, {n_groups} групп.")
    sys.exit(0)

OUT.write_text(md, encoding="utf-8")
print(f"{OUT.relative_to(GRILLMAX)}: {n_screens} экранов, {n_groups} групп (живой реестр)")
