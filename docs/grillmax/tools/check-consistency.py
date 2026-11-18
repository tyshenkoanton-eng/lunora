#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Гейт связности пакета «Лунора» (по рекомендации внешних ревью v5/v6/v7).
Запуск из любого места:  python3 tools/check-consistency.py [корень_grillmax]
По умолчанию корень — родитель папки tools/. Только чтение, ничего не меняет.

Коды выхода:
  0 — блокирующих замечаний нет (информационные допустимы);
  1 — есть блокирующие замечания;
  2 — корень не найден или не похож на пакет «Лунора» (защита от «ложного зелёного»).

Две категории:
  • БЛОКИРУЮЩИЕ (код 1): битые внутренние ссылки, casefold-коллизии,
    снятые термины в видимом тексте, неоговорённое «маржа >85 %».
  • ИНФОРМАЦИОННЫЕ (код 0): внешние ссылки на research/ (намеренно вне пакета),
    ID рисков без определения в RISKS.md.

Что проверяет:
  1. Битые относительные markdown-ссылки [..](path) на файлы внутри пакета.
  2. Casefold-коллизии имён файлов (ENGINE-SPEC.md vs engine-spec.md).
  3. Остатки снятых моделей/терминов в ВИДИМОМ тексте: прототип .html (вся
     строка) + UI-строки спек в «кавычках-ёлочках» (методописание не трогаем):
     холд/двухстадийная оплата, «мастер-число»/«доша»/«число души», «4 из 4»,
     «все направления/школы согласны».
  4. Ссылки на несуществующие каталоги плоской структуры (research/, v3-каталоги) — инфо.
  5. Число↔факт (эвристика): «маржа >85 %» без разведения gross/net.
  6. ID↔определение (эвристика, инфо): R-NN без строки-определения в RISKS.md.
Это не заменяет внешнее ревью, но ловит класс «хвостов после правки» за секунды.
"""
import os, re, sys

ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- 0. Защита от «ложного зелёного»: корень должен существовать и быть пакетом «Лунора».
ANCHORS = ('РЕШЕНИЯ-БЛОКЕРЫ.md', 'ПРАЙС.md', os.path.join('wireframes', '02-report.html'))
if not os.path.isdir(ROOT):
    print(f'⛔ Корень не найден или не каталог: {ROOT}')
    sys.exit(2)
missing_anchors = [a for a in ANCHORS if not os.path.exists(os.path.join(ROOT, a))]
if missing_anchors:
    print(f'⛔ Корень {ROOT} не похож на пакет «Лунора» — нет опорных файлов: {", ".join(missing_anchors)}')
    print('   (чтобы гейт не давал «зелёный» на неверном пути — см. ревью v7 §3.2)')
    sys.exit(2)

# Категории, которые НЕ влияют на код выхода (информационные).
INFO_CATS = {'link-outside-package', 'id-undefined'}

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

# 3. stale phrases (видимый текст: прототип .html + UI-спеки)
STALE = [
    (r'двухстадийн(ая|ой) оплат', 'двухстадийная оплата (снята D-056)'),
    (r'списани[ея] при выдаче', 'списание при выдаче (снято, charge-now)'),
    (r'ставит холд|холд ставится', 'модель холда (снята)'),
    (r'мастер-числ', 'мастер-число (в UI запрещено, safety-rules §Терминология)'),
    (r'\bдош[аеуиы]\b', 'доша (в UI запрещено)'),
    (r'число души|числа души|Число души', 'число души (термин упразднён)'),
    (r'(все )?четыре школы соглас|4 из 4 школ', '«4 из 4» как доказательство (считать по семействам)'),
    (r'(?i)все (четыре )?направлени[яй] соглас|все (четыре )?школ[аы] соглас', '«все направления/школы согласны» = 4-из-4 как доказательство (считать по семействам, B24)'),
]
NEG = re.compile(r'без холда|от холда|не.{0,3}холд|нет холда|снят|упразд|запрещ|не используетс|не выводит|ОТМЕН|устар|термин «|не применяет|УБРАН|старые имена|польз\. назв|в UI —|не ярлык|синоним|архив')
# N2 (ревью v8): символ «→» убран из NEG — он глушил 77 строк с обычными
# стрелками-переходами («Оплата → доступ», «56 → 5+6»), создавая слепую зону.
# Терм-скан только там, где текст ВИДЕН пользователю: прототип + UI-спеки.
# Канон/опора (safety-rules, NUMEROLOGY-RULES, …) легитимно определяют запретные
# термины, поэтому в терм-скан не входят.
SCAN = []
for x in ('02-report.html', '01-onboarding.html', '04-welcome.html', '05-bot.html'):
    p = os.path.join(ROOT, 'wireframes', x)
    if os.path.exists(p):
        SCAN.append(p)
# N1 (ревью v8): докстринг обещает «прототип + UI-спеки» — добавляем сами спеки,
# чтобы запретный термин в видимом тексте продукта (напр. в spec/chat.md) ловился.
spec_dir = os.path.join(ROOT, 'spec')
if os.path.isdir(spec_dir):
    for fn in sorted(os.listdir(spec_dir)):
        if fn.lower().endswith('.md'):
            SCAN.append(os.path.join(spec_dir, fn))
for f in SCAN:
    # В прототипе .html видимый текст — вся строка. В спеке .md видимый текст
    # продукта — это строки в «кавычках-ёлочках»; прочее — методописание, где
    # термин метода назвать можно (safety-rules «Область действия запрета»).
    is_spec = f.lower().endswith('.md')
    for ln, line in enumerate(open(f, encoding='utf-8', errors='replace'), 1):
        if NEG.search(line):
            continue
        segments = re.findall(r'«([^»]*)»', line) if is_spec else [line]
        for seg in segments:
            for pat, label in STALE:      # считаем КАЖДОЕ нарушение, не одно на строку
                if re.search(pat, seg):
                    add('stale-phrase-UI', f, f'{ln}: {label}')

# 5. Число↔факт (эвристика): «маржа >85 %» без разведения gross/net.
MARGIN = re.compile(r'маржа\s*>\s*85|маржинальн\w*\s*>\s*85|маржа\s+выше\s+85')
MARGIN_OK = re.compile(r'gross|net|нетто|брутто|83[.,]5')
for f in walk_files({'.md'}):
    for ln, line in enumerate(open(f, encoding='utf-8', errors='replace'), 1):
        if MARGIN.search(line) and not MARGIN_OK.search(line):
            add('margin-unqualified', f, f'{ln}: «маржа >85 %» без gross/net (пакет 50 — ниже 85 % net, ПРАЙС §3)')

# 6. ID↔определение (эвристика, инфо): R-NN без строки-определения в RISKS.md.
# Определением считаем строку таблицы RISKS.md вида «| **R-NN** | …» или «| R-NN |».
risks_path = os.path.join(ROOT, 'RISKS.md')
defined = set()
declared_unused = set()   # N4 (ревью v8): читаем объявленный в RISKS.md диапазон «не используются», не хардкодим
if os.path.exists(risks_path):
    for line in open(risks_path, encoding='utf-8', errors='replace'):
        for m in re.finditer(r'\|\s*\*{0,2}(R-\d+)\*{0,2}\s*\|', line):
            defined.add(m.group(1))
        # строки-объявления «номера R-a…R-b и R-n не использованы/не заняты»
        if re.search(r'не использ|не заняты|не занят', line):
            for a, b in re.findall(r'R-(\d+)\s*(?:…|\.{2,}|[—–-])\s*R-(\d+)', line):
                declared_unused |= {f'R-{n}' for n in range(int(a), int(b) + 1)}
            for n in re.findall(r'R-(\d+)', line):
                declared_unused.add(f'R-{n}')
referenced = {}
for f in walk_files({'.md'}):
    for ln, line in enumerate(open(f, encoding='utf-8', errors='replace'), 1):
        for m in re.finditer(r'\bR-\d+\b', line):
            referenced.setdefault(m.group(0), (os.path.relpath(f, ROOT), ln))
for rid, (p, ln) in sorted(referenced.items()):
    if rid not in defined and rid not in declared_unused:
        add('id-undefined', os.path.join(ROOT, p), f'{ln}: {rid} не определён в RISKS.md и не входит в объявленный диапазон неиспользуемых')

# --- report
cats = {}
for c, p, d in problems:
    cats.setdefault(c, []).append((p, d))
print(f'Проверено в: {ROOT}')

blocking = [c for c in cats if c not in INFO_CATS]
info = [c for c in cats if c in INFO_CATS]

if not problems:
    print('✅ Замечаний нет.')
    sys.exit(0)

for c in sorted(blocking):
    items = cats[c]
    print(f'\n[{c}] — {len(items)}  (блокирующее)')
    for p, d in items[:60]:
        print(f'  {p} :: {d}')
    if len(items) > 60:
        print(f'  … и ещё {len(items)-60}')
for c in sorted(info):
    items = cats[c]
    print(f'\n[{c}] — {len(items)}  (информационно, код выхода 0)')
    for p, d in items[:60]:
        print(f'  {p} :: {d}')
    if len(items) > 60:
        print(f'  … и ещё {len(items)-60}')

n_block = sum(len(cats[c]) for c in blocking)
n_info = sum(len(cats[c]) for c in info)
print(f'\nИтого: блокирующих — {n_block}, информационных — {n_info}')
sys.exit(1 if n_block else 0)
