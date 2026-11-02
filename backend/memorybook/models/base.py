from __future__ import annotations

from datetime import UTC, datetime
import os
from uuid import uuid4

from flask import current_app, has_app_context
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column


def configured_currency() -> str:
    if has_app_context():
        return str(current_app.config.get("PAYMENT_DEFAULT_CURRENCY", "USD")).upper()
    return os.getenv("PAYMENT_DEFAULT_CURRENCY", "USD").upper()


class IdMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
