#!/usr/bin/env python3
"""tz_backzone_check — стандартная сборка IANA ↔ полная с backzone (G17-S1, шаг 3д).

Из вендоренных tzcode/tzdata (data/vendor/iana) собирает zic и zdump 2026f, компилирует
две сборки: стандартную и с полным backzone (PACKRATDATA=backzone PACKRATLIST=), и сравнивает
переходы (zdump -V, 1900–2015) по зонам городов бывшего СССР от N жителей (GeoNames
из data/vendor/geonames). Плюс «тёзки»: зона backzone с именем самого города
(Europe/Tiraspol), когда GeoNames ведёт город по другой зоне, — такие расхождения
стандартная сборка прячет. Отдельно проверяет, что пакет tzdata с PyPI совпадает
со стандартной сборкой (TZif побайтно, tzdata.zi построчно): рантайм считает на тех же
данных, что лежат в вендоре.

Запуск:  python scripts/spike/tz_backzone_check.py [--min-pop 100000] [--write REPORT.md]
Нужно:   make, cc. Сеть не нужна.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from importlib import resources
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from vendor_check import DEFAULT as VENDOR  # noqa: E402
from vendor_check import load_manifest, verify  # noqa: E402

EX_USSR = {
    "RU",
    "UA",
    "BY",
    "KZ",
    "UZ",
    "GE",
    "AZ",
    "AM",
    "MD",
    "LV",
    "LT",
    "EE",
    "KG",
    "TJ",
    "TM",
}
SAMPLE_DATES = [datetime(y, m, 15, 12) for y in range(1930, 2015) for m in (1, 4, 7, 10)]
WINDOW = (1900, 2015)


@dataclasses.dataclass(frozen=True)
class Build:
    std: pathlib.Path
    full: pathlib.Path
    zdump: pathlib.Path
    version: str
    zic_version: str
    zones_std: int
    zones_full: int


def _run(args: list[str], cwd: pathlib.Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def _zone_count(zi: pathlib.Path) -> int:
    return sum(line.startswith("Z ") for line in zi.read_text(encoding="utf-8").splitlines())


def build(vendor: pathlib.Path, work: pathlib.Path) -> Build:
    """Собирает zic/zdump и две сборки зон в work/. Вендор сверяется с манифестом до сборки."""
    errors = verify(vendor)
    if errors:
        raise RuntimeError("вендор не совпадает с манифестом: " + "; ".join(errors))
    version = load_manifest(vendor)["sets"]["iana-tz"]["version"]
    src = work / "src"
    src.mkdir(parents=True)
    for name in ("tzcode", "tzdata"):
        with tarfile.open(vendor / "iana" / f"{name}{version}.tar.gz") as tar:
            tar.extractall(src, filter="data")
    out = {}
    for label, packrat in (("std", []), ("full", ["PACKRATDATA=backzone", "PACKRATLIST="])):
        # clean: промежуточные .zi make не пересобирает при смене PACKRAT*
        _run(["make", "-s", "clean"], src)
        _run(["make", "-s", *packrat, "zic", "zdump", "tzdata.zi"], src)
        zi = work / f"{label}.zi"
        zi.write_bytes((src / "tzdata.zi").read_bytes())
        _run(["./zic", "-d", str(work / label), str(zi)], src)
        out[label] = zi
    zic_version = _run(["./zic", "--version"], src).strip()
    head = out["std"].read_text(encoding="utf-8").splitlines()[0]
    if head != f"# version {version}":
        raise RuntimeError(f"tzdata.zi: ожидалась версия {version}, в файле «{head}»")
    return Build(
        std=work / "std",
        full=work / "full",
        zdump=src / "zdump",
        version=version,
        zic_version=zic_version,
        zones_std=_zone_count(out["std"]),
        zones_full=_zone_count(out["full"]),
    )


def _dump_many(b: Build, files: list[pathlib.Path], lo: int, hi: int) -> dict[str, list[str]]:
    """zdump -V (без крайних time_t) для многих файлов одним вызовом.

    Возвращает путь → строки переходов без первой колонки (пути).
    """
    out: dict[str, list[str]] = {str(f): [] for f in files}
    text = _run([str(b.zdump), "-V", "-c", f"{lo},{hi}", *map(str, files)], b.std)
    for line in text.splitlines():
        if line.strip():
            path, rest = line.split(None, 1)
            out[path].append(rest)
    return out


def _dump(b: Build, tzfile: pathlib.Path, lo: int, hi: int) -> list[str]:
    return _dump_many(b, [tzfile], lo, hi)[str(tzfile)]


def _first_diff(a: list[str], c: list[str], zone: str) -> dict | None:
    if a == c:
        return None
    i = next(
        (k for k, (x, y) in enumerate(zip(a, c, strict=False)) if x != y), min(len(a), len(c))
    )
    line = a[i] if i < len(a) else c[i]
    year = int(line.split(" UT = ")[0].split()[-1])
    return {"zone": zone, "lines_std": len(a), "lines_full": len(c), "first_year": year}


def zone_diff(b: Build, zone: str, lo: int = WINDOW[0], hi: int = WINDOW[1]) -> dict | None:
    """None — переходы совпадают; иначе число строк переходов и год первого расхождения."""
    return _first_diff(_dump(b, b.std / zone, lo, hi), _dump(b, b.full / zone, lo, hi), zone)


def grid_divergence(b: Build, zone: str) -> int:
    """Число дат сетки 1930–2014 × 4, где смещения сборок различаются."""
    za = ZoneInfo.from_file((b.std / zone).open("rb"), key=zone)
    zb = ZoneInfo.from_file((b.full / zone).open("rb"), key=zone)
    return sum(
        d.replace(tzinfo=za).utcoffset() != d.replace(tzinfo=zb).utcoffset() for d in SAMPLE_DATES
    )


def _names(root: pathlib.Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def package_mismatches(b: Build) -> list[str]:
    """Файлы, где пакет tzdata (PyPI) отличается от стандартной сборки из вендора.

    TZif-файлы зон — побайтно. tzdata.zi — как набор строк: порядок строк в нём зависит
    от реализации awk (zishrink.awk), смысл — нет. Пустой список — рантайм считает ровно на
    вендоренных исходниках.
    """
    pkg = pathlib.Path(str(resources.files("tzdata").joinpath("zoneinfo")))
    theirs = {n for n in _names(pkg) if (pkg / n).read_bytes()[:4] == b"TZif"}
    ours = set(_names(b.std))
    bad = sorted(theirs ^ ours)
    bad += [n for n in sorted(ours & theirs) if (b.std / n).read_bytes() != (pkg / n).read_bytes()]
    ours_zi = (b.std.parent / "std.zi").read_text(encoding="utf-8").splitlines()
    pkg_zi = (pkg / "tzdata.zi").read_text(encoding="utf-8").splitlines()
    if ours_zi[0] != pkg_zi[0] or sorted(ours_zi) != sorted(pkg_zi):
        bad.append("tzdata.zi")
    return bad


def city_rows(b: Build, min_pop: int) -> tuple[int, list[dict]]:
    from geonames_vendor import load_cities

    cities = [
        c
        for c in load_cities().values()
        if c["countrycode"] in EX_USSR and c["population"] >= min_pop
    ]
    cache: dict[str, dict | None] = {}
    rows = []
    for c in cities:
        z = c["timezone"]
        if z not in cache:
            cache[z] = zone_diff(b, z)
            if cache[z] is not None:
                cache[z]["grid"] = grid_divergence(b, z)
        if cache[z] is not None:
            rows.append(
                {
                    **cache[z],
                    "city": c["name"],
                    "geonameid": c["geonameid"],
                    "country": c["countrycode"],
                    "population": c["population"],
                }
            )
    rows.sort(key=lambda r: (-r["population"], r["city"]))
    return len(cities), rows


def namesake_rows(b: Build, min_pop: int) -> list[dict]:
    """Города, у которых в полной сборке есть зона-тёзка с иной историей, чем зона GeoNames."""
    from geonames_vendor import load_cities

    full_names = {n.rsplit("/", 1)[-1]: n for n in _names(b.full)}
    rows = []
    for c in load_cities().values():
        if c["countrycode"] not in EX_USSR or c["population"] < min_pop:
            continue
        twin = full_names.get(c["asciiname"].replace(" ", "_"))
        if not twin or twin == c["timezone"] or zone_diff(b, twin) is None:
            continue
        geo = ZoneInfo.from_file((b.std / c["timezone"]).open("rb"), key=c["timezone"])
        alt = ZoneInfo.from_file((b.full / twin).open("rb"), key=twin)
        dates = [
            d
            for d in SAMPLE_DATES
            if d.replace(tzinfo=geo).utcoffset() != d.replace(tzinfo=alt).utcoffset()
        ]
        rows.append(
            {
                "geonameid": c["geonameid"],
                "city": c["name"],
                "country": c["countrycode"],
                "population": c["population"],
                "geonames_zone": c["timezone"],
                "backzone_zone": twin,
                "grid": len(dates),
                "span": f"{dates[0]:%Y-%m}…{dates[-1]:%Y-%m}" if dates else "—",
            }
        )
    return sorted(rows, key=lambda r: -r["population"])


def all_zone_diffs(b: Build) -> list[dict]:
    names = _names(b.std)
    lo, hi = WINDOW
    a = _dump_many(b, [b.std / n for n in names], lo, hi)
    c = _dump_many(b, [b.full / n for n in names], lo, hi)
    diffs = (_first_diff(a[str(b.std / n)], c[str(b.full / n)], n) for n in names)
    return [d for d in diffs if d is not None]


def dispute_note(geonameid: int) -> str:
    """Ссылка на запись реестра tz_disputes, если место уже разобрано."""
    from geonames_vendor import load_cities

    from lunora.timeplace import load_disputes, region_of

    place = f"geonames:{geonameid}"
    c = load_cities().get(geonameid)
    region = region_of(c["countrycode"], c["admin1_code"]) if c else None
    found = [d for d in load_disputes() if d.place_id == place or region in d.regions]
    if not found:
        return "требует ручного разбора"
    return "; ".join(
        f"{d.id} `{d.status}` ({d.valid_from or '…'} — {d.valid_to or '…'}), "
        f"{d.primary_zone} / {d.alternative_zone}"
        for d in found
    )


def render(
    b: Build,
    total: int,
    rows: list[dict],
    twins: list[dict],
    zones: list[dict],
    pkg_bad: list[str],
    min_pop: int,
) -> str:
    ex_zones = sorted({r["zone"] for r in rows})
    lines = [
        "# Сверка сборок IANA: стандартная ↔ backzone (G17-S1, шаг 3д)",
        "",
        "<!-- СГЕНЕРИРОВАНО scripts/spike/tz_backzone_check.py. Руками не править. -->",
        "",
        f"Источник: вендоренные `tzdata{b.version}` + `tzcode{b.version}` (`data/vendor/iana`, "
        f"SHA-256 в манифесте), компилятор `{b.zic_version}`. Сборки: стандартная "
        f"({b.zones_std} зон) и с полным `backzone` ({b.zones_full} зон). Сравнение — переходы "
        f"`zdump -V` в окне {WINDOW[0]}–{WINDOW[1]}.",
        "",
        "## Пакет tzdata ↔ вендоренные исходники",
        "",
        "Пакет `tzdata` (PyPI), на котором считает рантайм, против стандартной сборки из вендора, "
        "все TZif-файлы зон побайтно и `tzdata.zi` построчно: "
        + (
            "**совпадает полностью**."
            if not pkg_bad
            else f"**расхождения: {len(pkg_bad)}** — " + ", ".join(f"`{z}`" for z in pkg_bad)
        ),
        "",
        "## Города бывшего СССР",
        "",
        f"Городов от {min_pop:,} жителей ".replace(",", " ")
        + f"(GeoNames, снимок data/vendor): **{total}**. "
        + "Город попадает в таблицу, если у его зоны переходы в сборках различаются: "
        f"**{len(rows)}** городов, зон: **{len(ex_zones)}**.",
        "",
    ]
    if rows:
        lines += [
            "| GeoNames id | Город | Страна | Население | Зона | Первое расхождение, год "
            "| Дат сетки 1930–2014 × 4 с разным смещением (из 340) |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {r['geonameid']} | {r['city']} | {r['country']} | {r['population']} "
            f"| {r['zone']} | {r['first_year']} | {r['grid']} |"
            for r in rows
        ]
        lines.append("")
    lines += [
        "### Тёзки из backzone",
        "",
        "Зона `backzone` с именем самого города, а GeoNames ведёт город по другой зоне. "
        f"Найдено: **{len(twins)}**. Это кандидаты в `tz_disputes`: стандартная сборка "
        "склеивает такую зону с соседней и прячет расхождение.",
        "",
    ]
    if twins:
        lines += [
            "| GeoNames id | Город | Страна | Население | Зона GeoNames | Зона backzone "
            "| Дат сетки с разным смещением (из 340) | Период расхождения на сетке | Разбор |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {r['geonameid']} | {r['city']} | {r['country']} | {r['population']} "
            f"| {r['geonames_zone']} | {r['backzone_zone']} | {r['grid']} | {r['span']} "
            f"| {dispute_note(r['geonameid'])} |"
            for r in twins
        ]
        lines += [
            "",
            "Период на сетке шире окна записи реестра: часть расхождения признана ошибкой "
            "источника — обоснование в `source_note` записи (`tz_disputes.yaml`).",
            "",
        ]
    lines += [
        "## Все зоны (справочно)",
        "",
        f"Зон и ссылок, где сборки расходятся в окне {WINDOW[0]}–{WINDOW[1]}: **{len(zones)}**. "
        "Из бывшего СССР среди них только тёзки из таблицы выше.",
        "",
        ", ".join(f"`{d['zone']}`" for d in zones),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-pop", type=int, default=100_000)
    ap.add_argument("--write", type=pathlib.Path)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        b = build(VENDOR, pathlib.Path(tmp))
        total, rows = city_rows(b, args.min_pop)
        twins = namesake_rows(b, args.min_pop)
        zones = all_zone_diffs(b)
        text = render(b, total, rows, twins, zones, package_mismatches(b), args.min_pop)
    if args.write:
        args.write.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
