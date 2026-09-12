#!/usr/bin/env python3
"""Сверка закрытых экранов: не изменилось ли то, что уже согласовано.

Порядок:
  1. После простановки замков снимается эталон  →  locked-snapshot.json
  2. После любой правки снимается новый снимок  →  сравнивается с эталоном
  3. Любое расхождение — повод остановиться и спросить

Снимок берётся из прототипа вызовом window.lockSnapshot().
"""
import json, sys, hashlib, io, os

BASE = os.path.join(os.path.dirname(__file__), 'locked-snapshot.json')

def digest(html):
    return hashlib.sha256(html.encode('utf-8')).hexdigest()[:12]

def save(snapshot):
    data = {k: {'hash': digest(v), 'len': len(v)} for k, v in snapshot.items()}
    io.open(BASE, 'w', encoding='utf-8').write(json.dumps(data, ensure_ascii=False, indent=2))
    print(f'эталон записан: {len(data)} экранов')

def check(snapshot):
    if not os.path.exists(BASE):
        print('эталона нет — сначала сохраните его'); return 1
    base = json.load(io.open(BASE, encoding='utf-8'))
    bad, gone, new = [], [], []
    for k, v in base.items():
        if k not in snapshot: gone.append(k)
        elif digest(snapshot[k]) != v['hash']:
            bad.append((k, v['len'], len(snapshot[k])))
    for k in snapshot:
        if k not in base: new.append(k)
    if bad:
        print('⛔ ИЗМЕНИЛИСЬ ЗАКРЫТЫЕ ЭКРАНЫ:')
        for k, a, b in bad: print(f'   {k}: было {a} знаков, стало {b}')
    if gone: print('⚠ пропали из снимка:', ', '.join(gone))
    if new: print('· закрыты новые:', ', '.join(new))
    if not bad and not gone: print(f'✓ все {len(base)} закрытых экранов не тронуты')
    return 1 if bad or gone else 0

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'check'
    snapshot = json.load(sys.stdin)
    sys.exit(save(snapshot) or 0 if mode == 'save' else check(snapshot))
