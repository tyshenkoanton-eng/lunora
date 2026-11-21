"""G17-S2a: golden нумерологии (NUMEROLOGY-RULES.md §9.2) против `lunora.engines.numerology`.

Кейсы — tests/golden/numerology/*.yaml, ожидания расшифрованы из спеки без пересчёта.
`snapshot()` раскладывает результат движка по путям ожиданий (`EXPRESSION`, `CELLS`,
`error.code`, …). Ошибка входа — отказ движка (fail closed), а не значение.
"""

import os
import pathlib

import pytest
import yaml

from lunora.engines import numerology as num

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden" / "numerology"


def _cases():
    out = []
    for path in sorted(GOLDEN.rglob("*.y*ml")):
        for case in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if case and case.get("layer") == "numerology":
                out.append(case)
    return out


CASES = _cases()
ACTIVE = [c for c in CASES if c["status"] == "active"]


def _run(inp: dict) -> dict:
    nb = inp.get("name_birth")
    name = num.FullName(nb["surname"], nb["given"], nb.get("patronymic")) if nb else None
    try:
        res = num.calculate(
            birth_date=inp.get("birth_date"), name_birth=name, calc_date=inp.get("calc_date")
        )
    except num.NumerologyInputError as e:
        return {"error.code": e.code, "error.field": e.field, "error.position": e.position}
    return num.snapshot(res)


def test_golden_set_is_complete():
    ids = {c["id"] for c in CASES}
    expected = (
        {f"G-N{i:02d}" for i in range(1, 12)}
        | {f"G-D{i:02d}" for i in range(1, 13)}
        | {f"G-S{i:02d}" for i in range(1, 5)}
    )
    assert expected <= ids


@pytest.mark.parametrize("case", ACTIVE, ids=[c["id"] for c in ACTIVE])
def test_numerology_matches_spec(case):
    snap = _run(case["input"])
    misses = [
        (e["path"], e["value"], snap.get(e["path"], "<нет>"))
        for e in case["expected"]
        if snap.get(e["path"], "<нет>") != e["value"]
    ]
    assert not misses, misses


@pytest.mark.skipif(
    not os.environ.get("LUNORA_PRIVATE_NUMEROLOGY_FIXTURE"),
    reason="G-S04: закрытый fixture профиля стейкхолдера вне репозитория (152-ФЗ)",
)
def test_stakeholder_profile_regression():
    fx = yaml.safe_load(
        pathlib.Path(os.environ["LUNORA_PRIVATE_NUMEROLOGY_FIXTURE"]).read_text(encoding="utf-8")
    )
    snap = _run(fx["input"])
    misses = [(k, v, snap.get(k)) for k, v in fx["expected"].items() if snap.get(k) != v]
    assert not misses, misses
