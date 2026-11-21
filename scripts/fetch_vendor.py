#!/usr/bin/env python3
"""fetch_vendor — загрузка вендоренных данных, которые не лежат в git (make setup).

Берёт из data/vendor/MANIFEST.yaml наборы с `fetch: setup` нужной группы (`runtime` — рантайм,
`oracle` — тестовые оракулы), качает каждый файл по `url`, сверяет размер и SHA-256 и только
после этого кладёт на место (атомарно, через .part). Файл, который уже есть и совпадает с
манифестом, повторно не качается. Несовпадение суммы — ошибка, файл не остаётся.

Это единственная точка, где эфемеридные данные приходят из сети (ADR-001 / B12):
в рантайме молчаливой загрузки нет.

Запуск:  python scripts/fetch_vendor.py --group runtime [--group oracle] [--root data/vendor]
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys
import urllib.request

import yaml

DEFAULT = pathlib.Path(__file__).resolve().parents[1] / "data" / "vendor"


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ok(path: pathlib.Path, entry: dict) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == entry["bytes"]
        and _sha256(path) == entry["sha256"]
    )


def fetch(root: pathlib.Path, groups: set[str]) -> list[str]:
    """Докачивает недостающие файлы групп `groups`; возвращает список ошибок."""
    manifest = yaml.safe_load((root / "MANIFEST.yaml").read_text(encoding="utf-8"))
    errors: list[str] = []
    for name, s in manifest["sets"].items():
        if s.get("fetch") != "setup" or s.get("group") not in groups:
            continue
        for entry in s["files"]:
            dest = root / entry["path"]
            if _ok(dest, entry):
                print(f"ok    {name}: {entry['path']}")
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            part = dest.with_name(dest.name + ".part")
            print(f"fetch {name}: {entry['url']}")
            try:
                with (
                    urllib.request.urlopen(entry["url"], timeout=120) as resp,  # noqa: S310
                    part.open("wb") as fh,
                ):
                    while chunk := resp.read(1 << 20):
                        fh.write(chunk)
            except OSError as exc:
                part.unlink(missing_ok=True)
                errors.append(f"{name}: {entry['path']}: загрузка не удалась ({exc})")
                continue
            if part.stat().st_size != entry["bytes"]:
                errors.append(
                    f"{name}: {entry['path']}: размер {part.stat().st_size} ≠ {entry['bytes']}"
                )
                part.unlink()
                continue
            if _sha256(part) != entry["sha256"]:
                errors.append(f"{name}: {entry['path']}: sha256 не совпадает с манифестом")
                part.unlink()
                continue
            part.replace(dest)
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", action="append", required=True, choices=["runtime", "oracle"])
    ap.add_argument("--root", type=pathlib.Path, default=DEFAULT)
    args = ap.parse_args()
    errors = fetch(args.root, set(args.group))
    for e in errors:
        print(f"FAIL  {e}")
    print(f"fetch_vendor: {'FAIL' if errors else 'OK'} ({', '.join(args.group)})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
