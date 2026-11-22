"""G17-S3a: таблицы адаптера Telegram Stars (§2.4b, S1–S5)

Revision ID: 002
Revises: 001
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = dict(server_default=sa.func.now(), nullable=False)


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "star_orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XTR"),
        sa.Column("price_xtr", sa.Integer(), nullable=False),
        sa.Column("payload", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="awaiting_payment"),
        sa.Column("created_at", sa.DateTime(timezone=True), **_TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **_TS),
        sa.CheckConstraint("currency = 'XTR'", name="star_orders_currency_xtr"),
        sa.CheckConstraint("price_xtr > 0", name="star_orders_price_positive"),
        sa.CheckConstraint(
            _in("status", ("awaiting_payment", "active", "refunded")), name="star_orders_status"
        ),
    )
    op.create_table(
        "star_processed_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("event_key", sa.String(200), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), **_TS),
        sa.UniqueConstraint("kind", "event_key", name="star_processed_events_key"),
    )
    op.create_table(
        "star_payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("star_orders.id"), nullable=True,
                  index=True),
        sa.Column("telegram_payment_charge_id", sa.String(200), nullable=False, unique=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), **_TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **_TS),
        sa.CheckConstraint(
            _in("status", ("succeeded", "reconcile_needed", "paid_late", "unknown_order",
                           "refunded_full")),
            name="star_payments_status",
        ),
        sa.CheckConstraint(_in("source", ("update", "reconcile")), name="star_payments_source"),
    )
    op.create_table(
        "star_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("star_orders.id"), nullable=False,
                  unique=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), **_TS),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_in("status", ("active", "revoked")), name="star_grants_status"),
    )
    op.create_table(
        "star_refunds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("payment_id", sa.Uuid(), sa.ForeignKey("star_payments.id"), nullable=False,
                  unique=True),
        sa.Column("amount_xtr", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), **_TS),
        sa.Column("updated_at", sa.DateTime(timezone=True), **_TS),
        sa.CheckConstraint(
            _in("status", ("requested", "succeeded", "failed")), name="star_refunds_status"
        ),
        sa.CheckConstraint(_in("origin", ("bot", "telegram")), name="star_refunds_origin"),
        sa.CheckConstraint("amount_xtr > 0", name="star_refunds_amount_positive"),
    )


def downgrade() -> None:
    for t in ("star_refunds", "star_grants", "star_payments", "star_processed_events",
              "star_orders"):
        op.drop_table(t)
