from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from memorybook.extensions import db
from memorybook.models.base import IdMixin, SoftDeleteMixin, TimestampMixin


class BookCategory(IdMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "book_categories"
    __table_args__ = (UniqueConstraint("slug", name="uq_book_categories_slug"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    style: Mapped[str | None] = mapped_column(String(60))
    hero_asset_key: Mapped[str | None] = mapped_column(String(1024))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class BookCollection(IdMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "book_collections"
    __table_args__ = (UniqueConstraint("slug", name="uq_book_collections_slug"),)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    hero_asset_key: Mapped[str | None] = mapped_column(String(1024))
    eyebrow: Mapped[str | None] = mapped_column(String(120))
    recommended_layouts: Mapped[list | None] = mapped_column(db.JSON)
    related_categories: Mapped[list | None] = mapped_column(db.JSON)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class BookProduct(IdMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "book_products"
    __table_args__ = (
        Index("ix_book_products_category_active", "category_id", "is_active"),
        CheckConstraint("starting_price >= 0", name="ck_book_products_starting_price_nonnegative"),
    )

    category_id: Mapped[str] = mapped_column(ForeignKey("book_categories.id", ondelete="RESTRICT"), nullable=False, index=True)
    collection_id: Mapped[str | None] = mapped_column(ForeignKey("book_collections.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    style: Mapped[str | None] = mapped_column(String(60), index=True)
    occasion: Mapped[str | None] = mapped_column(String(60), index=True)
    book_type: Mapped[str | None] = mapped_column(String(40), index=True)
    page_count_min: Mapped[int | None] = mapped_column(Integer)
    page_count_max: Mapped[int | None] = mapped_column(Integer)
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    cover_asset_key: Mapped[str | None] = mapped_column(String(1024))
    starting_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    admin_metadata: Mapped[dict | None] = mapped_column(db.JSON)


class BookTemplate(IdMixin, TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "book_templates"

    product_id: Mapped[str | None] = mapped_column(ForeignKey("book_products.id", ondelete="SET NULL"), index=True)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("book_categories.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    preview_asset_key: Mapped[str | None] = mapped_column(String(1024))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    design_document: Mapped[dict | None] = mapped_column(db.JSON)
    published_design_document: Mapped[dict | None] = mapped_column(db.JSON)
    published_version: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class BookTemplateVersion(IdMixin, db.Model):
    __tablename__ = "book_template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_book_template_versions_number"),)

    template_id: Mapped[str] = mapped_column(
        ForeignKey("book_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TemplatePage(IdMixin, db.Model):
    __tablename__ = "template_pages"
    __table_args__ = (
        UniqueConstraint("template_id", "page_number", name="uq_template_pages_template_number"),
        CheckConstraint("page_number > 0", name="ck_template_pages_page_number_positive"),
    )

    template_id: Mapped[str] = mapped_column(ForeignKey("book_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_type: Mapped[str] = mapped_column(String(30), nullable=False, default="interior", server_default="interior")
    layout_key: Mapped[str] = mapped_column(String(100), nullable=False)
    background: Mapped[str | None] = mapped_column(String(100))


class TemplateElement(IdMixin, db.Model):
    __tablename__ = "template_elements"
    __table_args__ = (
        Index("ix_template_elements_page_order", "template_page_id", "sort_order"),
        CheckConstraint("width > 0 AND height > 0", name="ck_template_elements_dimensions_positive"),
    )

    template_page_id: Mapped[str] = mapped_column(ForeignKey("template_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    element_type: Mapped[str] = mapped_column(String(30), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    x: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    y: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    width: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    height: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    content: Mapped[dict | None] = mapped_column(db.JSON)


class BookSize(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "book_sizes"
    __table_args__ = (
        UniqueConstraint("code", name="uq_book_sizes_code"),
        CheckConstraint("width_mm > 0 AND height_mm > 0", name="ck_book_sizes_dimensions_positive"),
    )

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    width_mm: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    height_mm: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class CoverType(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "cover_types"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class PaperType(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "paper_types"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    weight_gsm: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class BookVariant(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "book_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "size_id", "cover_type_id", "paper_type_id", name="uq_book_variant_specification"),
        CheckConstraint("base_price >= 0", name="ck_book_variants_base_price_nonnegative"),
    )

    product_id: Mapped[str] = mapped_column(ForeignKey("book_products.id", ondelete="CASCADE"), nullable=False, index=True)
    size_id: Mapped[str] = mapped_column(ForeignKey("book_sizes.id", ondelete="RESTRICT"), nullable=False)
    cover_type_id: Mapped[str] = mapped_column(ForeignKey("cover_types.id", ondelete="RESTRICT"), nullable=False)
    paper_type_id: Mapped[str] = mapped_column(ForeignKey("paper_types.id", ondelete="RESTRICT"), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
