"""Normalize active catalog and pricing currencies to PKR.

Revision ID: ce47a91d205f
Revises: 3e8c2d7a4f91
Create Date: 2026-10-26
"""

from alembic import op
import sqlalchemy as sa


revision = "ce47a91d205f"
down_revision = "3e8c2d7a4f91"
branch_labels = None
depends_on = None


def _set_currency_default(table, value):
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "currency",
                existing_type=sa.String(length=3),
                server_default=value,
                existing_nullable=False,
            )
        return
    op.alter_column(
        table,
        "currency",
        existing_type=sa.String(length=3),
        server_default=value,
        existing_nullable=False,
    )


def upgrade():
    for table in ("book_products", "book_variants", "pricing_tiers", "shipping_rates"):
        op.execute(sa.text(f"UPDATE {table} SET currency = 'PKR'"))
        _set_currency_default(table, "PKR")
    op.execute(sa.text(
        "UPDATE discount_codes SET currency = 'PKR' WHERE currency IS NOT NULL"
    ))
    op.execute(sa.text(
        "UPDATE print_quotes SET expires_at = created_at WHERE consumed_at IS NULL"
    ))


def downgrade():
    for table in ("book_products", "book_variants", "pricing_tiers", "shipping_rates"):
        _set_currency_default(table, "USD")
