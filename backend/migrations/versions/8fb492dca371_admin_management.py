"""admin management, product metadata, and immutable template versions

Revision ID: 8fb492dca371
Revises: 713c3e1f0a6b
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


revision = "8fb492dca371"
down_revision = "713c3e1f0a6b"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("book_products") as batch_op:
        batch_op.add_column(sa.Column("admin_metadata", sa.JSON(), nullable=True))

    with op.batch_alter_table("user_projects") as batch_op:
        batch_op.add_column(sa.Column("template_version", sa.Integer(), nullable=True))

    op.create_table(
        "book_template_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["template_id"], ["book_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "version", name="uq_book_template_versions_number"),
    )
    op.create_index("ix_book_template_versions_template_id", "book_template_versions", ["template_id"])


def downgrade():
    op.drop_index("ix_book_template_versions_template_id", table_name="book_template_versions")
    op.drop_table("book_template_versions")
    with op.batch_alter_table("user_projects") as batch_op:
        batch_op.drop_column("template_version")
    with op.batch_alter_table("book_products") as batch_op:
        batch_op.drop_column("admin_metadata")
