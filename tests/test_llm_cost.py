"""G17-S3b: офлайн-чекер замера стоимости LLM — схема, пороги, отсутствие ключей и сети.

Фикстуры — вымышленные: ни ключей, ни реальных данных, ни ПДн. Пороги берутся
из боевого файла scripts/spike/llm_cost_thresholds.json, схема — боевая
scripts/spike/llm_cost.schema.json (обе копии, не оригиналы).
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "spike" / "llm_cost.py"
SCHEMA = ROOT / "scripts" / "spike" / "llm_cost.schema.json"
THRESHOLDS = ROOT / "scripts" / "spike" / "llm_cost_thresholds.json"

_spec = importlib.util.spec_from_file_location("llm_cost", SCRIPT)
llm_cost = importlib.util.module_from_spec(_spec)
sys.modules["llm_cost"] = llm_cost
_spec.loader.exec_module(llm_cost)

# Заглушка sitecustomize: любое обращение к сети роняет процесс.
NO_NET = '''
import socket


def _blocked(*args, **kwargs):
    raise RuntimeError("сеть запрещена: --check не должен ходить в сеть")


socket.socket = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
'''


def _artifact(cost_per_call: float = 0.01, within_budget: bool = True, variant: str = "A") -> dict:
    """Вымышленный артефакт замера: цена одного вызова и единицы из методики."""
    scenarios = []
    for sid, calls in (("dialog", 25), ("document", 1), ("forecast", 7)):
        scenarios.append(
            {
                "id": sid,
                "runs": 3,
                "cards": ["A", "B", "C", "D", "E"],
                "calls_per_card": calls,
                "usage": {
                    "input_tokens": {"median": 3500, "p90": 4000},
                    "output_tokens": {"median": 800, "p90": 1000},
                },
                "cost_rub": {"median": cost_per_call, "p90": cost_per_call},
            }
        )
    return {
        "schema_version": 1,
        "measured_at": "2026-11-26",
        "provider": "провайдер-заглушка",
        "model": "модель-заглушка",
        "pricing": {
            "input_usd_per_1m": 1.0,
            "output_usd_per_1m": 5.0,
            "usd_rub_rate": 83.59,
            "intermediary_markup": 1.5,
            "priced_on": "2026-11-26",
        },
        "scenarios": scenarios,
        "verdict": {
            "within_budget": within_budget,
            "threshold_variant": variant,
            "notes": "",
        },
    }


def _limit(variant: str, scenario: str, metric: str) -> float:
    data = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
    return data["variants"][variant]["thresholds"][scenario][metric]


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """Копия репозитория: боевая схема и пороги, артефакт — фикстура."""
    (tmp_path / "scripts" / "spike").mkdir(parents=True)
    (tmp_path / "docs" / "current" / "spike").mkdir(parents=True)
    shutil.copy(SCHEMA, tmp_path / "scripts" / "spike" / "llm_cost.schema.json")
    shutil.copy(THRESHOLDS, tmp_path / "scripts" / "spike" / "llm_cost_thresholds.json")
    return tmp_path


def _write_artifact(root: pathlib.Path, artifact: dict) -> pathlib.Path:
    path = root / "docs" / "current" / "spike" / "llm_cost.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run(root: pathlib.Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--root", str(root)],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
        check=False,
    )


# ── критерий (а): артефакта нет ───────────────────────────────────────────────


def test_missing_artifact_fails_with_clear_message(repo):
    result = _run(repo)
    assert result.returncode == 1
    assert "llm_cost.json" in result.stdout
    assert "FAIL" in result.stdout


# ── критерий (б): артефакт невалиден по схеме ────────────────────────────────


def test_invalid_artifact_reports_field(repo):
    artifact = _artifact()
    artifact["provider"] = ""
    _write_artifact(repo, artifact)
    result = _run(repo)
    assert result.returncode == 1
    assert "provider" in result.stdout


def test_missing_required_field_is_reported(repo):
    artifact = _artifact()
    del artifact["measured_at"]
    _write_artifact(repo, artifact)
    result = _run(repo)
    assert result.returncode == 1
    assert "measured_at" in result.stdout


def test_extra_field_is_reported(repo):
    artifact = _artifact()
    artifact["surprise"] = 1
    _write_artifact(repo, artifact)
    result = _run(repo)
    assert result.returncode == 1
    assert "surprise" in result.stdout


# По одному нарушению на каждое ограничение боевой схемы.
INVALID_CASES = [
    ("const", lambda a: a.__setitem__("schema_version", 2), "schema_version"),
    ("type", lambda a: a.__setitem__("schema_version", "1"), "schema_version"),
    ("pattern", lambda a: a.__setitem__("measured_at", "26.11.2026"), "measured_at"),
    ("minLength", lambda a: a.__setitem__("provider", ""), "provider"),
    (
        "exclusiveMinimum",
        lambda a: a["pricing"].__setitem__("input_usd_per_1m", 0),
        "input_usd_per_1m",
    ),
    (
        "enum",
        lambda a: a["verdict"].__setitem__("threshold_variant", "C"),
        "threshold_variant",
    ),
    ("integer", lambda a: a["scenarios"][0].__setitem__("runs", 1.5), "runs"),
    (
        "minimum",
        lambda a: a["scenarios"][0]["cost_rub"].__setitem__("median", -1),
        "median",
    ),
    (
        "$ref",
        lambda a: a["scenarios"][0]["usage"]["input_tokens"].pop("p90"),
        "p90",
    ),
    ("minItems", lambda a: a.__setitem__("scenarios", a["scenarios"][:2]), "scenarios"),
    (
        "maxItems",
        lambda a: a.__setitem__("scenarios", a["scenarios"] + [a["scenarios"][0]]),
        "scenarios",
    ),
]


@pytest.mark.parametrize(
    ("case", "mutate", "needle"), INVALID_CASES, ids=[case[0] for case in INVALID_CASES]
)
def test_schema_constraints_are_enforced(repo, case, mutate, needle):
    artifact = _artifact()
    mutate(artifact)
    _write_artifact(repo, artifact)
    result = _run(repo)
    assert result.returncode == 1, result.stdout
    assert needle in result.stdout


def test_validator_knows_every_keyword_of_the_real_schema():
    used: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                used.add(key)
                if key in ("properties", "$defs") and isinstance(value, dict):
                    for sub in value.values():
                        walk(sub)
                elif key == "items":
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(json.loads(SCHEMA.read_text(encoding="utf-8")))
    known = llm_cost.CONSTRAINT_KEYWORDS | llm_cost.ANNOTATION_KEYWORDS
    assert used <= known, f"валидатор не знает ключевые слова схемы: {sorted(used - known)}"


def test_broken_json_is_reported(repo):
    path = repo / "docs" / "current" / "spike" / "llm_cost.json"
    path.write_text("{не json", encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 1
    assert "JSON" in result.stdout


# ── критерий (в): превышение порога ──────────────────────────────────────────


def test_over_budget_reports_value_and_threshold(repo):
    _write_artifact(repo, _artifact(cost_per_call=100.0, within_budget=False))
    result = _run(repo)
    assert result.returncode == 1
    limit = _limit("A", "dialog", "max_rub_per_question")
    assert "100" in result.stdout
    assert llm_cost._fmt(limit) in result.stdout
    assert "FAIL" in result.stdout


def test_verdict_claim_must_agree_with_calculation(repo):
    _write_artifact(repo, _artifact(cost_per_call=100.0, within_budget=True))
    result = _run(repo)
    assert result.returncode == 1
    assert "within_budget" in result.stdout


# ── критерий (г): артефакт в бюджете ─────────────────────────────────────────


def test_within_budget_passes(repo):
    _write_artifact(repo, _artifact(cost_per_call=0.01))
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout
    assert "FAIL" not in result.stdout


def test_variant_b_from_artifact_is_used(repo):
    _write_artifact(repo, _artifact(cost_per_call=0.01, variant="B"))
    result = _run(repo)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "вариант B" in result.stdout
    # порог документа в варианте Б не пересчитан (null) — сценарий пропускается
    assert "не пересчитан" in result.stdout


# ── критерий (д): пороги берутся из файла ────────────────────────────────────


def test_thresholds_are_taken_from_file(repo):
    _write_artifact(repo, _artifact(cost_per_call=0.01))
    path = repo / "scripts" / "spike" / "llm_cost_thresholds.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["variants"]["A"]["thresholds"]["dialog"]["max_rub_per_question"] = 0.001
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 1
    assert "0.001" in result.stdout


def test_scenario_set_must_be_complete(repo):
    artifact = _artifact()
    artifact["scenarios"][2] = dict(artifact["scenarios"][0])
    _write_artifact(repo, artifact)
    result = _run(repo)
    assert result.returncode == 1
    assert "сценари" in result.stdout


def test_calls_per_card_must_match_methodology(repo):
    artifact = _artifact()
    artifact["scenarios"][0]["calls_per_card"] = 20
    _write_artifact(repo, artifact)
    result = _run(repo)
    assert result.returncode == 1
    assert "calls_per_card" in result.stdout


# ── критерий (з): без ключей и без сети ─────────────────────────────────────


def test_check_needs_no_key_and_no_network(repo, tmp_path):
    _write_artifact(repo, _artifact(cost_per_call=0.01))
    site_dir = tmp_path / "nonet"
    site_dir.mkdir()
    (site_dir / "sitecustomize.py").write_text(NO_NET, encoding="utf-8")
    result = _run(repo, env={"PYTHONPATH": str(site_dir)})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "сеть запрещена" not in result.stderr


def test_check_runs_with_empty_environment(repo):
    _write_artifact(repo, _artifact(cost_per_call=0.01))
    result = _run(repo, env={})
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_reads_neither_environment_nor_network():
    source = SCRIPT.read_text(encoding="utf-8")
    for banned in ("environ", "getenv", "socket", "urllib", "requests", "httpx", "LUNORA_"):
        assert banned not in source, f"чекер не должен касаться {banned}"


# ── критерий (ж): цель make slice-check-s3b ──────────────────────────────────


@pytest.mark.skipif(shutil.which("make") is None, reason="нет make")
def test_make_target_calls_the_checker():
    result = subprocess.run(
        ["make", "-n", "slice-check-s3b"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "scripts/spike/llm_cost.py --check" in result.stdout


@pytest.mark.skipif(shutil.which("make") is None, reason="нет make")
def test_accumulated_slice_check_does_not_include_s3b():
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if line.startswith("slice-check:"))
    assert "slice-check-s3b" not in line


@pytest.mark.skipif(shutil.which("make") is None, reason="нет make")
def test_make_target_fails_when_budget_is_exceeded(tmp_path):
    root = _make_sandbox(tmp_path, _artifact(cost_per_call=100.0, within_budget=False))
    result = _make(root)
    assert result.returncode != 0
    assert "llm_cost" in result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("make") is None, reason="нет make")
def test_make_target_passes_when_budget_is_met(tmp_path):
    root = _make_sandbox(tmp_path, _artifact(cost_per_call=0.01))
    result = _make(root)
    assert result.returncode == 0, result.stdout + result.stderr


def _make_sandbox(tmp_path: pathlib.Path, artifact: dict) -> pathlib.Path:
    """Песочница make: настоящий Makefile и скрипт, артефакт — фикстура."""
    shutil.copy(ROOT / "Makefile", tmp_path / "Makefile")
    (tmp_path / "scripts" / "spike").mkdir(parents=True)
    shutil.copy(SCRIPT, tmp_path / "scripts" / "spike" / "llm_cost.py")
    shutil.copy(SCHEMA, tmp_path / "scripts" / "spike" / "llm_cost.schema.json")
    shutil.copy(THRESHOLDS, tmp_path / "scripts" / "spike" / "llm_cost_thresholds.json")
    (tmp_path / "docs" / "current" / "spike").mkdir(parents=True)
    _write_artifact(tmp_path, artifact)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_llm_cost.py").write_text(
        "def test_stub():\n    assert True\n", encoding="utf-8"
    )
    return tmp_path


def _make(root: pathlib.Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = f"{pathlib.Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(
        ["make", "-C", str(root), "slice-check-s3b"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
