from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from memorybook.extensions import db
from memorybook.models.base import IdMixin, TimestampMixin


class UserProject(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "user_projects"
    __table_args__ = (Index("ix_user_projects_owner_updated", "user_id", "updated_at"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("book_products.id", ondelete="SET NULL"), index=True)
    template_id: Mapped[str | None] = mapped_column(ForeignKey("book_templates.id", ondelete="SET NULL"), index=True)
    template_version: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", server_default="draft", index=True)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    document: Mapped[dict | None] = mapped_column(db.JSON)
    cover_settings: Mapped[dict | None] = mapped_column(db.JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectPage(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "project_pages"
    __table_args__ = (
        UniqueConstraint("project_id", "page_number", name="uq_project_pages_project_number"),
        CheckConstraint("page_number > 0", name="ck_project_pages_page_number_positive"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("user_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_type: Mapped[str] = mapped_column(String(30), nullable=False, default="interior", server_default="interior")
    label: Mapped[str | None] = mapped_column(String(120))
    layout_key: Mapped[str | None] = mapped_column(String(100))
    background: Mapped[dict | None] = mapped_column(db.JSON)
    elements: Mapped[list | None] = mapped_column(db.JSON)


class ProjectAsset(IdMixin, db.Model):
    __tablename__ = "project_assets"
    __table_args__ = (
        Index("ix_project_assets_project_created", "project_id", "created_at"),
        CheckConstraint("byte_size >= 0", name="ck_project_assets_size_nonnegative"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("user_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id: Mapped[str | None] = mapped_column(ForeignKey("project_pages.id", ondelete="SET NULL"), index=True)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProjectElement(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "project_elements"
    __table_args__ = (
        Index("ix_project_elements_page_order", "page_id", "sort_order"),
        CheckConstraint("width > 0 AND height > 0", name="ck_project_elements_dimensions_positive"),
    )

    page_id: Mapped[str] = mapped_column(ForeignKey("project_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("project_assets.id", ondelete="SET NULL"), index=True)
    element_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    x: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    y: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    width: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    height: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    rotation: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False, default=Decimal("0"), server_default="0")
    content: Mapped[dict | None] = mapped_column(db.JSON)


class ProjectRevision(IdMixin, db.Model):
    __tablename__ = "project_revisions"
    __table_args__ = (UniqueConstraint("project_id", "revision_number", name="uq_project_revisions_project_number"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("user_projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    document_version: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    immutable_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProjectSnapshot(IdMixin, db.Model):
    __tablename__ = "project_snapshots"
    __table_args__ = (UniqueConstraint("project_id", "snapshot_number", name="uq_project_snapshots_project_number"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("user_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("project_revisions.id", ondelete="SET NULL"), index=True)
    snapshot_number: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False, default="autosave", server_default="autosave")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProjectSetting(IdMixin, db.Model):
    __tablename__ = "project_settings"
    __table_args__ = (UniqueConstraint("project_id", "setting_key", name="uq_project_settings_project_key"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("user_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    setting_key: Mapped[str] = mapped_column(String(100), nullable=False)
    setting_value: Mapped[dict] = mapped_column(db.JSON, nullable=False)
