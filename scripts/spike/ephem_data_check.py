#!/usr/bin/env python3
"""ephem_data_check — вход slice-check G17-S1: эфемериды и время на месте и закреплены.

Офлайн. Проверяет: de440s.bsp лежит в data/vendor/jpl и его SHA-256 = манифест = ENGINE-SPEC
§0.5; рантайм `_ephem` объявляет ту же сумму; Skyfield — закреплённая 1.55; пакет tzdata —
версия IANA из манифеста (2026f).

Запуск:  python scripts/spike/ephem_data_check.py [data/vendor]
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "data" / "vendor"
SPEC_SHA256 = "c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2"  # §0.5
SKYFIELD = "1.55"


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(root: pathlib.Path) -> list[str]:
    errors: list[str] = []
    sets = yaml.safe_load((root / "MANIFEST.yaml").read_text(encoding="utf-8"))["sets"]
    (entry,) = sets["jpl-de440s"]["files"]
    if entry["sha256"] != SPEC_SHA256:
        errors.append("манифест: сумма DE440s не совпадает с ENGINE-SPEC §0.5")
    path = root / entry["path"]
    if not path.is_file():
        errors.append(f"нет {entry['path']} (de440s.bsp) — запустите make setup")
    elif _sha256(path) != entry["sha256"]:
        errors.append(f"{entry['path']}: SHA-256 не совпадает с манифестом")

    import skyfield
    import tzdata

    from lunora.calc import _ephem

    if entry["sha256"] != _ephem.EPHEMERIS_SHA256:
        errors.append("_ephem.EPHEMERIS_SHA256 расходится с манифестом")
    if skyfield.__version__ != SKYFIELD:
        errors.append(f"Skyfield {skyfield.__version__} ≠ закреплённой {SKYFIELD}")
    if sets["iana-tz"]["version"] != tzdata.IANA_VERSION:
        errors.append(f"tzdata {tzdata.IANA_VERSION} ≠ {sets['iana-tz']['version']}")
    return errors


def main() -> int:
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    errors = check(root)
    for e in errors:
        print(f"FAIL  {e}")
    print(f"ephem_data_check: {'FAIL' if errors else 'OK'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
