"""catalog filters and editable project documents

Revision ID: 713c3e1f0a6b
Revises: 305605e278d1
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


revision = "713c3e1f0a6b"
down_revision = "e4ebcdad0273"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("book_categories") as batch_op:
        batch_op.add_column(sa.Column("style", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("hero_asset_key", sa.String(length=1024), nullable=True))

    with op.batch_alter_table("book_collections") as batch_op:
        batch_op.add_column(sa.Column("eyebrow", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("recommended_layouts", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("related_categories", sa.JSON(), nullable=True))

    with op.batch_alter_table("book_products") as batch_op:
        batch_op.add_column(sa.Column("occasion", sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column("book_type", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("page_count_min", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("page_count_max", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("is_featured", sa.Boolean(), server_default=sa.text("false"), nullable=False))
        batch_op.create_index("ix_book_products_occasion", ["occasion"], unique=False)
        batch_op.create_index("ix_book_products_book_type", ["book_type"], unique=False)

    with op.batch_alter_table("user_projects") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), server_default="1", nullable=False))
        batch_op.add_column(sa.Column("document", sa.JSON(), nullable=True))

    with op.batch_alter_table("project_pages") as batch_op:
        batch_op.add_column(sa.Column("label", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("elements", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("project_pages") as batch_op:
        batch_op.drop_column("elements")
        batch_op.drop_column("label")

    with op.batch_alter_table("user_projects") as batch_op:
        batch_op.drop_column("document")
        batch_op.drop_column("version")

    with op.batch_alter_table("book_products") as batch_op:
        batch_op.drop_index("ix_book_products_book_type")
        batch_op.drop_index("ix_book_products_occasion")
        batch_op.drop_column("is_featured")
        batch_op.drop_column("page_count_max")
        batch_op.drop_column("page_count_min")
        batch_op.drop_column("book_type")
        batch_op.drop_column("occasion")

    with op.batch_alter_table("book_collections") as batch_op:
        batch_op.drop_column("related_categories")
        batch_op.drop_column("recommended_layouts")
        batch_op.drop_column("eyebrow")

    with op.batch_alter_table("book_categories") as batch_op:
        batch_op.drop_column("hero_asset_key")
        batch_op.drop_column("style")
