#!/usr/bin/env python3
"""horizons_fetch — снимок 10 контрольных дат из JPL Horizons в фикстуру (G17-S1, GE-01/GE-02).

Единственный сетевой шаг сверки с Horizons: запускается один раз вручную, результат
коммитится в tests/fixtures/horizons/control_dates.json, тесты читают его офлайн.

Что снимаем:
  * геоцентрическая видимая эклиптическая долгота/широта даты (QUANTITIES=31) — 10 тел;
  * местное видимое звёздное время (QUANTITIES=7) на точке карты A (Волгоград) → RAMC.
Время запрашивается в TT (TIME_TYPE=TT), чтобы не зависеть от прогноза ΔT/UT1 Horizons.

Запуск:  python scripts/spike/horizons_fetch.py [--out PATH]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "fixtures" / "horizons" / "control_dates.json"
API = "https://ssd.jpl.nasa.gov/api/horizons.api"

# 10 контрольных моментов 1901–2099; карты A–D из ENGINE-SPEC §0.5. Шкала — по правилу §2.2
# (до 1972 гражданское время минус пояс = UT1, с 1972 — UTC); jd_tt считает Skyfield (builtin).
CONTROL = [
    ("1901-03-15 06:00 UT1", "ut1", (1901, 3, 15, 6, 0)),
    ("1930-06-15 09:00 UT1 (GE-03, Москва 1930)", "ut1", (1930, 6, 15, 9, 0)),
    ("1950-06-15 06:00 UT1 (GE-03, Москва 1950)", "ut1", (1950, 6, 15, 6, 0)),
    ("1962-08-09 03:15 UT1 (карта D)", "ut1", (1962, 8, 9, 3, 15)),
    ("1984-02-04 11:00 UTC (карта A)", "utc", (1984, 2, 4, 11, 0)),
    ("1987-06-15 08:00 UTC (карта B)", "utc", (1987, 6, 15, 8, 0)),
    ("1990-12-22 20:40 UTC (карта C)", "utc", (1990, 12, 22, 20, 40)),
    ("2000-01-01 12:00 TT (J2000.0)", "tt", (2000, 1, 1, 12, 0)),
    ("2026-02-03 20:02 UTC (ли-чунь 2026)", "utc", (2026, 2, 3, 20, 2)),
    ("2099-07-01 00:00 TT", "tt", (2099, 7, 1, 0, 0)),
]


def control_jd_tt() -> list[float]:
    from skyfield.api import load

    ts = load.timescale(builtin=True)
    return [round(getattr(ts, scale)(*ymdhm).tt, 9) for _, scale, ymdhm in CONTROL]


# Horizons COMMAND: Солнце, Луна, Меркурий, Венера — центры тел; Марс…Плутон — барицентры (§2.3).
BODIES = {
    "sun": "10",
    "moon": "301",
    "mercury": "199",
    "venus": "299",
    "mars": "4",
    "jupiter": "5",
    "saturn": "6",
    "uranus": "7",
    "neptune": "8",
    "pluto": "9",
}

SITE_A = {"name": "Волгоград (карта A)", "lat": 48.7080, "lon": 44.5133, "alt_km": 0.0}


def _query(params: dict[str, str]) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 — фиксированный хост JPL
        data = json.load(resp)
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


def _rows(result: str) -> list[list[str]]:
    body = result.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    return [[c.strip() for c in line.split(",")] for line in body.strip().splitlines()]


def _source(result: str) -> str:
    m = re.search(r"\{source:\s*([^}]+)\}", result)
    return m.group(1).strip() if m else "unknown"


def _base(command: str) -> dict[str, str]:
    return {
        "format": "json",
        "COMMAND": f"'{command}'",
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "OBSERVER",
        "TLIST": " ".join(f"'{jd:.9f}'" for jd in control_jd_tt()),
        "TLIST_TYPE": "JD",
        "TIME_TYPE": "TT",
        "TIME_DIGITS": "FRACSEC",
        "ANG_FORMAT": "DEG",
        "EXTRA_PREC": "YES",
        "CSV_FORMAT": "YES",
    }


def fetch() -> dict:
    out: dict = {
        "what": "JPL Horizons: 10 контрольных дат G17-S1 (GE-01, GE-02), снимок для офлайн-тестов",
        "retrieved": dt.date.today().isoformat(),
        "api": API,
        "time_scale": "TT",
        "quantities": {
            "31": "ObsEcLon/ObsEcLat — геоцентр, видимое место, эклиптика даты",
            "7": "L_Ap_Sid_Time — местное видимое звёздное время, часы",
        },
        "dates": [
            {"label": label, "scale": scale, "civil": list(ymdhm), "jd_tt": jd}
            for (label, scale, ymdhm), jd in zip(CONTROL, control_jd_tt(), strict=True)
        ],
        "bodies": {},
        "site_a": dict(SITE_A),
    }
    for name, cmd in BODIES.items():
        params = _base(cmd) | {"CENTER": "'500@399'", "QUANTITIES": "'31'"}
        data = _query(params)
        rows = _rows(data["result"])
        assert len(rows) == len(CONTROL), (name, len(rows))
        out["bodies"][name] = {
            "horizons_command": cmd,
            "source": _source(data["result"]),
            "lon": [float(r[-3]) for r in rows],
            "lat": [float(r[-2]) for r in rows],
        }
        out["signature"] = data["signature"]
    params = _base("10") | {
        "CENTER": "'coord@399'",
        "COORD_TYPE": "GEODETIC",
        "SITE_COORD": f"'{SITE_A['lon']},{SITE_A['lat']},{SITE_A['alt_km']}'",
        "QUANTITIES": "'7'",
    }
    data = _query(params)
    rows = _rows(data["result"])
    out["site_a"]["last_hours"] = [float(r[3]) for r in rows]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    args = ap.parse_args()
    data = fetch()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"horizons_fetch: {args.out.relative_to(ROOT)} — {len(CONTROL)} дат × {len(BODIES)} тел")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
