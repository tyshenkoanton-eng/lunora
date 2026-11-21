"""G17-S1: вендоренные данные (tzdata, GeoNames) сверяются с манифестом SHA-256 офлайн."""

import hashlib
import importlib.util
import pathlib
import sys
import tarfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "data" / "vendor"
_spec = importlib.util.spec_from_file_location(
    "vendor_check", ROOT / "scripts" / "spike" / "vendor_check.py"
)
vc = importlib.util.module_from_spec(_spec)
sys.modules["vendor_check"] = vc
_spec.loader.exec_module(vc)


def _mini_vendor(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "set").mkdir()
    blob = b"lunora"
    (tmp_path / "set" / "a.txt").write_bytes(blob)
    (tmp_path / "MANIFEST.yaml").write_text(
        "schema: 1\n"
        "sets:\n"
        "  demo:\n"
        "    version: '1'\n"
        "    files:\n"
        "      - path: set/a.txt\n"
        f"        sha256: {hashlib.sha256(blob).hexdigest()}\n"
        f"        bytes: {len(blob)}\n",
        encoding="utf-8",
    )
    return tmp_path


def test_repo_vendor_matches_manifest():
    assert vc.verify(VENDOR) == []


def test_clean_mini_vendor_passes(tmp_path):
    assert vc.verify(_mini_vendor(tmp_path)) == []


def test_tampered_file_is_reported(tmp_path):
    root = _mini_vendor(tmp_path)
    (root / "set" / "a.txt").write_bytes(b"lunorA")
    errors = vc.verify(root)
    assert any("sha256" in e for e in errors)


def test_missing_file_is_reported(tmp_path):
    root = _mini_vendor(tmp_path)
    (root / "set" / "a.txt").unlink()
    assert any("нет файла" in e for e in vc.verify(root))


def test_unlisted_file_is_reported(tmp_path):
    root = _mini_vendor(tmp_path)
    (root / "set" / "extra.bin").write_bytes(b"x")
    assert any("не в манифесте" in e for e in vc.verify(root))


def test_every_entry_has_source_and_license():
    m = vc.load_manifest(VENDOR)
    for name, s in m["sets"].items():
        for key in ("version", "source", "license", "retrieved"):
            assert s.get(key), f"{name}: нет поля {key}"
        for f in s["files"]:
            assert f.get("url"), f"{name}/{f['path']}: нет url"


def test_pinned_tzdata_package_is_vendored_iana_version():
    import tzdata

    assert tzdata.IANA_VERSION == vc.load_manifest(VENDOR)["sets"]["iana-tz"]["version"]


@pytest.mark.parametrize("name", ["tzdata", "tzcode"])
def test_tarball_version_file_matches_manifest(name):
    version = vc.load_manifest(VENDOR)["sets"]["iana-tz"]["version"]
    with tarfile.open(VENDOR / "iana" / f"{name}{version}.tar.gz") as tar:
        assert tar.extractfile("version").read().decode().strip() == version
