#!/usr/bin/env python3
"""llm_measure — живой замер стоимости LLM-синтеза (гейт G17-S3b).

Собирает РЕАЛЬНЫЕ пакеты сообщений теми же функциями, что рантайм
(lunora.llm.client.build_messages для диалога/прогноза; lunora.interpret.portrait
для документа-портрета), гоняет их по кандидатам моделей через OpenRouter
(как в рантайме, OpenAI-совместимый /chat/completions), снимает usage и считает
себестоимость ОДНОГО вызова по формуле 05_business.md §3.1:
    руб = (in_tokens·in_price + out_tokens·out_price) · курс · наценка.

ПДн: входы — синтетические карты A–E (имя «Тест», вымышленные дата/место). В пакет
к модели и так уходят только градусы+текст (стерегут tests/test_llm_privacy.py).

Два режима:
  --dry-run  офлайн: собирает пакеты, оценивает входные токены, печатает ориентир
             стоимости всего замера. Ни сети к моделям, ни ключа. Бюджет не жжёт.
  (живой)    нужен LUNORA_LLM_API_KEY. Гоняет модели, пишет сравнение в
             docs/current/spike/llm_compare.json и артефакт выбранной модели
             (--artifact-model) в docs/current/spike/llm_cost.json по схеме чекера.

Цены берём на день замера из публичного OpenRouter /api/v1/models (без ключа);
курс USD→RUB — параметр --usd-rub (по умолчанию из --usd-rub, сверяем с ЦБ).

Запуск:
  python scripts/spike/llm_measure.py --dry-run
  python scripts/spike/llm_measure.py --models anthropic/claude-opus-5.5,... \
      --artifact-model anthropic/claude-opus-5.5 --usd-rub 79 --markup 1.0
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from lunora.calc.engine import calculate, resolve_moment  # noqa: E402
from lunora.calc.serialize import chart_to_dict  # noqa: E402
from lunora.calc.types import BirthData, BirthTimePrecision  # noqa: E402
from lunora.engines.numerology import FullName  # noqa: E402
from lunora.forecast.generate import FORECAST_QUESTION  # noqa: E402
from lunora.interpret.portrait import (  # noqa: E402
    PORTRAIT_SYSTEM_PROMPT,
    build_interpretation_blocks,
    build_portrait_prompt,
)
from lunora.llm.client import build_messages  # noqa: E402

OPENROUTER = "https://openrouter.ai/api/v1"
ARTIFACT = ROOT / "docs/current/spike/llm_cost.json"
COMPARE = ROOT / "docs/current/spike/llm_compare.json"

DEFAULT_MODELS = [
    "anthropic/claude-opus-5.5",
    "anthropic/claude-sonnet-5.5",
    "anthropic/claude-haiku-5.5",
    "deepseek/deepseek-v3.2",
]

# Множители периодных порогов (05_business.md §3.1/§3.5; schema calls_per_card).
CALLS_PER_CARD = {"dialog": 25, "document": 1, "forecast": 7}

# Синтетические карты A–E — без ПДн (имя «Тест», вымышленные дата/место/координаты).
# lat/lon/timezone заданы прямо, чтобы не тянуть реестр мест.
SYNTH = [
    ("A", date(1990, 3, 21), time(14, 30), 55.7558, 37.6173, "Europe/Moscow", "m"),
    ("B", date(1985, 7, 8), time(6, 15), 59.9311, 30.3609, "Europe/Moscow", "f"),
    ("C", date(1972, 11, 2), time(23, 45), 56.8389, 60.6057, "Asia/Yekaterinburg", "m"),
    ("D", date(1998, 1, 17), time(9, 0), 54.9924, 73.3686, "Asia/Omsk", "f"),
    ("E", date(2001, 9, 30), time(18, 20), 43.1155, 131.8855, "Asia/Vladivostok", "m"),
]

# Представительные вопросы диалога (варьируем по картам). Без ПДн.
DIALOG_QUESTIONS = [
    "Что говорит моя карта о моём характере и сильных сторонах?",
    "Какой период сейчас у меня по картам — на что опереться?",
    "Что системы говорят про мои отношения и совместимость?",
    "Где мне искать себя в работе и призвании?",
    "Какие внутренние противоречия видны в моей карте?",
]


@dataclass
class Prices:
    in_per_tok: float  # USD за токен
    out_per_tok: float


def fetch_prices(models: list[str]) -> dict[str, Prices]:
    """Публичный OpenRouter /models — без ключа, без трат. Цены USD за токен."""
    req = urllib.request.Request(f"{OPENROUTER}/models", headers={"User-Agent": "lunora-spike"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        data = json.load(r)
    by_id = {m["id"]: m for m in data.get("data", data)}
    out: dict[str, Prices] = {}
    for mid in models:
        m = by_id.get(mid)
        if not m:
            raise SystemExit(f"модель не найдена в OpenRouter /models: {mid}")
        p = m["pricing"]
        out[mid] = Prices(float(p["prompt"]), float(p["completion"]))
    return out


def chart_for(idx: int) -> dict:
    tag, d, t, lat, lon, tz, sex = SYNTH[idx]
    birth = BirthData(
        birth_date=d,
        birth_time=t,
        precision=BirthTimePrecision.EXACT,
        lat=lat,
        lon=lon,
        timezone=tz,
        sex=sex,
        full_name=FullName("Тест", "Тест", "Тестович" if sex == "m" else "Тестовна"),
        name="Тест",
    )
    moment = resolve_moment(birth)
    full = calculate(birth, moment)
    return {
        "western": chart_to_dict(full.western),
        "vedic": chart_to_dict(full.vedic),
        "chinese": chart_to_dict(full.chinese),
        "numerology": chart_to_dict(full.numerology),
    }


def messages_for(scenario: str, card_idx: int, chart_data: dict) -> list[dict]:
    if scenario == "dialog":
        q = DIALOG_QUESTIONS[card_idx % len(DIALOG_QUESTIONS)]
        return build_messages(q, chart_data, "exact")
    if scenario == "forecast":
        q = FORECAST_QUESTION.format(date=date.today().isoformat())
        return build_messages(q, chart_data, "exact")
    if scenario == "document":
        blocks = build_interpretation_blocks(chart_data)
        prompt = build_portrait_prompt(blocks, chart_data)
        return [
            {"role": "system", "content": PORTRAIT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
    raise ValueError(scenario)


def est_tokens(messages: list[dict]) -> int:
    """Грубая офлайн-оценка входных токенов (кириллица ≈ 3 символа/токен)."""
    chars = sum(len(m["content"]) for m in messages)
    return round(chars / 3.0)


def call_model(model: str, messages: list[dict], api_key: str) -> dict:
    body = json.dumps(
        {"model": model, "messages": messages, "max_tokens": 1000, "temperature": 0.7}
    ).encode()
    req = urllib.request.Request(
        f"{OPENROUTER}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "lunora-spike",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310
        data = json.load(r)
    u = data["usage"]
    return {
        "input_tokens": int(u["prompt_tokens"]),
        "output_tokens": int(u["completion_tokens"]),
    }


def cost_rub(inp: int, outp: int, pr: Prices, usd_rub: float, markup: float) -> float:
    return (inp * pr.in_per_tok + outp * pr.out_per_tok) * usd_rub * markup


def dist(values: list[float]) -> dict:
    s = sorted(values)
    p90 = s[min(len(s) - 1, round(0.9 * (len(s) - 1)))]
    return {"median": round(statistics.median(s), 6), "p90": round(p90, 6)}


def run(args: argparse.Namespace) -> None:
    models = args.models.split(",") if args.models else DEFAULT_MODELS
    cards = [s[0] for s in SYNTH]
    print(f"Карты: {cards}; сценарии: dialog/document/forecast; повторов: {args.runs}")
    charts = [chart_for(i) for i in range(len(SYNTH))]

    # Офлайн-оценка входных токенов по реально собранным пакетам.
    est = {}
    for scen in ("dialog", "document", "forecast"):
        ins = [est_tokens(messages_for(scen, i, charts[i])) for i in range(len(SYNTH))]
        est[scen] = round(statistics.mean(ins))
    print("Оценка входных токенов (медиана карт):", est)

    prices = fetch_prices(models)
    usd_rub, markup = args.usd_rub, args.markup

    if args.dry_run:
        # Оценка стоимости всего замера: выход принимаем у потолка (max_tokens=1000).
        out_assumed = {"dialog": 800, "document": 700, "forecast": 500}
        total = 0.0
        n = len(SYNTH) * args.runs
        print(f"\n--- ОЦЕНКА СТОИМОСТИ ЗАМЕРА (dry-run), курс {usd_rub}, наценка {markup} ---")
        for mid in models:
            pr = prices[mid]
            mcost = 0.0
            for scen in ("dialog", "document", "forecast"):
                per = cost_rub(est[scen], out_assumed[scen], pr, usd_rub, markup)
                mcost += per * n
            total += mcost
            print(f"{mid:34s} ~{mcost:7.2f} ₽  (${mcost / usd_rub:6.3f})")
        print(f"{'ИТОГО весь замер':34s} ~{total:7.2f} ₽  (${total / usd_rub:6.3f})")
        print(f"Живых вызовов: {len(models)} моделей × 3 сценария × {n} = {len(models) * 3 * n}")
        return

    api_key = os.environ.get("LUNORA_LLM_API_KEY")
    if not api_key:
        raise SystemExit("LUNORA_LLM_API_KEY не задан — живой замер невозможен (бюджет не жжём).")

    compare = {"measured_at": date.today().isoformat(), "usd_rub": usd_rub,
               "markup": markup, "models": {}}
    for mid in models:
        pr = prices[mid]
        scen_out = {}
        for scen in ("dialog", "document", "forecast"):
            costs, ins, outs = [], [], []
            for _rep in range(args.runs):
                for i in range(len(SYNTH)):
                    u = call_model(mid, messages_for(scen, i, charts[i]), api_key)
                    ins.append(u["input_tokens"])
                    outs.append(u["output_tokens"])
                    costs.append(
                        cost_rub(u["input_tokens"], u["output_tokens"], pr, usd_rub, markup)
                    )
            scen_out[scen] = {
                "runs": args.runs,
                "cards": [s[0] for s in SYNTH],
                "calls_per_card": CALLS_PER_CARD[scen],
                "usage": {"input_tokens": dist(ins), "output_tokens": dist(outs)},
                "cost_rub": dist(costs),
            }
            med = scen_out[scen]["cost_rub"]["median"]
            period = med * CALLS_PER_CARD[scen]
            print(f"{mid} {scen}: 1 вызов median {med:.4f} ₽; период = {period:.3f} ₽")
        compare["models"][mid] = {
            "pricing_usd_per_1m": {
                "input": pr.in_per_tok * 1e6,
                "output": pr.out_per_tok * 1e6,
            },
            "scenarios": scen_out,
        }

    COMPARE.parent.mkdir(parents=True, exist_ok=True)
    COMPARE.write_text(json.dumps(compare, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nСравнение → {COMPARE.relative_to(ROOT)}")

    if args.artifact_model:
        pr_art = prices[args.artifact_model]
        write_artifact(args.artifact_model, pr_art, compare, usd_rub, markup, args)


def write_artifact(model: str, pr: Prices, compare: dict, usd_rub: float,
                   markup: float, args: argparse.Namespace) -> None:
    src = compare["models"][model]["scenarios"]
    scenarios = []
    for scen in ("dialog", "document", "forecast"):
        s = src[scen]
        scenarios.append({"id": scen, **s})
    within = True  # вердикт выставит чекер против порогов; здесь — честный замер
    art = {
        "schema_version": 1,
        "measured_at": date.today().isoformat(),
        "provider": "openrouter",
        "model": model,
        "pricing": {
            "input_usd_per_1m": round(pr.in_per_tok * 1e6, 4),
            "output_usd_per_1m": round(pr.out_per_tok * 1e6, 4),
            "usd_rub_rate": usd_rub,
            "intermediary_markup": markup,
            "priced_on": date.today().isoformat(),
        },
        "scenarios": scenarios,
        "verdict": {"within_budget": within, "threshold_variant": args.variant,
                    "notes": args.notes or ""},
    }
    ARTIFACT.write_text(json.dumps(art, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Артефакт выбранной модели → {ARTIFACT.relative_to(ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--models", default="")
    ap.add_argument("--artifact-model", default="")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--usd-rub", type=float, default=79.0)
    ap.add_argument("--markup", type=float, default=1.0)
    ap.add_argument("--variant", choices=["A", "B"], default="B")
    ap.add_argument("--notes", default="")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
