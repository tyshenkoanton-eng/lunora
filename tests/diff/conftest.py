"""Оракул Swiss Ephemeris для дифф-тестов (группа [oracle]; рантайм от него не зависит).

SE 2.10.03 читает DE440 в двоичном формате JPL (data/vendor/jpl-oracle, make setup-oracle)
в режиме FLG_JPLEPH: те же данные JPL, что у рантайма, — дифф проверяет нашу редукцию.
Молчаливый откат SE на Moshier или .se1 ловится по флагу результата.
"""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ORACLE_DIR = ROOT / "data" / "vendor" / "jpl-oracle"
ORACLE_FILE = "linux_p1550p2650.440"


@pytest.fixture(scope="session")
def swe():
    swe = pytest.importorskip("swisseph")
    if not (ORACLE_DIR / ORACLE_FILE).is_file():
        pytest.fail(f"нет {ORACLE_DIR / ORACLE_FILE} — запустите make setup-oracle")
    swe.set_ephe_path(str(ORACLE_DIR))
    swe.set_jpl_file(ORACLE_FILE)
    return swe
