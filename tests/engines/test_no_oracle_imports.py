"""G17-S2: движки не тянут оракулы (ENGINE-SOURCES §6, ADR-001).

pyswisseph и PyJHora — AGPL, только группа `[oracle]`; cnlunar, lunar-python,
timezonefinder — оракулы тестов. Пакет `lunora.engines` не импортирует ни один из них.
Проверка статическая (по AST), чтобы ловить и ленивые импорты внутри функций.
"""

import ast
import pathlib

ENGINES = pathlib.Path(__file__).resolve().parents[2] / "src" / "lunora" / "engines"
FORBIDDEN = {"swisseph", "jhora", "pyjhora", "cnlunar", "lunar_python", "timezonefinder"}


def _imported_roots(path: pathlib.Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_engines_package_exists():
    assert (ENGINES / "__init__.py").is_file()


def test_engines_do_not_import_oracles():
    bad = {
        str(p.relative_to(ENGINES)): sorted(_imported_roots(p) & FORBIDDEN)
        for p in ENGINES.rglob("*.py")
        if _imported_roots(p) & FORBIDDEN
    }
    assert not bad, bad
