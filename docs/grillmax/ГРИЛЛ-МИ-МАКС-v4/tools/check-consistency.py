#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ГРИЛЛ МИ МАКС — референс-чекер связности и распространения решений (П3, машинная половина).

ПОРТАТИВНЫЙ: не привязан к конкретному проекту. Специфику (запретные термины,
якоря проекта) читает из необязательного tools/grillmax-check.config.json.
Решения берёт из _SESSION.json (gates[*].decisions[]) и/или DECISIONS.md.

Это НЕ заменяет смысловую проверку агента (сравнение бизнес-правил по существу) —
машина ловит форму: битые ссылки, коллизии имён, недонесённые/устаревшие решения,
опционально запретные термины. Смысловой вердикт агент выносит сам (см. П3 в SKILL.md).

Запуск:  python3 tools/check-consistency.py [корень_пакета]
По умолчанию корень — родитель папки tools/. Только чтение, ничего не меняет.

Коды выхода:
  0 — блокирующих замечаний нет (информационные допустимы);
  1 — есть блокирующие замечания;
  2 — корень не найден или не похож на пакет ГРИЛЛ МИ МАКС.
"""
import os, re, sys, json, glob

ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- 0. Защита от «ложного зелёного»: корень должен быть похож на пакет дискавери.
#         Якорь — SKILL.md ИЛИ _SESSION.json (методология или живая сессия).
if not os.path.isdir(ROOT):
    print(f'⛔ Корень не найден или не каталог: {ROOT}'); sys.exit(2)
if not (os.path.exists(os.path.join(ROOT, 'SKILL.md')) or os.path.exists(os.path.join(ROOT, '_SESSION.json'))):
    # не методологический пакет и не сессия — но, возможно, указали корень docs; мягко предупредим
    print(f'⚠️  В {ROOT} нет ни SKILL.md, ни _SESSION.json — проверяю что есть.')

TEXT_EXT = ('.md', '.html', '.htm', '.json', '.txt')
CANCEL_WORDS = re.compile(r'отмен|замен|устар|supersed|deprecat|вместо\s+нег', re.I)

def rel(p): return os.path.relpath(p, ROOT)

def walk_files():
    for dp, dn, fn in os.walk(ROOT):
        if '/.git' in dp or os.sep + '.git' in dp: continue
        for f in fn:
            yield os.path.join(dp, f)

def read(p):
    try:
        with open(p, encoding='utf-8') as fh: return fh.read()
    except Exception: return ''

blocking, info = [], []

# --- optional config -------------------------------------------------------
cfg = {}
cfg_path = os.path.join(ROOT, 'tools', 'grillmax-check.config.json')
if os.path.exists(cfg_path):
    try: cfg = json.loads(read(cfg_path))
    except Exception as e: info.append(('config-parse', f'grillmax-check.config.json не распарсился: {e}'))

# --- 1. Битые внутренние markdown-ссылки -----------------------------------
LINK = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
for p in walk_files():
    if not p.endswith('.md'): continue
    base = os.path.dirname(p)
    for m in LINK.finditer(read(p)):
        target = m.group(1).strip()
        if target.startswith(('http://', 'https://', 'mailto:', '#')): continue
        path_only = target.split('#')[0].split('?')[0]
        if not path_only: continue
        dest = os.path.normpath(os.path.join(base, path_only))
        if not os.path.commonpath([dest, ROOT]) == ROOT:
            info.append(('link-outside-package', f'{rel(p)} :: {target}')); continue
        if not os.path.exists(dest):
            blocking.append(('link-broken', f'{rel(p)} :: {target}'))

# --- 2. Casefold-коллизии имён файлов --------------------------------------
seen = {}
for p in walk_files():
    key = rel(p).casefold()
    if key in seen and seen[key] != rel(p):
        blocking.append(('casefold-collision', f'{seen[key]} vs {rel(p)}'))
    seen[key] = rel(p)

# --- 3. Решения: распространение и устаревание (из _SESSION.json + DECISIONS.md) ---
decisions = {}  # id -> {status, dependents:[...], superseded_by}
sess_path = os.path.join(ROOT, '_SESSION.json')
if os.path.exists(sess_path):
    try:
        sess = json.loads(read(sess_path))
        for g in (sess.get('gates') or {}).values():
            for d in (g.get('decisions') or []):
                if 'id' in d:
                    decisions[d['id']] = {
                        'status': d.get('status', 'active'),
                        'dependents': d.get('dependents', []),
                        'superseded_by': d.get('superseded_by')}
    except Exception as e:
        info.append(('session-parse', f'_SESSION.json не распарсился: {e}'))

dec_md = os.path.join(ROOT, 'DECISIONS.md')
if os.path.exists(dec_md):
    # таблица: | ID | значение | источник | зависимые | версия | статус |
    for line in read(dec_md).splitlines():
        cells = [c.strip() for c in line.split('|')]
        if len(cells) >= 7 and re.match(r'^[A-ZА-Я]-?\d', cells[1]):
            did = cells[1]
            deps = [x.strip() for x in re.split(r'[,\s]+', cells[4]) if x.strip()]
            status = 'superseded' if CANCEL_WORDS.search(cells[6]) or 'supersed' in cells[6].lower() else 'active'
            decisions.setdefault(did, {'status': status, 'dependents': deps, 'superseded_by': None})

# индекс всего видимого текста
all_text = {rel(p): read(p) for p in walk_files() if p.endswith(TEXT_EXT)}

for did, d in decisions.items():
    if d['status'] == 'active':
        for dep in d['dependents']:
            dep_norm = dep if dep.endswith(TEXT_EXT) else None
            # зависимый может быть именем файла или фрагментом пути
            hit = any(did in txt for f, txt in all_text.items() if dep in f)
            exists = any(dep in f for f in all_text)
            if not exists:
                info.append(('dependent-missing', f'{did}: зависимый «{dep}» не найден'))
            elif not hit:
                blocking.append(('decision-not-propagated', f'{did} не упомянут в зависимом «{dep}»'))
    else:  # superseded / отменено
        for f, txt in all_text.items():
            for mobj in re.finditer(re.escape(did), txt):
                window = txt[max(0, mobj.start()-80):mobj.end()+80]
                if not CANCEL_WORDS.search(window):
                    blocking.append(('cancelled-referenced', f'{did} упомянут как действующий в {f}'))
                    break

# --- 4. Запретные термины (опционально, из конфига) ------------------------
banned = cfg.get('banned_terms') or []
scope_globs = cfg.get('banned_scope_globs') or ['**/*.html']
if banned:
    scoped = set()
    for g in scope_globs:
        scoped.update(glob.glob(os.path.join(ROOT, g), recursive=True))
    for p in scoped:
        txt = read(p)
        for term in banned:
            if re.search(term, txt, re.I):
                blocking.append(('banned-term', f'{rel(p)} :: «{term}»'))

# --- 5. ID рисков без определения (эвристика, инфо) -------------------------
risks_file = next((f for f in all_text if os.path.basename(f).upper().startswith('RISKS')), None)
if risks_file:
    defined = set(re.findall(r'\b([RРR]-?\d{1,3})\b', all_text[risks_file]))
    referenced = set()
    for f, txt in all_text.items():
        if f == risks_file: continue
        referenced.update(re.findall(r'\b(R-\d{1,3})\b', txt))
    for rid in sorted(referenced - defined):
        info.append(('risk-id-undefined', f'{rid} не определён в RISKS'))

# --- отчёт -----------------------------------------------------------------
from collections import Counter
print(f'Проверено в: {ROOT}\n')
def dump(items, suffix):
    for cat in Counter(c for c, _ in items):
        rows = [m for c, m in items if c == cat]
        print(f'[{cat}] — {len(rows)}{suffix}')
        for r in rows[:40]: print(f'  {r}')
        if len(rows) > 40: print(f'  … ещё {len(rows)-40}')

if blocking:
    print('— БЛОКИРУЮЩИЕ —'); dump(blocking, '  (БЛОКИРУЮЩЕЕ)')
if info:
    print('\n— ИНФОРМАЦИОННЫЕ —'); dump(info, '  (информационно, код выхода 0)')
print(f'\nИтого: блокирующих — {len(blocking)}, информационных — {len(info)}')
sys.exit(1 if blocking else 0)
