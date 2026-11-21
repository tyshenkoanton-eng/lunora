#!/usr/bin/env python3
"""ephem_diff_report — измеренные максимумы расхождений `_ephem` с Swiss Ephemeris (G17-S1).

Та же выборка и логика, что tests/diff/test_ephem_oracle.py, но вместо assert — максимумы
по каждой величине против допусков §2.11. Пишет docs/current/spike/ephem-oracle-дифф.md.
Офлайн: нужны make setup и make setup-oracle.

Запуск:  python scripts/spike/ephem_diff_report.py [--n 3000]
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "current" / "spike" / "ephem-oracle-дифф.md"


def _load_diff_module():
    spec = importlib.util.spec_from_file_location(
        "ephem_oracle_diff", ROOT / "tests" / "diff" / "test_ephem_oracle.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3000)
    args = ap.parse_args()

    import swisseph as swe

    from lunora.calc import _ephem as eph

    d = _load_diff_module()
    swe.set_ephe_path(str(ROOT / "data" / "vendor" / "jpl-oracle"))
    swe.set_jpl_file("linux_p1550p2650.440")
    n = args.n
    rows: dict[str, float] = {}

    def put(key: str, value: float) -> None:
        rows[key] = max(rows.get(key, 0.0), value)

    ts, _ = d.moments(n, 1900, 2100, salt=1)
    for t in ts:
        for name in eph.BODIES:
            r = d._calc(swe, t, getattr(swe, d.SWE_ID[name]))
            p = eph.body(t, name)
            near = name not in ("sun", "moon") and d._elongation(t, name) < 1.0
            suffix = " (ближе 1° к Солнцу)" if near else ""
            group = "Луна" if name == "moon" else "Солнце–Плутон"
            put(f"долгота: {group}{suffix}", d.arcsec(p.lon, r[0]))
            put(f"скорость, °/сут{suffix}", abs(p.speed - r[3]))

    ts, rnd = d.moments(n, 1900, 2026, salt=2)
    for t in ts:
        lat, lon = rnd.uniform(-66.0, 66.0), rnd.uniform(-180.0, 180.0)
        a = eph.angles(t, lat, lon)
        _, m = swe.houses_ex(t.ut1, lat, lon, b"W")
        put("ASC, MC 1900–2026 (abs(φ) ≤ 66°)", max(d.arcsec(a.asc, m[0]), d.arcsec(a.mc, m[1])))
        put("RAMC 1900–2026", d.arcsec(a.ramc, m[2]))

    ts, rnd = d.moments(n, 2027, 2100, salt=7)
    for t in ts:
        lat, lon = rnd.uniform(-50.0, 50.0), rnd.uniform(-180.0, 180.0)
        a = eph.angles(t, lat, lon)
        _, m = swe.houses_ex(t.ut1, lat, lon, b"W")
        put("ASC, MC 2027–2100 (abs(φ) ≤ 50°)", max(d.arcsec(a.asc, m[0]), d.arcsec(a.mc, m[1])))
        put("RAMC 2027–2100", d.arcsec(a.ramc, m[2]))

    ts, rnd = d.moments(n, 1900, 2100, salt=8)
    for t in ts:
        lat, lon = rnd.uniform(-66.0, 66.0), rnd.uniform(-180.0, 180.0)
        a = eph.angles(t, lat, lon)
        _, m = swe.houses_armc(a.ramc, lat, a.obliquity, b"W")
        put("ASC, MC при одинаковых θ, ε", max(d.arcsec(a.asc, m[0]), d.arcsec(a.mc, m[1])))

    ts, rnd = d.moments(n, 1950, 2024, salt=3)
    flips = 0
    for t in ts:
        lat = rnd.choice((1, -1)) * rnd.uniform(66.6, 89.5)
        lon = rnd.uniform(-180.0, 180.0)
        a = eph.angles(t, lat, lon)
        _, full = swe.houses_ex(t.ut1, lat, lon, b"W")
        if d.arcsec(a.asc, full[0]) > 90 * 3600:
            flips += 1
        else:
            put("ASC abs(φ) > 66,56°, полный конвейер", d.arcsec(a.asc, full[0]))
        _, same = swe.houses_armc(a.ramc, lat, a.obliquity, b"W")
        put("ASC abs(φ) > 66,56°, одинаковые θ, ε", d.arcsec(a.asc, same[0]))

    ts, rnd = d.moments(n, 1900, 2100, salt=4)
    for t in ts:
        lat, lon = rnd.uniform(-66.0, 66.0), rnd.uniform(-180.0, 180.0)
        a = eph.angles(t, lat, lon)
        ours = eph.placidus(a.ramc, lat, a.obliquity)
        cusps, _ = swe.houses_armc(a.ramc, lat, a.obliquity, b"P")
        put("куспиды Плацидуса", max(d.arcsec(ours[k], cusps[k]) for k in range(12)))

    swe.set_sid_mode(swe.SIDM_LAHIRI)
    ts, _ = d.moments(n, 1900, 2100, salt=5)
    for t in ts:
        _, v = swe.get_ayanamsa_ex(t.tt, swe.FLG_JPLEPH | swe.FLG_NONUT)
        put("айанамша Лахири (средняя)", d.arcsec(eph.ayanamsha_lahiri_mean(t), v))

    ts, _ = d.moments(n, 1900, 2100, salt=6)
    for t in ts:
        put("средний узел", d.arcsec(eph.mean_node(t), d._calc(swe, t, swe.MEAN_NODE)[0]))
        put("истинный узел", d.arcsec(eph.true_node(t), d._calc(swe, t, swe.TRUE_NODE)[0]))

    tol = {
        "долгота: Солнце–Плутон": d.TOL_PLANET,
        "долгота: Луна": d.TOL_MOON,
        "долгота: Солнце–Плутон (ближе 1° к Солнцу)": d.TOL_NEAR_SUN,
        "скорость, °/сут": d.TOL_SPEED,
        "скорость, °/сут (ближе 1° к Солнцу)": d.TOL_SPEED_NEAR_SUN,
        "ASC, MC 1900–2026 (abs(φ) ≤ 66°)": d.TOL_ANGLES_PAST,
        "RAMC 1900–2026": d.TOL_ANGLES_PAST,
        "ASC, MC 2027–2100 (abs(φ) ≤ 50°)": d.TOL_ANGLES_FUTURE,
        "RAMC 2027–2100": 2.5,
        "ASC, MC при одинаковых θ, ε": d.TOL_ANGLES_PAST,
        "ASC abs(φ) > 66,56°, полный конвейер": None,
        "ASC abs(φ) > 66,56°, одинаковые θ, ε": d.TOL_POLAR,
        "куспиды Плацидуса": d.TOL_PLACIDUS,
        "айанамша Лахири (средняя)": d.TOL_AYANAMSHA,
        "средний узел": d.TOL_MEAN_NODE,
        "истинный узел": d.TOL_TRUE_NODE,
    }
    lines = [
        "# Дифф эфемеридного слоя с Swiss Ephemeris (G17-S1)",
        "",
        f"**Дата:** {date.today().isoformat()} · **Выборка:** {n} моментов на величину, "
        f"seed {d.SEED} · **Генератор:** `scripts/spike/ephem_diff_report.py --n {n}`",
        "",
        "Рантайм: `lunora.calc._ephem` — Skyfield "
        f"{eph.versions()['skyfield']} + DE440s. Оракул: Swiss Ephemeris {swe.version} "
        "в режиме `FLG_JPLEPH` на DE440 (`linux_p1550p2650.440`) — те же данные JPL, поэтому "
        "дифф показывает расхождение редукции и моделей, а не эфемерид. Допуски — "
        "ENGINE-SPEC §2.11; величины в угловых секундах, если не указано иное.",
        "",
        "| Величина | Макс. расхождение | Допуск | Итог |",
        "| --- | --- | --- | --- |",
    ]
    bad = 0
    for key, limit in tol.items():
        value = rows.get(key)
        if value is None:
            lines.append(f"| {key} | — (в выборку не попало) | {limit} | — |")
            continue
        ok = limit is None or value <= limit
        bad += not ok
        verdict = "справочно" if limit is None else ("OK" if ok else "**превышен**")
        lim = "—" if limit is None else f"{limit:g}"
        lines.append(f"| {key} | {value:.6f} | {lim} | {verdict} |")
    lines += [
        f"| переворотов ASC на 180° (abs(φ) 66,6–89,5°, 1950–2024) | {flips} | 0 | "
        f"{'OK' if flips == 0 else '**превышен**'} |",
        "",
        "Пояснения — в `docs/current/WORKLOG.md`, шаг 2д.",
        "",
    ]
    bad += flips != 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"ephem_diff_report: {OUT.relative_to(ROOT)} — {'FAIL' if bad else 'OK'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
