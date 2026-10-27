"""Store PayPal currency snapshots on payments.

Revision ID: 72a31ef8c94d
Revises: ce47a91d205f
Create Date: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = "72a31ef8c94d"
down_revision = "ce47a91d205f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("payments") as batch:
        batch.add_column(sa.Column("pkr_amount", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("usd_amount", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("exchange_rate", sa.Numeric(14, 8), nullable=True))
        batch.add_column(sa.Column("provider_capture_id", sa.String(length=160), nullable=True))
        batch.create_unique_constraint("uq_payments_provider_capture_id", ["provider_capture_id"])


def downgrade():
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint("uq_payments_provider_capture_id", type_="unique")
        batch.drop_column("provider_capture_id")
        batch.drop_column("exchange_rate")
        batch.drop_column("usd_amount")
        batch.drop_column("pkr_amount")
