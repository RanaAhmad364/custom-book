"""Store editable and published admin book designs.

Revision ID: 4bc81f02d9a7
Revises: a18f6c2d9e40
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa


revision = "4bc81f02d9a7"
down_revision = "a18f6c2d9e40"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("book_templates") as batch:
        batch.add_column(sa.Column("design_document", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("published_design_document", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("published_version", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("book_templates") as batch:
        batch.drop_column("published_version")
        batch.drop_column("published_design_document")
        batch.drop_column("design_document")
