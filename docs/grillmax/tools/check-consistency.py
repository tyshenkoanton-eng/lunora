#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Гейт связности пакета «Лунора» (по рекомендации внешних ревью v5/v6).
Запуск из любого места:  python3 tools/check-consistency.py [корень_grillmax]
По умолчанию корень — родитель папки tools/. Только чтение, ничего не меняет.
Код выхода: 0 — замечаний нет; 1 — есть.

Что проверяет:
  1. Битые относительные markdown-ссылки [..](path) на файлы внутри пакета.
  2. Casefold-коллизии имён файлов (ENGINE-SPEC.md vs engine-spec.md).
  3. Остатки снятых моделей/терминов (холд, двухстадийная оплата как действующая,
     «мастер-число»/«доша»/«число души» в видимом тексте, «4 из 4» как доказательство).
  4. Ссылки на несуществующие каталоги плоской структуры (research/, v3-каталоги).
Это не заменяет внешнее ревью, но ловит класс «хвостов после правки» за секунды.
"""
import os, re, sys

ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def walk_files(exts):
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in ('.git', 'node_modules')]
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in exts:
                yield os.path.join(dp, fn)

problems = []
def add(cat, path, detail):
    problems.append((cat, os.path.relpath(path, ROOT), detail))

# 1 + 4. Markdown links
LINK = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
OUTSIDE = ('research/', '../../research', 'docs/grillmax', 'прототип/', 'правовое/', 'ДВИЖОК/', 'исследования/', 'спека-экранов/')
for f in walk_files({'.md'}):
    txt = open(f, encoding='utf-8', errors='replace').read()
    base = os.path.dirname(f)
    for m in LINK.finditer(txt):
        tgt = m.group(1).strip()
        if tgt.startswith(('http://', 'https://', '#', 'mailto:')):
            continue
        tgt_clean = tgt.split('#')[0].split('?')[0]
        if not tgt_clean:
            continue
        if any(o in tgt for o in OUTSIDE):
            add('link-outside-package', f, tgt)
            continue
        dest = os.path.normpath(os.path.join(base, tgt_clean))
        if not os.path.exists(dest):
            add('link-broken', f, tgt)

# 2. casefold collisions
seen = {}
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if d not in ('.git', 'node_modules')]
    for fn in fns:
        key = os.path.join(dp, fn).lower()
        if key in seen:
            add('casefold-collision', os.path.join(dp, fn), seen[key])
        seen[key] = os.path.join(dp, fn)

# 3. stale phrases (видимый текст: .md и прототип .html)
STALE = [
    (r'двухстадийн(ая|ой) оплат', 'двухстадийная оплата (снята D-056)'),
    (r'списани[ея] при выдаче', 'списание при выдаче (снято, charge-now)'),
    (r'ставит холд|холд ставится', 'модель холда (снята)'),
    (r'мастер-числ', 'мастер-число (в UI запрещено, safety-rules §Терминология)'),
    (r'\bдош[аеуиы]\b', 'доша (в UI запрещено)'),
    (r'число души|числа души|Число души', 'число души (термин упразднён)'),
    (r'(все )?четыре школы соглас|4 из 4 школ', '«4 из 4» как доказательство (считать по семействам)'),
]
NEG = re.compile(r'без холда|от холда|не.{0,3}холд|нет холда|снят|упразд|запрещ|не используетс|не выводит|ОТМЕН|устар|термин «|не применяет|→|УБРАН|старые имена|польз\. назв|в UI —|не ярлык|синоним|архив')
# Терм-скан только там, где текст ВИДЕН пользователю: прототип + UI-спеки.
# Канон/опора (safety-rules, NUMEROLOGY-RULES, …) легитимно определяют запретные
# термины, поэтому в терм-скан не входят.
SCAN = []
for x in ('02-report.html', '01-onboarding.html', '04-welcome.html', '05-bot.html', '_botdata.js'):
    p = os.path.join(ROOT, 'wireframes', x)
    if os.path.exists(p):
        SCAN.append(p)
for f in SCAN:
    for ln, line in enumerate(open(f, encoding='utf-8', errors='replace'), 1):
        for pat, label in STALE:
            if re.search(pat, line) and not NEG.search(line):
                add('stale-phrase-UI', f, f'{ln}: {label}')
                break

# report
cats = {}
for c, p, d in problems:
    cats.setdefault(c, []).append((p, d))
print(f'Проверено в: {ROOT}')
if not problems:
    print('✅ Замечаний нет.')
    sys.exit(0)
for c in sorted(cats):
    items = cats[c]
    print(f'\n[{c}] — {len(items)}')
    for p, d in items[:60]:
        print(f'  {p} :: {d}')
    if len(items) > 60:
        print(f'  … и ещё {len(items)-60}')
print(f'\nИтого замечаний: {len(problems)}')
sys.exit(1)
