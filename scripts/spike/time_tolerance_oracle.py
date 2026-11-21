#!/usr/bin/env python3
"""time_tolerance_oracle — golden «Допуск времени» (ARCHITECTURE §4.5) из оракула SE.

Карточка G17-S1, строка «Допуск времени»: карта A с ± 30 мин, ± 3 ч и «не знаю» →
`stability` = stable / range / undetermined. Сигнал — знак асцендента (самый чувствительный
к времени дискретный сигнал). Эталон множества знаков на интервале снимается независимо
от нашего кода: SE 2.10.03 (FLG_JPLEPH, DE440) считает ASC на мелкой сетке каждой гипотезы
смещения `ResolvedMoment`; из множества знаков выводится тег §4.5. Тест сверяет
`lunora.calc.stability.stability` с этим эталоном.

Четвёртая строка — карта A в 04:00 местного (UTC+4) с ± 30 мин: окно ложится на границу
знака асцендента, поэтому значений ровно два → `range` (без неё ветка range не покрыта).

Пишет tests/golden/time_tolerance/card-a-tolerance.yaml и
tests/golden/evidence/card-a-time-tolerance-oracle.md. Офлайн, нужен make setup-oracle.
Запуск:  python scripts/spike/time_tolerance_oracle.py
"""

from __future__ import annotations

import pathlib
from datetime import UTC, date, datetime, time, timedelta

import swisseph as swe
import yaml

from lunora.calc import _ephem as eph
from lunora.timeplace import resolve

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASE = ROOT / "tests" / "golden" / "time_tolerance" / "card-a-tolerance.yaml"
EVIDENCE = ROOT / "tests" / "golden" / "evidence" / "card-a-time-tolerance-oracle.md"
EVIDENCE_REL = "evidence/card-a-time-tolerance-oracle.md"

PLACE = "geonames:472757"  # Волгоград
LAT, LON = 48.71378, 44.4976
ZONE = "Europe/Volgograd"
SAMPLE = timedelta(minutes=2)  # мелкая сетка снятия эталона (не рантайм-поиск корня)

# (id, местное время или None, допуск в минутах, комментарий)
INPUTS = [
    ("TT-A-exact", time(15, 0), 0, "точно — t ± 0"),
    ("TT-A-pm30", time(15, 0), 30, "± 30 мин"),
    ("TT-A-pm180", time(15, 0), 180, "± 3 часа"),
    ("TT-A-unknown", None, None, "«не знаю» — целые сутки, опора на полдень"),
    ("TT-A-boundary-pm30", time(4, 0), 30, "± 30 мин на границе знака асцендента (range)"),
]


def _oracle_asc_sign(moment: datetime) -> int:
    t = eph.instant(moment)
    _, ascmc = swe.houses_ex(t.ut1 if t.ut1 else t.tt, LAT, LON, b"W")
    return int(ascmc[0] // 30.0)


def _sign_set(m) -> list[int]:
    signs: list[int] = []
    for h in m.hypotheses:
        start = h.utc_start if h.utc_start.tzinfo else h.utc_start.replace(tzinfo=UTC)
        end = h.utc_end if h.utc_end.tzinfo else h.utc_end.replace(tzinfo=UTC)
        t = start
        while t <= end:
            s = _oracle_asc_sign(t)
            if s not in signs:
                signs.append(s)
            t += SAMPLE
    return signs


def _tag(signs: list[int]) -> str:
    return "stable" if len(signs) == 1 else "range" if len(signs) == 2 else "undetermined"


def main() -> int:
    swe.set_ephe_path(str(ROOT / "data" / "vendor" / "jpl-oracle"))
    swe.set_jpl_file("linux_p1550p2650.440")
    cases, rows = [], []
    for cid, lt, tol, note in INPUTS:
        m = resolve(date(1984, 2, 4), lt, ZONE, tolerance_minutes=tol, place_id=PLACE)
        signs = sorted(_sign_set(m))
        tag = _tag(signs)
        rows.append((cid, note, tag, signs))
        inp = {"place_id": PLACE, "local_date": "1984-02-04", "lat": LAT, "lon": LON}
        if lt is not None:
            inp["local_time"] = lt.strftime("%H:%M")
            inp["tolerance_minutes"] = tol
        else:
            inp["local_time"] = None
        cases.append(
            {
                "id": cid,
                "layer": "time_tolerance",
                "status": "active",
                "case": f"Допуск времени карты A: {note}",
                "input": inp,
                "reference": {
                    "source": "Swiss Ephemeris 2.10.03 (знаки ASC) + ARCHITECTURE §4.5 (тег)",
                    "settings": {
                        "ephemeris": "DE440 linux_p1550p2650.440, FLG_JPLEPH",
                        "signal": "знак асцендента, houses_ex(jd, φ, λ, 'W')",
                        "sampling": "2 мин по каждому интервалу гипотезы ResolvedMoment",
                        "rule": "stable=1 знак, range=2, undetermined>2 (§4.5)",
                    },
                    "captured_at": date.today().isoformat(),
                    "captured_by": "Claude (scripts/spike/time_tolerance_oracle.py)",
                    "evidence_file": EVIDENCE_REL,
                },
                "versions": {
                    "tz": "2026f",
                    "ephemeris": "DE440s (SHA-256 c1c7feea…49f2), Skyfield 1.55",
                    "reference_service": f"pyswisseph 2.10.3.2 / SE {swe.version}",
                },
                "expected": [
                    {"path": "stability.tag", "value": tag, "exact": True},
                    {"path": "stability.asc_signs", "value": signs, "exact": True},
                ],
            }
        )
    header = (
        "# Допуск времени карты A (ARCHITECTURE §4.5): stable / range / undetermined.\n"
        "# Эталон знаков ASC — оракул SE; тег — правило §4.5. Не править руками:\n"
        "# python scripts/spike/time_tolerance_oracle.py\n"
    )
    CASE.parent.mkdir(parents=True, exist_ok=True)
    CASE.write_text(
        header + yaml.safe_dump_all(cases, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    lines = [
        "# Доказательство «Допуск времени» карты A (§4.5)",
        "",
        f"Сгенерировано `scripts/spike/time_tolerance_oracle.py` {date.today().isoformat()}. "
        f"Эталон множества знаков асцендента — Swiss Ephemeris {swe.version} "
        "(`FLG_JPLEPH`, DE440), "
        "мелкая сетка 2 мин по каждому интервалу гипотезы `ResolvedMoment`; тег стабильности — "
        "правило ARCHITECTURE §4.5 (stable = один знак, range = два, undetermined — больше).",
        "",
        "Карта A — Волгоград (geonames:472757), 04.02.1984, зона `Europe/Volgograd` (UTC+4).",
        "",
        "| Кейс | Допуск | Знаки ASC (0 = Овен) | stability |",
        "| --- | --- | --- | --- |",
    ]
    for cid, note, tag, signs in rows:
        lines.append(f"| {cid} | {note} | {signs} | {tag} |")
    lines += [
        "",
        "Знак асцендента — самый чувствительный к времени сигнал; на нём ветка каждого тега "
        "§4.5 покрыта. Для «range» клок-тайм выбран так, чтобы окно ± 30 мин легло на границу "
        "знака (±30 мин в 15:00 знак не меняют — stable).",
        "",
    ]
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"time_tolerance_oracle: {len(cases)} кейсов")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
