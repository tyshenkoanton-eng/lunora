#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Гейт распространения решений (ревью v11). Ловит класс «решение принято, а
документы о нём не знают» — тот самый «хвост после правки».

Параметризован активным платёжным решением D-121 (Stars внутри Telegram +
ЮKassa вне) и отменённым D-116. Проверяет:
  1. decision-not-propagated — D-121 упомянут во всех канонических файлах,
     где обязан (точка входа, описание, транзакции, дорожная карта, реестр
     решений, прототип).
  2. cancelled-referenced — D-116 не упоминается как ДЕЙСТВУЮЩЕЕ (упоминание
     рядом со словами «отменён/заменён/устар» допустимо — это история).
  3. stale-payment-model — старые формулировки «оплата … не Telegram Stars»,
     «Stars стоили бы трети выручки» и т. п.
  4. proto-payment-method — видимые пользователю строки способа оплаты
     «· СБП»/«· карта» в истории платежей прототипа.
  5. registry-stale — D-121 присутствует в _SESSION.json.

Запуск: python3 tools/check-decision-propagation.py [корень]
Код выхода: 0 — расхождений нет; 1 — есть; 2 — корень не похож на пакет.
Только чтение.
"""
import os, re, sys

ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANCHORS = ('РЕШЕНИЯ-БЛОКЕРЫ.md', 'ПРАЙС.md', os.path.join('wireframes', '02-report.html'))
if not os.path.isdir(ROOT) or any(not os.path.exists(os.path.join(ROOT, a)) for a in ANCHORS):
    print(f'⛔ {ROOT} не похож на пакет «Лунора».'); sys.exit(2)

ACTIVE = 'D-121'
CANCELLED = 'D-116'
# Файлы, которые ОБЯЗАНЫ знать про активное платёжное решение.
MUST_PROPAGATE = [
    'ПЕРЕДАЧА-КОМАНДЕ.md', 'ОПИСАНИЕ-ПРОЕКТА.md', 'TRANSACTIONS-КОНТРАКТЫ.md',
    'ДОРОЖНАЯ-КАРТА.md', '_SESSION.json', os.path.join('wireframes', '02-report.html'),
]

problems = []
def add(cat, path, detail):
    problems.append((cat, path, detail))

def read(rel):
    p = os.path.join(ROOT, rel)
    return open(p, encoding='utf-8', errors='replace').read() if os.path.exists(p) else None

# 1. decision-not-propagated
for rel in MUST_PROPAGATE:
    txt = read(rel)
    if txt is None:
        continue
    if ACTIVE not in txt:
        add('decision-not-propagated', rel, f'{ACTIVE} не упомянут')

# 2. cancelled-referenced — D-116 как действующее (не рядом с отменой)
CANCEL_OK = re.compile(r'(отмен|ОТМЕН|заменён|заменен|заменя|устар|снят|supersed|→\s*D-121)')
JSON_ID = re.compile(r'"(id|superseded_by)"\s*:\s*"D-116"')
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in ('.git', 'node_modules')]
    for fn in fns:
        if os.path.splitext(fn)[1].lower() not in ('.md', '.json'):
            continue
        p = os.path.join(dp, fn)
        for ln, line in enumerate(open(p, encoding='utf-8', errors='replace'), 1):
            if CANCELLED in line and not CANCEL_OK.search(line) and not JSON_ID.search(line):
                add('cancelled-referenced', os.path.relpath(p, ROOT), f'{ln}: {CANCELLED} без пометки отмены')

# 3. stale-payment-model
STALE = re.compile(r'\bне\s+Telegram\s+Stars|Stars\s+стоили\s+бы|оплата\s+(через\s+)?(СБП|ЮKassa)[^\n]{0,40}\bне\s+Stars')
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in ('.git', 'node_modules')]
    for fn in fns:
        if os.path.splitext(fn)[1].lower() != '.md':
            continue
        p = os.path.join(dp, fn)
        # архивные L0-гейты не считаем (история)
        if re.match(r'0[0-7]_', fn):
            continue
        for ln, line in enumerate(open(p, encoding='utf-8', errors='replace'), 1):
            if STALE.search(line):
                add('stale-payment-model', os.path.relpath(p, ROOT), f'{ln}: старая модель оплаты vs D-121')

# 4. proto-payment-method — видимый способ оплаты в истории платежей
proto = read(os.path.join('wireframes', '02-report.html'))
if proto:
    for ln, line in enumerate(proto.splitlines(), 1):
        # строки истории платежей: "ЧЧ:ММ · СБП" / "ЧЧ:ММ · карта" (способ оплаты),
        # не путать с «· карта готова/посчитана» (астрологическая карта).
        if re.search(r'\d\d:\d\d\s*·\s*(СБП|карта)(?!\s*(готова|посчитана|личности))', line) and 'Оплата живёт вне' not in line:
            add('proto-payment-method', 'wireframes/02-report.html', f'{ln}: способ оплаты «СБП/карта» (при D-121 внутри TG — Stars)')

# 5. registry-stale
sess = read('_SESSION.json')
if sess is not None and ACTIVE not in sess:
    add('registry-stale', '_SESSION.json', f'{ACTIVE} отсутствует в реестре решений')

# report
cats = {}
for c, p, d in problems:
    cats.setdefault(c, []).append((p, d))
print(f'Проверено в: {ROOT}  (активное решение {ACTIVE}, отменённое {CANCELLED})')
if not problems:
    print('✅ Расхождений нет.'); sys.exit(0)
for c in sorted(cats):
    print(f'\n[{c}] — {len(cats[c])}')
    for p, d in cats[c][:40]:
        print(f'  {p} :: {d}')
print(f'\nИтого расхождений: {len(problems)}')
sys.exit(1)
