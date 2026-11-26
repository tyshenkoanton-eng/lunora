"""Общие фикстуры тестов: временный кластер PostgreSQL + схема через alembic.

Вынесено из tests/payments/conftest.py (G17-S2f), чтобы сквозные тесты интеграции (onboard)
и тесты оплаты поднимали одну и ту же настоящую БД с реальной миграцией (`alembic upgrade head`),
а не metadata.create_all. Нет PostgreSQL → skip; при LUNORA_REQUIRE_PG=1 (make slice-check) — fail.
"""

from __future__ import annotations

import glob
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
from collections.abc import Iterator

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pg_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    cands = sorted(glob.glob(f"/usr/lib/postgresql/*/bin/{name}"))
    return cands[-1] if cands else None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _unavailable(reason: str):
    if os.environ.get("LUNORA_REQUIRE_PG") == "1":
        pytest.fail(f"PostgreSQL обязателен (LUNORA_REQUIRE_PG=1): {reason}", pytrace=False)
    pytest.skip(f"нет PostgreSQL: {reason}")


@pytest.fixture(scope="session")
def pg_dsn() -> Iterator[str]:
    dsn = os.environ.get("LUNORA_TEST_PG_DSN")
    if dsn:
        yield dsn
        return

    initdb, pg_ctl = _pg_bin("initdb"), _pg_bin("pg_ctl")
    if not (initdb and pg_ctl):
        _unavailable("initdb/pg_ctl не найдены и LUNORA_TEST_PG_DSN не задан")

    as_root = os.geteuid() == 0
    prefix: list[str] = []
    if as_root:
        runuser = shutil.which("runuser")
        if not runuser:
            _unavailable("запуск под root без runuser")
        prefix = [runuser, "-u", "postgres", "--"]

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="lunora-pg-"))
    data = tmp / "data"
    if as_root:
        shutil.chown(tmp, "postgres")
    port = _free_port()
    run = lambda args: subprocess.run(  # noqa: E731
        prefix + args, check=True, capture_output=True, text=True
    )
    try:
        run([initdb, "-D", str(data), "-A", "trust", "-U", "postgres", "-E", "UTF8"])
        run(
            [
                pg_ctl, "-D", str(data), "-w", "-l", str(tmp / "pg.log"), "-o",
                f"-p {port} -k {tmp} -c listen_addresses=127.0.0.1 -c fsync=off",
                "start",
            ]
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - среда без PG
        _unavailable(f"кластер не поднялся: {exc.stderr.strip()[:300]}")
    try:
        subprocess.run(
            prefix + [_pg_bin("createdb") or "createdb", "-h", "127.0.0.1", "-p", str(port),
                      "-U", "postgres", "lunora_test"],
            check=True, capture_output=True, text=True,
        )
        yield f"postgresql+asyncpg://postgres@127.0.0.1:{port}/lunora_test"
    finally:
        subprocess.run(prefix + [pg_ctl, "-D", str(data), "-m", "immediate", "stop"],
                       capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="session")
def migrated_dsn(pg_dsn: str) -> str:
    """Схема — настоящая миграция (alembic upgrade head) на чистой базе."""
    env = {**os.environ, "LUNORA_DATABASE_URL": pg_dsn}
    for cmd in (["downgrade", "base"], ["upgrade", "head"]):
        res = subprocess.run(
            [sys.executable, "-m", "alembic", *cmd], cwd=ROOT, env=env,
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            pytest.fail(f"alembic {' '.join(cmd)}: {res.stderr[-2000:]}", pytrace=False)
    return pg_dsn
