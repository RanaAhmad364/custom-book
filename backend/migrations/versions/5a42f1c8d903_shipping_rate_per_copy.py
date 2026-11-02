"""Make per-copy shipping an explicit option.

Revision ID: 5a42f1c8d903
Revises: 4d9f3a7b2c11
"""

from alembic import op
import sqlalchemy as sa


revision = "5a42f1c8d903"
down_revision = "4d9f3a7b2c11"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("shipping_rates") as batch:
        batch.add_column(
            sa.Column("per_copy", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade():
    with op.batch_alter_table("shipping_rates") as batch:
        batch.drop_column("per_copy")
