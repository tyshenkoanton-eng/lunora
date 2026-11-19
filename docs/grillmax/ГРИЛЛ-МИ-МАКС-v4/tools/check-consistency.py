#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ГРИЛЛ МИ МАКС — референс-чекер связности и распространения решений (П3, машинная половина).

ПОРТАТИВНЫЙ: специфику проекта читает из tools/grillmax-check.config.json, не хардкодит.
Машина ловит ФОРМУ (файлы, точные ID, статусы, версии, ссылки, запретные строки).
СМЫСЛ (бизнес-правила, цены, инварианты) проверяет агент и фиксирует в CONSISTENCY_REPORT.md
— без его вердикта exit П3 не считается пройденным, даже если код вернул 0 (см. П3 в SKILL.md).

Два режима (определяются автоматически, можно задать --mode):
  • package — методологический пакет (есть SKILL.md, нет _SESSION.json): ссылки, casefold,
    запретные термины. Реестр решений не требуется.
  • project — живой проект (есть _SESSION.json): всё выше + ОБЯЗАТЕЛЬНЫЙ реестр решений,
    распространение, устаревание (stale по ревизиям), конфликт реестров, неизвестные ID.

Запуск:  python3 tools/check-consistency.py [корень] [--mode package|project] [--json]
Коды выхода: 0 — блокирующих нет · 1 — есть блокирующие · 2 — корень не похож на пакет/проект.
Только чтение.
"""
import os, re, sys, json, glob
from collections import Counter

args = [a for a in sys.argv[1:] if not a.startswith('--')]
flags = [a for a in sys.argv[1:] if a.startswith('--')]
ROOT = os.path.abspath(args[0]) if args else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODE = next((f.split('=',1)[1] for f in flags if f.startswith('--mode')), None)
JSON_OUT = '--json' in flags

TEXT_EXT = ('.md', '.html', '.htm', '.json', '.txt')
GATE_STATUSES = {'not_started','draft','ready_for_review','accepted','waived','blocked','conditional','contract_only','stale'}
DEC_STATUSES = {'active','superseded'}
# слова, по которым упоминание отменённого решения считается историческим (не действующим).
# Намеренно только явные рус. маркеры: англ. "deprecated" сам по себе не оправдывает (лазейка р.2).
CANCEL_WORDS = re.compile(r'отмен|замен(?:ён|ен|а)|устар|вместо\s+нег', re.I)

blocking, info = [], []
def blk(cat, msg): blocking.append((cat, msg))
def inf(cat, msg): info.append((cat, msg))
def rel(p): return os.path.relpath(p, ROOT)
def read(p):
    try:
        with open(p, encoding='utf-8') as fh: return fh.read()
    except Exception: return ''
def walk_files():
    for dp, _, fn in os.walk(ROOT):
        if os.sep + '.git' in dp: continue
        for f in fn: yield os.path.join(dp, f)

# --- 0. Корень и режим -----------------------------------------------------
if not os.path.isdir(ROOT):
    print(f'⛔ Корень не найден или не каталог: {ROOT}'); sys.exit(2)
has_skill = os.path.exists(os.path.join(ROOT, 'SKILL.md'))
has_session = os.path.exists(os.path.join(ROOT, '_SESSION.json'))
if not MODE:
    MODE = 'project' if has_session else ('package' if has_skill else None)
if MODE not in ('package', 'project'):
    print(f'⛔ {ROOT} не похож ни на методологический пакет (SKILL.md), ни на проект (_SESSION.json).')
    sys.exit(2)

# --- config ----------------------------------------------------------------
cfg = {}
cfg_path = os.path.join(ROOT, 'tools', 'grillmax-check.config.json')
if os.path.exists(cfg_path):
    try: cfg = json.loads(read(cfg_path))
    except Exception as e: blk('config-parse', f'grillmax-check.config.json не распарсился: {e}')
DEC_ID_RE = re.compile(cfg.get('decision_id_pattern', r'[A-ZА-Я]{1,4}-\d{1,4}'))

def id_present(did, txt):
    """Точное вхождение ID (D-001 не матчит D-0010)."""
    return re.search(r'(?<![\w-])' + re.escape(did) + r'(?![\w-])', txt) is not None

# --- 1. Битые внутренние markdown-ссылки -----------------------------------
LINK = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
for p in walk_files():
    if not p.endswith('.md'): continue
    base = os.path.dirname(p)
    for m in LINK.finditer(read(p)):
        target = m.group(1).strip()
        if target.startswith(('http://','https://','mailto:','#')): continue
        path_only = target.split('#')[0].split('?')[0]
        if not path_only: continue
        dest = os.path.normpath(os.path.join(base, path_only))
        try: inside = os.path.commonpath([dest, ROOT]) == ROOT
        except ValueError: inside = False
        if not inside: inf('link-outside-package', f'{rel(p)} :: {target}')
        elif not os.path.exists(dest): blk('link-broken', f'{rel(p)} :: {target}')

# --- 2. Casefold-коллизии --------------------------------------------------
seen = {}
for p in walk_files():
    key = rel(p).casefold()
    if key in seen and seen[key] != rel(p): blk('casefold-collision', f'{seen[key]} vs {rel(p)}')
    seen[key] = rel(p)

all_text = {rel(p): read(p) for p in walk_files() if p.endswith(TEXT_EXT)}

# --- 3. Запретные термины (конфиг) -----------------------------------------
banned = cfg.get('banned_terms') or []
if banned:
    scoped = set()
    for g in (cfg.get('banned_scope_globs') or ['**/*.html']):
        scoped.update(glob.glob(os.path.join(ROOT, g), recursive=True))
    for p in scoped:
        txt = read(p)
        for term in banned:
            if re.search(term, txt, re.I): blk('banned-term', f'{rel(p)} :: «{term}»')

# --- 4. Проектные проверки (режим project) ---------------------------------
session, gate_rev = None, {}
if MODE == 'project':
    # 4.0 сессия обязана парситься
    try:
        session = json.loads(read(os.path.join(ROOT, '_SESSION.json')))
    except Exception as e:
        blk('session-unreadable', f'_SESSION.json не парсится: {e}')
        session = None

    # 4.1 собрать реестр решений из двух источников (DECISIONS.md — канонический)
    dec_canon, dec_sess = {}, {}
    dec_md = os.path.join(ROOT, 'DECISIONS.md')
    if os.path.exists(dec_md):
        for line in read(dec_md).splitlines():
            cells = [c.strip() for c in line.split('|')]
            if len(cells) >= 7 and DEC_ID_RE.fullmatch(cells[1] or ''):
                did = cells[1]
                if did in dec_canon: blk('duplicate-decision-id', f'{did} дважды в DECISIONS.md')
                status = 'superseded' if re.search(r'supersed|отмен|устар', cells[6], re.I) else 'active'
                deps = [x.strip() for x in re.split(r'[,\s]+', cells[4]) if x.strip()]
                dec_canon[did] = {'status': status, 'dependents': deps, 'value': cells[2], 'src': 'DECISIONS.md'}
    if session:
        for gname, g in (session.get('gates') or {}).items():
            if 'revision' in g: gate_rev[gname] = g['revision']
            if g.get('status') and g['status'] not in GATE_STATUSES:
                blk('bad-gate-status', f'{gname}: статус «{g["status"]}» вне словаря')
            for d in (g.get('decisions') or []):
                did = d.get('id')
                if not did: continue
                if did in dec_sess: blk('duplicate-decision-id', f'{did} дважды в _SESSION.json')
                st = d.get('status', 'active')
                if st not in DEC_STATUSES: blk('bad-decision-status', f'{did}: статус «{st}» вне словаря')
                dec_sess[did] = {'status': st, 'dependents': d.get('dependents', []), 'value': d.get('value'), 'src': '_SESSION.json'}

    # 4.2 конфликт реестров (один ID, разные статус/значение)
    for did in set(dec_canon) & set(dec_sess):
        a, b = dec_canon[did], dec_sess[did]
        if a['status'] != b['status'] or (a.get('value') and b.get('value') and a['value'] != b['value']):
            blk('registry-conflict', f'{did}: DECISIONS.md={a["status"]}/{a.get("value")} ≠ _SESSION.json={b["status"]}/{b.get("value")}')
    decisions = {**dec_sess, **dec_canon}  # канонический перекрывает

    # 4.3 реестр обязателен
    if not decisions:
        blk('registry-missing', 'режим project, но реестр решений пуст (нет DECISIONS.md и decisions в _SESSION.json) — П3 не проверяем')

    # 4.4 распространение и устаревание отменённых
    registry_files = {'DECISIONS.md', '_SESSION.json'}
    for did, d in decisions.items():
        if d['status'] == 'active':
            for dep in d['dependents']:
                matches = [f for f in all_text if dep in f]
                if not matches: blk('dependent-missing', f'{did}: зависимый «{dep}» не найден')
                elif not any(id_present(did, all_text[f]) for f in matches):
                    blk('decision-not-propagated', f'{did} не упомянут в зависимом «{dep}»')
        else:  # superseded
            repl = d.get('superseded_by')
            for f, txt in all_text.items():
                if os.path.basename(f) in registry_files: continue
                for mo in re.finditer(r'(?<![\w-])' + re.escape(did) + r'(?![\w-])', txt):
                    w = txt[max(0, mo.start()-80):mo.end()+80]
                    excused = CANCEL_WORDS.search(w) or (repl and id_present(repl, w))
                    if not excused:
                        blk('cancelled-referenced', f'{did} упомянут как действующий в {f}'); break

    # 4.5 неизвестные ID решений (встречается ID-образный токен, которого нет в реестре)
    for f, txt in all_text.items():
        if os.path.basename(f) in {'DECISIONS.md', '_SESSION.json', 'SKILL.md'}: continue
        for tok in set(DEC_ID_RE.findall(txt)):
            if tok not in decisions and re.match(r'[DРД]-\d', tok):
                inf('unknown-decision-id', f'{f}: {tok} не определён в реестре') if MODE != 'project' else blk('unknown-decision-id', f'{f}: {tok} не определён в реестре')

    # 4.6 устаревание артефактов по ревизиям входов
    if session:
        for gname, g in (session.get('gates') or {}).items():
            art = g.get('artifact') or {}
            for ig, used_rev in (art.get('input_versions') or {}).items():
                cur = gate_rev.get(ig)
                if cur is None: inf('revision-missing', f'{gname}: вход {ig} без зафиксированной revision — устаревание не проверить')
                elif str(cur) != str(used_rev):
                    blk('artifact-stale', f'{gname}: артефакт на {ig}={used_rev}, а текущая {ig}={cur} → stale, нужна повторная приёмка')

    # 4.7 токены (если есть) — валидный JSON с нужными ключами
    for f in all_text:
        if os.path.basename(f) in ('tokens.json', 'brand.tokens.json'):
            try:
                data = json.loads(all_text[f])
                top = data.get('color') or data.get('brand', {}).get('color')
                if not top: blk('tokens-schema', f'{f}: нет ключа color/brand.color')
            except Exception as e: blk('tokens-invalid', f'{f}: не парсится как JSON: {e}')

# --- 5. ID рисков без определения (инфо) ------------------------------------
risks_file = next((f for f in all_text if os.path.basename(f).upper().startswith('RISKS')), None)
if risks_file:
    defined = set(re.findall(r'\b([RРД]-?\d{1,3})\b', all_text[risks_file]))
    referenced = set()
    for f, txt in all_text.items():
        if f != risks_file: referenced.update(re.findall(r'\b(R-\d{1,3})\b', txt))
    for rid in sorted(referenced - defined): inf('risk-id-undefined', f'{rid} не определён в RISKS')

# --- отчёт -----------------------------------------------------------------
if JSON_OUT:
    print(json.dumps({'root': ROOT, 'mode': MODE, 'blocking': blocking, 'info': info,
        'blocking_count': len(blocking), 'info_count': len(info),
        'note': 'машинная половина П3; смысловой вердикт агента — в CONSISTENCY_REPORT.md'}, ensure_ascii=False, indent=2))
    sys.exit(1 if blocking else 0)

print(f'Проверено в: {ROOT}  (режим: {MODE})\n')
def dump(items, suffix):
    for cat in Counter(c for c, _ in items):
        rows = [m for c, m in items if c == cat]
        print(f'[{cat}] — {len(rows)}{suffix}')
        for r in rows[:40]: print(f'  {r}')
        if len(rows) > 40: print(f'  … ещё {len(rows)-40}')
if blocking: print('— БЛОКИРУЮЩИЕ —'); dump(blocking, '  (БЛОКИРУЮЩЕЕ)')
if info: print('\n— ИНФОРМАЦИОННЫЕ —'); dump(info, '  (информационно, код 0)')
print(f'\nИтого: блокирующих — {len(blocking)}, информационных — {len(info)}')
if MODE == 'project':
    print('⚠️  Машина проверила только форму. Exit П3 требует ещё вердикт агента в CONSISTENCY_REPORT.md.')
sys.exit(1 if blocking else 0)
