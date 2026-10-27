"""Add durable in-process background job tracking.

Revision ID: f14a62c9b781
Revises: b51d8c2a4e70
Create Date: 2026-10-25
"""

from alembic import op
import sqlalchemy as sa


revision = "f14a62c9b781"
down_revision = "b51d8c2a4e70"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "background_jobs",
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("reference_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_background_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="ck_background_jobs_attempts",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_type", "reference_id", name="uq_background_jobs_type_reference"),
    )
    op.create_index(
        "ix_background_jobs_status_run_after",
        "background_jobs",
        ["status", "run_after"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_background_jobs_status_run_after", table_name="background_jobs")
    op.drop_table("background_jobs")
