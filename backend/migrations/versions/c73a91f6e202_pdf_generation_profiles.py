"""Add PDF generation profiles and per-file download entitlements.

Revision ID: c73a91f6e202
Revises: 8fb492dca371
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa


revision = "c73a91f6e202"
down_revision = "8fb492dca371"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("pdf_jobs") as batch_op:
        batch_op.add_column(sa.Column("generation_profile", sa.String(length=20), server_default="digital", nullable=False))
        batch_op.create_unique_constraint("uq_pdf_jobs_order_profile", ["order_id", "generation_profile"])

    with op.batch_alter_table("generated_files") as batch_op:
        batch_op.add_column(sa.Column("generation_profile", sa.String(length=20), server_default="digital", nullable=False))
        batch_op.create_unique_constraint("uq_generated_files_order_profile", ["pdf_order_id", "generation_profile"])

    with op.batch_alter_table("download_entitlements") as batch_op:
        batch_op.drop_constraint("uq_download_entitlement_user_order", type_="unique")
        batch_op.create_unique_constraint(
            "uq_download_entitlement_user_order_file",
            ["user_id", "pdf_order_id", "generated_file_id"],
        )


def downgrade():
    with op.batch_alter_table("download_entitlements") as batch_op:
        batch_op.drop_constraint("uq_download_entitlement_user_order_file", type_="unique")
        batch_op.create_unique_constraint("uq_download_entitlement_user_order", ["user_id", "pdf_order_id"])

    with op.batch_alter_table("generated_files") as batch_op:
        batch_op.drop_constraint("uq_generated_files_order_profile", type_="unique")
        batch_op.drop_column("generation_profile")

    with op.batch_alter_table("pdf_jobs") as batch_op:
        batch_op.drop_constraint("uq_pdf_jobs_order_profile", type_="unique")
        batch_op.drop_column("generation_profile")
