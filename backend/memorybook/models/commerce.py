from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from memorybook.extensions import db
from memorybook.models.base import IdMixin, TimestampMixin

MONEY = Numeric(12, 2)


class PricingTier(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "pricing_tiers"
    __table_args__ = (CheckConstraint("base_price >= 0", name="ck_pricing_tiers_price_nonnegative"),)

    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    base_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    is_active: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=True, server_default="true")


class PricingRule(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "pricing_rules"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_pricing_rules_amount_nonnegative"),
        Index("ix_pricing_rules_active_window", "is_active", "starts_at", "ends_at"),
    )

    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    adjustment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    conditions: Mapped[dict] = mapped_column(db.JSON, nullable=False, default=dict)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=True, server_default="true")


class PagePricing(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "page_pricing"
    __table_args__ = (
        UniqueConstraint("tier_id", "minimum_pages", "maximum_pages", name="uq_page_pricing_tier_range"),
        CheckConstraint("minimum_pages > 0 AND maximum_pages >= minimum_pages", name="ck_page_pricing_valid_range"),
        CheckConstraint("price_per_page >= 0", name="ck_page_pricing_price_nonnegative"),
    )

    tier_id: Mapped[str] = mapped_column(ForeignKey("pricing_tiers.id", ondelete="CASCADE"), nullable=False, index=True)
    minimum_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    price_per_page: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class ShippingRate(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "shipping_rates"
    __table_args__ = (
        UniqueConstraint("country_code", "region_code", "service_code", name="uq_shipping_rates_destination_service"),
        CheckConstraint("price >= 0", name="ck_shipping_rates_price_nonnegative"),
    )

    country_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    region_code: Mapped[str | None] = mapped_column(String(20))
    service_code: Mapped[str] = mapped_column(String(40), nullable=False)
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    estimated_days_min: Mapped[int | None] = mapped_column(Integer)
    estimated_days_max: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=True, server_default="true")


class DiscountCode(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "discount_codes"
    __table_args__ = (
        CheckConstraint("value > 0", name="ck_discount_codes_value_positive"),
        CheckConstraint("maximum_uses IS NULL OR maximum_uses > 0", name="ck_discount_codes_maximum_uses_positive"),
        Index("ix_discount_codes_active_window", "is_active", "starts_at", "ends_at"),
    )

    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    discount_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    maximum_uses: Mapped[int | None] = mapped_column(Integer)
    uses_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=True, server_default="true")


class PdfOrder(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "pdf_orders"
    __table_args__ = (
        CheckConstraint("service_price >= 0 AND discount_amount >= 0 AND tax_amount >= 0 AND total_amount >= 0", name="ck_pdf_orders_amounts_nonnegative"),
        Index("ix_pdf_orders_user_created", "user_id", "created_at"),
        UniqueConstraint("idempotency_key", name="uq_pdf_orders_idempotency_key"),
    )

    order_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("user_projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_revision_id: Mapped[str] = mapped_column(ForeignKey("project_revisions.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending", index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    service_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"), server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"), server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    price_snapshot: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))


class PdfJob(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "pdf_jobs"
    __table_args__ = (
        Index("ix_pdf_jobs_status_created", "status", "created_at"),
        UniqueConstraint("order_id", "generation_profile", name="uq_pdf_jobs_order_profile"),
    )

    order_id: Mapped[str] = mapped_column(ForeignKey("pdf_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    generation_profile: Mapped[str] = mapped_column(String(20), nullable=False, default="digital", server_default="digital")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", server_default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GeneratedFile(IdMixin, db.Model):
    __tablename__ = "generated_files"
    __table_args__ = (
        UniqueConstraint("pdf_order_id", "generation_profile", name="uq_generated_files_order_profile"),
        CheckConstraint("byte_size >= 0", name="ck_generated_files_size_nonnegative"),
        CheckConstraint(
            "(pdf_order_id IS NOT NULL AND print_order_id IS NULL) OR "
            "(pdf_order_id IS NULL AND print_order_id IS NOT NULL)",
            name="ck_generated_files_exactly_one_order",
        ),
    )

    pdf_order_id: Mapped[str | None] = mapped_column(ForeignKey("pdf_orders.id", ondelete="RESTRICT"), index=True)
    print_order_id: Mapped[str | None] = mapped_column(ForeignKey("print_orders.id", ondelete="RESTRICT"), index=True)
    generation_profile: Mapped[str] = mapped_column(String(20), nullable=False, default="digital", server_default="digital")
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    file_type: Mapped[str] = mapped_column(String(80), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DownloadEntitlement(IdMixin, db.Model):
    __tablename__ = "download_entitlements"
    __table_args__ = (
        UniqueConstraint("user_id", "pdf_order_id", "generated_file_id", name="uq_download_entitlement_user_order_file"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    pdf_order_id: Mapped[str] = mapped_column(ForeignKey("pdf_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_file_id: Mapped[str | None] = mapped_column(ForeignKey("generated_files.id", ondelete="SET NULL"), index=True)
    max_downloads: Mapped[int | None] = mapped_column(Integer)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DownloadHistory(IdMixin, db.Model):
    __tablename__ = "download_history"
    __table_args__ = (Index("ix_download_history_entitlement_time", "entitlement_id", "downloaded_at"),)

    entitlement_id: Mapped[str] = mapped_column(ForeignKey("download_entitlements.id", ondelete="RESTRICT"), nullable=False, index=True)
    generated_file_id: Mapped[str] = mapped_column(ForeignKey("generated_files.id", ondelete="RESTRICT"), nullable=False)
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ip_address: Mapped[str | None] = mapped_column(String(45))


class ShippingAddress(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "shipping_addresses"
    __table_args__ = (Index("ix_shipping_addresses_user_default", "user_id", "is_default"),)

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    recipient_name: Mapped[str] = mapped_column(String(160), nullable=False)
    company: Mapped[str | None] = mapped_column(String(160))
    address_line_1: Mapped[str] = mapped_column(String(200), nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str] = mapped_column(String(30), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    is_default: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PrintOrder(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "print_orders"
    __table_args__ = (
        CheckConstraint(
            "book_amount >= 0 AND printing_amount >= 0 AND additional_pages_amount >= 0 "
            "AND shipping_amount >= 0 AND discount_amount >= 0 AND tax_amount >= 0 AND total_amount >= 0",
            name="ck_print_orders_amounts_nonnegative",
        ),
        Index("ix_print_orders_user_created", "user_id", "created_at"),
        UniqueConstraint("idempotency_key", name="uq_print_orders_idempotency_key"),
    )

    order_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("user_projects.id", ondelete="RESTRICT"), nullable=False, index=True)
    project_revision_id: Mapped[str] = mapped_column(ForeignKey("project_revisions.id", ondelete="RESTRICT"), nullable=False, index=True)
    shipping_address_id: Mapped[str] = mapped_column(ForeignKey("shipping_addresses.id", ondelete="RESTRICT"), nullable=False)
    shipping_address_snapshot: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending", index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    book_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    printing_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    additional_pages_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"), server_default="0")
    shipping_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"), server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"), server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    price_snapshot: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))


class PrintQuote(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "print_quotes"
    __table_args__ = (
        Index("ix_print_quotes_user_expiry", "user_id", "expires_at"),
        CheckConstraint("total_amount >= 0", name="ck_print_quotes_total_nonnegative"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("user_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    project_revision_id: Mapped[str] = mapped_column(ForeignKey("project_revisions.id", ondelete="RESTRICT"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    configuration: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    shipping_address_snapshot: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    price_snapshot: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PrintOrderItem(IdMixin, db.Model):
    __tablename__ = "print_order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND page_count > 0", name="ck_print_order_items_quantity_pages_positive"),
        CheckConstraint("unit_price >= 0 AND line_total >= 0", name="ck_print_order_items_amounts_nonnegative"),
    )

    print_order_id: Mapped[str] = mapped_column(ForeignKey("print_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id: Mapped[str | None] = mapped_column(ForeignKey("book_variants.id", ondelete="SET NULL"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    specification_snapshot: Mapped[dict] = mapped_column(db.JSON, nullable=False)


class PrintSpecification(IdMixin, db.Model):
    __tablename__ = "print_specifications"

    item_id: Mapped[str] = mapped_column(ForeignKey("print_order_items.id", ondelete="CASCADE"), nullable=False, unique=True)
    tier_code: Mapped[str] = mapped_column(String(40), nullable=False)
    size_name: Mapped[str] = mapped_column(String(100), nullable=False)
    cover_name: Mapped[str] = mapped_column(String(100), nullable=False)
    paper_name: Mapped[str] = mapped_column(String(100), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    specification_data: Mapped[dict] = mapped_column(db.JSON, nullable=False, default=dict)


class OrderStatusHistory(IdMixin, db.Model):
    __tablename__ = "order_status_history"
    __table_args__ = (
        CheckConstraint(
            "(pdf_order_id IS NOT NULL AND print_order_id IS NULL) OR "
            "(pdf_order_id IS NULL AND print_order_id IS NOT NULL)",
            name="ck_order_status_history_exactly_one_order",
        ),
        Index("ix_order_status_history_pdf_time", "pdf_order_id", "created_at"),
        Index("ix_order_status_history_print_time", "print_order_id", "created_at"),
    )

    pdf_order_id: Mapped[str | None] = mapped_column(ForeignKey("pdf_orders.id", ondelete="CASCADE"), index=True)
    print_order_id: Mapped[str | None] = mapped_column(ForeignKey("print_orders.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    changed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Shipment(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "shipments"

    print_order_id: Mapped[str] = mapped_column(ForeignKey("print_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    carrier: Mapped[str | None] = mapped_column(String(100))
    tracking_number: Mapped[str | None] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", server_default="pending", index=True)
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Payment(IdMixin, TimestampMixin, db.Model):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "(pdf_order_id IS NOT NULL AND print_order_id IS NULL) OR "
            "(pdf_order_id IS NULL AND print_order_id IS NOT NULL)",
            name="ck_payments_exactly_one_order",
        ),
        CheckConstraint("amount >= 0", name="ck_payments_amount_nonnegative"),
        Index("ix_payments_status_created", "status", "created_at"),
        UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        UniqueConstraint("pdf_order_id", name="uq_payments_pdf_order"),
        UniqueConstraint("print_order_id", name="uq_payments_print_order"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    pdf_order_id: Mapped[str | None] = mapped_column(ForeignKey("pdf_orders.id", ondelete="RESTRICT"), index=True)
    print_order_id: Mapped[str | None] = mapped_column(ForeignKey("print_orders.id", ondelete="RESTRICT"), index=True)
    purpose: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="order_payment",
        server_default="order_payment",
    )
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(60))
    provider_payment_id: Mapped[str | None] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending", index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))


class PaymentAttempt(IdMixin, db.Model):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        Index("ix_payment_attempts_payment_created", "payment_id", "created_at"),
        UniqueConstraint("payment_id", "attempt_number", name="uq_payment_attempts_payment_number"),
        UniqueConstraint("payment_id", "idempotency_key", name="uq_payment_attempts_idempotency_key"),
    )

    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(160))
    checkout_url: Mapped[str | None] = mapped_column(String(2048))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    failure_code: Mapped[str | None] = mapped_column(String(80))
    failure_message: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PaymentWebhookEvent(IdMixin, db.Model):
    __tablename__ = "payment_webhook_events"
    __table_args__ = (UniqueConstraint("provider", "provider_event_id", name="uq_payment_webhook_provider_event"),)

    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict] = mapped_column(db.JSON, nullable=False)
    signature_verified: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=False, server_default="false")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Refund(IdMixin, db.Model):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_refunds_amount_positive"),
        UniqueConstraint("idempotency_key", name="uq_refunds_idempotency_key"),
    )

    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False, index=True)
    provider_refund_id: Mapped[str | None] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", server_default="pending")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Invoice(IdMixin, db.Model):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "(pdf_order_id IS NOT NULL AND print_order_id IS NULL) OR "
            "(pdf_order_id IS NULL AND print_order_id IS NOT NULL)",
            name="ck_invoices_exactly_one_order",
        ),
        CheckConstraint("amount >= 0", name="ck_invoices_amount_nonnegative"),
    )

    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False, index=True)
    pdf_order_id: Mapped[str | None] = mapped_column(ForeignKey("pdf_orders.id", ondelete="RESTRICT"), index=True)
    print_order_id: Mapped[str | None] = mapped_column(ForeignKey("print_orders.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    document_storage_key: Mapped[str | None] = mapped_column(String(1024))
