"""Store print consent and PayPal capture review details.

Revision ID: 4d9f3a7b2c11
Revises: 0c5d8a2f71b4
"""

from alembic import op
import sqlalchemy as sa


revision = "4d9f3a7b2c11"
down_revision = "0c5d8a2f71b4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("print_orders") as batch:
        batch.add_column(sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("payments") as batch:
        batch.add_column(sa.Column("provider_capture_amount", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("provider_capture_currency", sa.String(length=3), nullable=True))


def downgrade():
    with op.batch_alter_table("payments") as batch:
        batch.drop_column("provider_capture_currency")
        batch.drop_column("provider_capture_amount")
    with op.batch_alter_table("print_orders") as batch:
        batch.drop_column("consent_at")
