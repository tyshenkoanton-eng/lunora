"""G17-S2e: весь рантайм `lunora.*` не импортирует оракулы (ENGINE-SOURCES §6, ADR-001).

После переключения рантайма на `lunora.engines.*` ни один продуктовый модуль (API, бот,
calc, timeplace, interpret, llm, forecast) не тянет pyswisseph / cnlunar / timezonefinder
/ lunar-python / PyJHora — они живут только в группе `[oracle]` и в `tests/diff`. Проверка
статическая (AST), ловит и ленивые импорты внутри функций. Падает, если рантайм потянет оракул.
"""

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "lunora"
FORBIDDEN = {"swisseph", "jhora", "pyjhora", "cnlunar", "lunar_python", "timezonefinder"}


def _imported_roots(path: pathlib.Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_runtime_does_not_import_oracles():
    bad = {
        str(p.relative_to(SRC)): sorted(_imported_roots(p) & FORBIDDEN)
        for p in SRC.rglob("*.py")
        if _imported_roots(p) & FORBIDDEN
    }
    assert not bad, bad
