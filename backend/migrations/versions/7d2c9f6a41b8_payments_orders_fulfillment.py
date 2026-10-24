"""Add idempotent payment, quote, and notification event keys.

Revision ID: 7d2c9f6a41b8
Revises: c73a91f6e202
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa


revision = "7d2c9f6a41b8"
down_revision = "c73a91f6e202"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("pdf_orders") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint("uq_pdf_orders_idempotency_key", ["idempotency_key"])
    with op.batch_alter_table("print_orders") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint("uq_print_orders_idempotency_key", ["idempotency_key"])
    with op.batch_alter_table("payments") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint("uq_payments_idempotency_key", ["idempotency_key"])
        batch.create_unique_constraint("uq_payments_pdf_order", ["pdf_order_id"])
        batch.create_unique_constraint("uq_payments_print_order", ["print_order_id"])
    with op.batch_alter_table("payment_attempts") as batch:
        batch.add_column(sa.Column("checkout_url", sa.String(length=2048), nullable=True))
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint(
            "uq_payment_attempts_idempotency_key",
            ["payment_id", "idempotency_key"],
        )
        batch.create_unique_constraint(
            "uq_payment_attempts_payment_number",
            ["payment_id", "attempt_number"],
        )
    with op.batch_alter_table(
        "payment_webhook_events",
        naming_convention={"uq": "%(table_name)s_%(column_0_name)s_key"},
    ) as batch:
        batch.drop_constraint("payment_webhook_events_provider_event_id_key", type_="unique")
        batch.create_unique_constraint(
            "uq_payment_webhook_provider_event",
            ["provider", "provider_event_id"],
        )
    with op.batch_alter_table("refunds") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint("uq_refunds_idempotency_key", ["idempotency_key"])
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("event_key", sa.String(length=200), nullable=True))
        batch.create_unique_constraint("uq_notifications_event_key", ["event_key"])
    with op.batch_alter_table("email_logs") as batch:
        batch.add_column(sa.Column("event_key", sa.String(length=200), nullable=True))
        batch.create_unique_constraint("uq_email_logs_event_key", ["event_key"])

    op.create_table(
        "print_quotes",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("project_revision_id", sa.String(length=36), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("shipping_address_snapshot", sa.JSON(), nullable=False),
        sa.Column("price_snapshot", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("total_amount >= 0", name="ck_print_quotes_total_nonnegative"),
        sa.ForeignKeyConstraint(["project_id"], ["user_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_revision_id"], ["project_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_print_quotes_user_expiry", "print_quotes", ["user_id", "expires_at"], unique=False)
    op.create_index("ix_print_quotes_project_id", "print_quotes", ["project_id"], unique=False)
    op.create_index("ix_print_quotes_expires_at", "print_quotes", ["expires_at"], unique=False)


def downgrade():
    op.drop_index("ix_print_quotes_expires_at", table_name="print_quotes")
    op.drop_index("ix_print_quotes_project_id", table_name="print_quotes")
    op.drop_index("ix_print_quotes_user_expiry", table_name="print_quotes")
    op.drop_table("print_quotes")

    with op.batch_alter_table("email_logs") as batch:
        batch.drop_constraint("uq_email_logs_event_key", type_="unique")
        batch.drop_column("event_key")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_constraint("uq_notifications_event_key", type_="unique")
        batch.drop_column("event_key")
    with op.batch_alter_table("refunds") as batch:
        batch.drop_constraint("uq_refunds_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")
    with op.batch_alter_table(
        "payment_webhook_events",
        naming_convention={"uq": "%(table_name)s_%(column_0_name)s_key"},
    ) as batch:
        batch.drop_constraint("uq_payment_webhook_provider_event", type_="unique")
        batch.create_unique_constraint(
            "payment_webhook_events_provider_event_id_key",
            ["provider_event_id"],
        )
    with op.batch_alter_table("payment_attempts") as batch:
        batch.drop_constraint("uq_payment_attempts_payment_number", type_="unique")
        batch.drop_constraint("uq_payment_attempts_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")
        batch.drop_column("checkout_url")
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint("uq_payments_print_order", type_="unique")
        batch.drop_constraint("uq_payments_pdf_order", type_="unique")
        batch.drop_constraint("uq_payments_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")
    with op.batch_alter_table("print_orders") as batch:
        batch.drop_constraint("uq_print_orders_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")
    with op.batch_alter_table("pdf_orders") as batch:
        batch.drop_constraint("uq_pdf_orders_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")
