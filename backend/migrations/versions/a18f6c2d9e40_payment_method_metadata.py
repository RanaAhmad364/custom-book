"""Record payment purpose and selected method.

Revision ID: a18f6c2d9e40
Revises: 7d2c9f6a41b8
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa


revision = "a18f6c2d9e40"
down_revision = "7d2c9f6a41b8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("payments") as batch:
        batch.add_column(
            sa.Column(
                "purpose",
                sa.String(length=40),
                nullable=False,
                server_default="order_payment",
            )
        )
        batch.add_column(sa.Column("payment_method", sa.String(length=60), nullable=True))
    op.execute(
        "UPDATE payments SET purpose = 'pdf_purchase' WHERE pdf_order_id IS NOT NULL"
    )
    op.execute(
        "UPDATE payments SET purpose = 'print_order' WHERE print_order_id IS NOT NULL"
    )


def downgrade():
    with op.batch_alter_table("payments") as batch:
        batch.drop_column("payment_method")
        batch.drop_column("purpose")
