"""Add stable machine codes to paper and cover catalog options.

Revision ID: 91d4a7c2e6b0
Revises: f14a62c9b781
Create Date: 2026-10-29
"""

from alembic import op
import sqlalchemy as sa


revision = "91d4a7c2e6b0"
down_revision = "72a31ef8c94d"
branch_labels = None
depends_on = None


def _backfill_codes(table_name: str) -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(f"SELECT id FROM {table_name} WHERE code IS NULL")).all()
    for (item_id,) in rows:
        code = f"legacy-{item_id.replace('-', '')[:32]}"
        connection.execute(
            sa.text(f"UPDATE {table_name} SET code = :code WHERE id = :item_id"),
            {"code": code, "item_id": item_id},
        )


def upgrade():
    op.add_column("cover_types", sa.Column("code", sa.String(length=40), nullable=True))
    op.add_column("paper_types", sa.Column("code", sa.String(length=40), nullable=True))
    _backfill_codes("cover_types")
    _backfill_codes("paper_types")
    with op.batch_alter_table("cover_types") as batch_op:
        batch_op.alter_column("code", existing_type=sa.String(length=40), nullable=False)
        batch_op.create_unique_constraint("uq_cover_types_code", ["code"])
    with op.batch_alter_table("paper_types") as batch_op:
        batch_op.alter_column("code", existing_type=sa.String(length=40), nullable=False)
        batch_op.create_unique_constraint("uq_paper_types_code", ["code"])


def downgrade():
    with op.batch_alter_table("paper_types") as batch_op:
        batch_op.drop_constraint("uq_paper_types_code", type_="unique")
        batch_op.drop_column("code")
    with op.batch_alter_table("cover_types") as batch_op:
        batch_op.drop_constraint("uq_cover_types_code", type_="unique")
        batch_op.drop_column("code")
