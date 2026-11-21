"""G17-S1, шаг 2а: эфемеридные данные JPL — манифест SHA-256, файлы вне git, загрузка в make setup.

DE440s (ENGINE-SPEC §2.1, §0.5) и файл DE440 для оракула Swiss Ephemeris вендорятся как данные
(ADR-001 / B12): суммы — в data/vendor/MANIFEST.yaml, сами файлы качает
scripts/fetch_vendor.py из make setup; в git их нет, в рантайме молчаливой загрузки нет.
"""

import hashlib
import importlib.util
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "data" / "vendor"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_spike(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "spike" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fv = _load("fetch_vendor")
vc = _load_spike("vendor_check")

DE440S_SHA256 = "c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2"  # §0.5


def _sets():
    return vc.load_manifest(VENDOR)["sets"]


def test_de440s_in_manifest_with_spec_checksum():
    s = _sets()["jpl-de440s"]
    (f,) = s["files"]
    assert f["path"] == "jpl/de440s.bsp"
    assert f["sha256"] == DE440S_SHA256
    assert f["bytes"] == 32726016
    assert f["url"].startswith("https://naif.jpl.nasa.gov/")
    assert s["fetch"] == "setup"
    assert s["group"] == "runtime"


def test_oracle_de440_in_manifest_as_oracle_group():
    s = _sets()["jpl-de440-oracle"]
    assert s["group"] == "oracle"
    assert s["fetch"] == "setup"
    paths = {f["path"] for f in s["files"]}
    assert "jpl-oracle/linux_p1550p2650.440" in paths
    assert all(f["url"].startswith("https://ssd.jpl.nasa.gov/") for f in s["files"])


def test_fetched_sets_are_not_in_git():
    tracked = subprocess.run(
        ["git", "ls-files", "data/vendor"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    for name, s in _sets().items():
        if s.get("fetch") != "setup":
            continue
        for f in s["files"]:
            assert f"data/vendor/{f['path']}" not in tracked, f"{name}: {f['path']} в git"
            ignored = subprocess.run(
                ["git", "check-ignore", "-q", f"data/vendor/{f['path']}"], cwd=ROOT
            )
            assert ignored.returncode == 0, f"{f['path']} не в .gitignore"


def test_de440s_present_and_matches_spec_checksum():
    path = VENDOR / "jpl" / "de440s.bsp"
    assert path.is_file(), "нет de440s.bsp — запустите make setup"
    assert vc.sha256(path) == DE440S_SHA256


# --- fetch_vendor: загрузка по манифесту (сеть подменяется file://) ---


def _mini(tmp_path: pathlib.Path, blob: bytes, sha: str | None = None) -> pathlib.Path:
    src = tmp_path / "src.bin"
    src.write_bytes(blob)
    root = tmp_path / "vendor"
    root.mkdir()
    (root / "MANIFEST.yaml").write_text(
        "schema: 1\n"
        "sets:\n"
        "  demo:\n"
        "    version: '1'\n"
        "    fetch: setup\n"
        "    group: runtime\n"
        "    files:\n"
        "      - path: d/x.bin\n"
        f"        url: {src.as_uri()}\n"
        f"        sha256: {sha or hashlib.sha256(blob).hexdigest()}\n"
        f"        bytes: {len(blob)}\n"
        "  tracked:\n"
        "    version: '1'\n"
        "    files: []\n",
        encoding="utf-8",
    )
    return root


def test_fetch_downloads_and_verifies(tmp_path):
    root = _mini(tmp_path, b"ephemeris")
    assert fv.fetch(root, groups={"runtime"}) == []
    assert (root / "d" / "x.bin").read_bytes() == b"ephemeris"
    assert vc.verify(root) == []


def test_fetch_rejects_wrong_checksum_and_leaves_nothing(tmp_path):
    root = _mini(tmp_path, b"ephemeris", sha="0" * 64)
    errors = fv.fetch(root, groups={"runtime"})
    assert any("sha256" in e for e in errors)
    assert not (root / "d" / "x.bin").exists()
    assert list(root.rglob("*.part")) == []


def test_fetch_skips_present_valid_file(tmp_path):
    root = _mini(tmp_path, b"ephemeris")
    assert fv.fetch(root, groups={"runtime"}) == []
    (tmp_path / "src.bin").unlink()  # источник пропал — повторный setup не ходит в сеть
    assert fv.fetch(root, groups={"runtime"}) == []


def test_fetch_respects_group(tmp_path):
    root = _mini(tmp_path, b"ephemeris")
    assert fv.fetch(root, groups={"oracle"}) == []
    assert not (root / "d" / "x.bin").exists()


@pytest.mark.parametrize("group", ["runtime", "oracle"])
def test_makefile_setup_fetches_group(group):
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert f"scripts/fetch_vendor.py --group {group}" in mk


# --- ephem_data_check: вход slice-check (DE440s + сумма + версия tzdata) ---


def test_ephem_data_check_passes_on_repo():
    edc = _load_spike("ephem_data_check")
    assert edc.check(VENDOR) == []


def test_ephem_data_check_reports_missing_de440s(tmp_path):
    edc = _load_spike("ephem_data_check")
    (tmp_path / "MANIFEST.yaml").write_text(
        (VENDOR / "MANIFEST.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    errors = edc.check(tmp_path)
    assert any("de440s.bsp" in e and "make setup" in e for e in errors)


def test_slice_check_runs_ephemeris_checks():
    mk = (ROOT / "Makefile").read_text(encoding="utf-8")
    # slice-check накопительный (G17-S2): проверки S1 живут в slice-check-s1 и входят в него
    head = mk.split("\nslice-check:", 1)[1].split("\n", 1)[0]
    assert "slice-check-s1" in head
    block = mk.split("\nslice-check-s1:", 1)[1].split("\n\n", 1)[0]
    assert "scripts/spike/ephem_data_check.py" in block
    assert "tests/test_ephem.py" in block
    assert 'tests/diff -m "not full"' in block
