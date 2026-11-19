#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Регрессионные тесты для check-consistency.py — воспроизводят матрицу повторного ревью.
Запуск:  python3 tools/test_check_consistency.py
Код выхода 0 — все кейсы прошли, 1 — есть провалы.
"""
import os, sys, json, tempfile, subprocess, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, 'check-consistency.py')
PKG = os.path.dirname(HERE)  # сам методологический пакет
fails = []

def run(root):
    r = subprocess.run([sys.executable, CHECKER, root, '--json'], capture_output=True, text=True)
    try: data = json.loads(r.stdout)
    except Exception: data = {'blocking': [], 'info': []}
    cats = {c for c, _ in data.get('blocking', [])}
    return r.returncode, cats

def mk(files):
    d = tempfile.mkdtemp(prefix='gmtest_')
    for name, content in files.items():
        p = os.path.join(d, name); os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f: f.write(content)
    return d

def check(name, root, want_exit, want_cat=None, cleanup=True):
    code, cats = run(root)
    ok = (code == want_exit) and (want_cat is None or want_cat in cats)
    print(f'[{"PASS" if ok else "FAIL"}] {name}: exit={code} cats={sorted(cats) or "—"}')
    if not ok: fails.append(name)
    if cleanup and root != PKG: shutil.rmtree(root, ignore_errors=True)

def sess(gates): return json.dumps({'gates': gates}, ensure_ascii=False)

# 1. методологический пакет — зелёный
check('package-green', PKG, 0, cleanup=False)

# 2. пустой каталог — не похож ни на пакет, ни на проект
check('empty-dir', mk({'readme.txt': 'hi'}), 2)

# 3. битый _SESSION.json
check('corrupt-session', mk({'_SESSION.json': '{ broken'}), 1, 'session-unreadable')

# 4. активное решение, зависимый файл отсутствует
check('missing-dependent', mk({'_SESSION.json': sess({'G5': {'decisions': [
    {'id': 'D-001', 'status': 'active', 'dependents': ['nope.md']}]}})}), 1, 'dependent-missing')

# 5. D-0010 вместо D-001 (точное сравнение, не подстрока)
check('exact-id-not-substring', mk({
    '_SESSION.json': sess({'G5': {'decisions': [{'id': 'D-001', 'status': 'active', 'dependents': ['dep.md']}]}}),
    'dep.md': '# dep\nздесь только D-0010 и ничего больше'}), 1, 'decision-not-propagated')

# 6. устаревание по ревизии входа
check('artifact-stale', mk({'_SESSION.json': sess({
    'G3': {'revision': 'rev-3'},
    'G9': {'artifact': {'input_versions': {'G3': 'rev-2'}}},
    'G5': {'decisions': [{'id': 'D-001', 'status': 'active', 'dependents': ['dep.md']}]}}),
    'dep.md': 'D-001 тут'}), 1, 'artifact-stale')

# 7. неизвестный ID решения — блокирующе только при registry_complete
check('unknown-decision-id', mk({
    '_SESSION.json': sess({'G5': {'decisions': [{'id': 'D-001', 'status': 'active', 'dependents': ['dep.md']}]}}),
    'tools/grillmax-check.config.json': '{"registry_complete": true}',
    'dep.md': 'D-001 тут', 'notes.md': 'мы опираемся на D-999 где-то'}), 1, 'unknown-decision-id')

# 8. битая markdown-ссылка
check('broken-link', mk({'SKILL.md': '# s', 'a.md': 'см [туда](nope.md)'}), 1, 'link-broken')

# 9. casefold-коллизия
d = mk({'SKILL.md': '# s', 'Demo.md': 'a'})
with open(os.path.join(d, 'demo.md'), 'w') as f: f.write('b')
check('casefold', d, 1, 'casefold-collision')

# 10. конфликт двух реестров
check('registry-conflict', mk({
    '_SESSION.json': sess({'G5': {'decisions': [{'id': 'D-001', 'status': 'active', 'dependents': []}]}}),
    'DECISIONS.md': '| ID | Значение | Источник | Зависимые | Версия | Статус |\n| D-001 | x | G5 | | rev-1 | superseded |'}),
    1, 'registry-conflict')

# 11. отменённое решение упомянуто как действующее
check('cancelled-referenced', mk({
    '_SESSION.json': sess({'G5': {'decisions': [{'id': 'D-002', 'status': 'superseded'}]}}),
    'legacy.md': 'мы используем D-002 как основную модель'}), 1, 'cancelled-referenced')

# 12. project без реестра решений
check('registry-missing', mk({'_SESSION.json': sess({'G1': {'status': 'accepted'}})}), 1, 'registry-missing')

# 13. счастливый проект — зелёный
check('project-green', mk({
    '_SESSION.json': sess({
        'G5': {'status': 'accepted', 'decisions': [{'id': 'D-001', 'status': 'active', 'dependents': ['dep.md']}]}}),
    'dep.md': 'реализуем D-001 здесь'}), 0)

print(f'\nИтого: {"ВСЕ ПРОШЛИ" if not fails else "ПРОВАЛЫ: " + ", ".join(fails)}')
sys.exit(1 if fails else 0)
