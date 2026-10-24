from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, func, select
from sqlalchemy.orm import Mapped, mapped_column

from memorybook.extensions import db
from memorybook.models.authentication import Role, UserRole


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(40))
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def public_dict(self) -> dict:
        role_names = db.session.scalars(
            select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == self.id)
        ).all()
        return {
            "id": self.id,
            "email": self.email,
            "name": self.full_name,
            "phone": self.phone,
            "isActive": self.is_active,
            "emailVerified": self.email_verified_at is not None,
            "roles": role_names,
        }
