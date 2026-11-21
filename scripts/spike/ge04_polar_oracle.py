#!/usr/bin/env python3
"""ge04_polar_oracle — golden GE-04 (полярное правило ASC, синтетика 78°) из оракула SE.

GE-04 (карточка G17-S1): эталон — тестовый оракул Swiss Ephemeris, а не ручной съём.
Сетка: 22.12.1990 (дата карты C), каждые 2 ч UTC, φ = +78° и −78°, λ = 15° E.
Для каждой точки SE 2.10.03 (FLG_JPLEPH, DE440) даёт ASC и MC через houses_ex от UT1.
Пишет tests/golden/ephemeris/ge04-polar-78.yaml и доказательство
tests/golden/evidence/ge04-polar-78-oracle.md (с пометкой, где формула без полярного
правила перевернула бы ASC на 180° — кейс должен такие моменты содержать).

Офлайн, нужен make setup-oracle. Запуск:  python scripts/spike/ge04_polar_oracle.py
"""

from __future__ import annotations

import math
import pathlib
from datetime import UTC, date, datetime

import swisseph as swe
import yaml

from lunora.calc import _ephem as eph

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASE = ROOT / "tests" / "golden" / "ephemeris" / "ge04-polar-78.yaml"
EVIDENCE = ROOT / "tests" / "golden" / "evidence" / "ge04-polar-78-oracle.md"
LATS = (78.0, -78.0)
LON = 15.0
HOURS = range(0, 24, 2)


def _naive_asc(theta: float, eps: float, lat: float) -> float:
    th, e, phi = math.radians(theta), math.radians(eps), math.radians(lat)
    x = -(math.sin(th) * math.cos(e) + math.tan(phi) * math.sin(e))
    return math.degrees(math.atan2(math.cos(th), x)) % 360.0


def main() -> int:
    swe.set_ephe_path(str(ROOT / "data" / "vendor" / "jpl-oracle"))
    swe.set_jpl_file("linux_p1550p2650.440")
    cases, rows, flips = [], [], 0
    for lat in LATS:
        tag = "N" if lat > 0 else "S"
        for h in HOURS:
            moment = datetime(1990, 12, 22, h, 0, tzinfo=UTC)
            t = eph.instant(moment)
            _, ascmc = swe.houses_ex(t.ut1, lat, LON, b"W")
            ours = eph.angles(t, lat, LON)
            naive = _naive_asc(ours.ramc, ours.obliquity, lat)
            flip = abs((naive - ascmc[0] + 180) % 360 - 180) > 90
            flips += flip
            rows.append((tag, h, lat, ascmc[0], ascmc[1], flip))
            cases.append(
                {
                    "id": f"GE-04-polar-78{tag}-{h:02d}h",
                    "layer": "ephemeris",
                    "status": "active",
                    "case": "GE-04 — полярное правило ASC, без переворота на 180°",
                    "input": {
                        "place_id": f"synthetic:lat{lat:+.0f}-lon{LON:+.0f}",
                        "local_date": moment.date().isoformat(),
                        "local_time": f"{h:02d}:00",
                        "utc_offset": "+00:00",
                        "utc": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "lat": lat,
                        "lon": LON,
                    },
                    "reference": {
                        "source": "Swiss Ephemeris 2.10.03 (тестовый оракул)",
                        "settings": {
                            "ephemeris": "DE440 linux_p1550p2650.440, FLG_JPLEPH",
                            "call": "swe.houses_ex(jd_ut1, lat, lon, b'W')",
                            "time": "UT1 = Skyfield builtin от UTC (как рантайм)",
                        },
                        "captured_at": date.today().isoformat(),
                        "captured_by": "Claude (scripts/spike/ge04_polar_oracle.py)",
                        "evidence_file": "evidence/ge04-polar-78-oracle.md",
                    },
                    "versions": {
                        "tz": "2026f",
                        "ephemeris": "DE440s (SHA-256 c1c7feea…49f2), Skyfield 1.55",
                        "reference_service": f"pyswisseph 2.10.3.2 / SE {swe.version}",
                    },
                    "notes": (
                        "Без полярного правила ASC здесь перевернулся бы на 180°."
                        if flip
                        else "Контрольная точка сетки: переворота не было бы и без правила."
                    ),
                    "expected": [
                        {
                            "path": "angles.asc",
                            "value": round(ascmc[0], 9),
                            "tolerance": 0.05,
                            "unit": "arcsec",
                        },
                        {
                            "path": "angles.mc",
                            "value": round(ascmc[1], 9),
                            "tolerance": 0.05,
                            "unit": "arcsec",
                        },
                    ],
                }
            )
    assert flips, "в сетке нет ни одного момента, где правило что-то меняет"
    header = (
        "# GE-04: полярное правило ASC (синтетика ±78°) — сгенерировано из оракула SE.\n"
        "# Не править руками: python scripts/spike/ge04_polar_oracle.py\n"
    )
    CASE.write_text(
        header + yaml.safe_dump_all(cases, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    lines = [
        "# Доказательство GE-04: полярное правило ASC, синтетика ±78°",
        "",
        f"Сгенерировано `scripts/spike/ge04_polar_oracle.py` {date.today().isoformat()}. "
        f"Оракул — Swiss Ephemeris {swe.version} (pyswisseph 2.10.3.2) в режиме `FLG_JPLEPH` "
        "на DE440 (`linux_p1550p2650.440`, SHA-256 в `data/vendor/MANIFEST.yaml`), вызов "
        "`houses_ex(jd_ut1, φ, 15°, 'W')`. Момент — 22.12.1990 (дата карты C), сетка 2 ч UTC.",
        "",
        "«Переворот без правила» — формула ASC без строки «если (ASC − MC) mod 360° ≥ 180° → "
        "+180°» (ENGINE-SPEC §2.4) дала бы значение, отличающееся от оракула на 180°.",
        "",
        f"Моментов с переворотом без правила: **{flips} из {len(rows)}**.",
        "",
        "| φ | UTC | ASC оракула, ° | MC оракула, ° | Переворот без правила |",
        "| --- | --- | --- | --- | --- |",
    ]
    for _tag, h, lat, asc, mc, flip in rows:
        lines.append(
            f"| {lat:+.0f}° | {h:02d}:00 | {asc:.9f} | {mc:.9f} | {'да' if flip else 'нет'} |"
        )
    EVIDENCE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"ge04_polar_oracle: {len(cases)} кейсов, переворотов без правила — {flips}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
