"""G17-S2f: пол/ФИО в users и полное происхождение в calculation_runs (F02/F04/F07)

Revision ID: 003
Revises: 002
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # users: место (F02) и ПДн-вход движков (F04) — пол и ФИО при рождении
    op.add_column("users", sa.Column("place_id", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("region", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("sex", sa.String(1), nullable=True))
    op.add_column("users", sa.Column("name_surname", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("name_given", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("name_patronymic", sa.String(100), nullable=True))

    # calculation_runs: полное происхождение входа (F07)
    op.add_column("calculation_runs", sa.Column("timezone", sa.String(50), nullable=True))
    op.add_column("calculation_runs", sa.Column("precision", sa.String(20), nullable=True))
    op.add_column("calculation_runs", sa.Column("tolerance_minutes", sa.Integer(), nullable=True))
    op.add_column("calculation_runs", sa.Column("place_id", sa.String(64), nullable=True))
    op.add_column("calculation_runs", sa.Column("region", sa.String(64), nullable=True))
    op.add_column("calculation_runs", sa.Column("dispute_id", sa.String(32), nullable=True))
    op.add_column(
        "calculation_runs",
        sa.Column("provenance", JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    for col in ("provenance", "dispute_id", "region", "place_id", "tolerance_minutes",
                "precision", "timezone"):
        op.drop_column("calculation_runs", col)
    for col in ("name_patronymic", "name_given", "name_surname", "sex", "region", "place_id"):
        op.drop_column("users", col)
