#!/usr/bin/env python3
"""vendor_check — сверка вендоренных данных (data/vendor) с манифестом SHA-256.

Офлайн: сеть не нужна. Каждый файл в data/vendor должен быть в MANIFEST.yaml с
совпадающими размером и SHA-256; лишние и пропавшие файлы — ошибка (ADR-001 / B12).

Запуск:  python scripts/spike/vendor_check.py [data/vendor]
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

import yaml

DEFAULT = pathlib.Path(__file__).resolve().parents[2] / "data" / "vendor"
UNTRACKED_OK = {"MANIFEST.yaml", "README.md"}


def load_manifest(root: pathlib.Path) -> dict:
    return yaml.safe_load((root / "MANIFEST.yaml").read_text(encoding="utf-8"))


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(root: pathlib.Path) -> list[str]:
    """Список ошибок; пустой — данные совпадают с манифестом."""
    errors: list[str] = []
    listed: set[str] = set()
    for name, s in load_manifest(root)["sets"].items():
        for f in s["files"]:
            rel = f["path"]
            listed.add(rel)
            p = root / rel
            if not p.is_file():
                errors.append(f"{name}: нет файла {rel}")
                continue
            if p.stat().st_size != f["bytes"]:
                errors.append(f"{name}: {rel}: размер {p.stat().st_size} ≠ {f['bytes']}")
            if sha256(p) != f["sha256"]:
                errors.append(f"{name}: {rel}: sha256 не совпадает с манифестом")
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and rel not in listed and rel not in UNTRACKED_OK:
            errors.append(f"{rel}: файл не в манифесте")
    return errors


def main() -> int:
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    errors = verify(root)
    for e in errors:
        print(f"FAIL  {e}")
    n = sum(len(s["files"]) for s in load_manifest(root)["sets"].values())
    print(f"vendor_check: {'FAIL' if errors else 'OK'} ({n} файлов в манифесте)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
