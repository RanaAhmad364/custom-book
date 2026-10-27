"""Add account and project privacy controls.

Revision ID: 3e8c2d7a4f91
Revises: 62d0b4c9a1f7
Create Date: 2026-10-25
"""

from alembic import op
import sqlalchemy as sa


revision = "3e8c2d7a4f91"
down_revision = "62d0b4c9a1f7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("privacy_mode", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("user_projects", sa.Column("privacy_override", sa.Boolean(), nullable=True))
    op.add_column("project_assets", sa.Column("original_deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("project_assets", "original_deleted_at")
    op.drop_column("user_projects", "privacy_override")
    op.drop_column("users", "privacy_mode")
