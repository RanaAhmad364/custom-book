from sqlalchemy import LargeBinary, Numeric

from memorybook.extensions import db
from memorybook.models import BookProduct, PdfOrder, Payment, PrintOrder, ProjectAsset, ProjectRevision, ProjectPage, UserProject


def test_database_schema_covers_all_requested_domains():
    expected_tables = {
        "users",
        "roles",
        "user_roles",
        "email_verifications",
        "password_reset_tokens",
        "refresh_tokens",
        "user_sessions",
        "book_categories",
        "book_collections",
        "book_products",
        "book_templates",
        "template_pages",
        "template_elements",
        "book_variants",
        "book_sizes",
        "cover_types",
        "paper_types",
        "user_projects",
        "project_pages",
        "project_assets",
        "project_revisions",
        "project_snapshots",
        "project_settings",
        "pricing_tiers",
        "pricing_rules",
        "page_pricing",
        "shipping_rates",
        "discount_codes",
        "pdf_orders",
        "print_quotes",
        "pdf_jobs",
        "generated_files",
        "download_entitlements",
        "download_history",
        "print_orders",
        "print_order_items",
        "print_specifications",
        "order_status_history",
        "shipments",
        "shipping_addresses",
        "payments",
        "payment_attempts",
        "payment_webhook_events",
        "refunds",
        "invoices",
        "notifications",
        "email_logs",
        "notification_preferences",
        "admin_activity_logs",
        "platform_settings",
        "support_tickets",
        "support_messages",
    }

    assert expected_tables.issubset(db.metadata.tables)


def test_purchase_orders_reference_immutable_project_revisions():
    for model in (PdfOrder, PrintOrder):
        revision_fk = next(
            foreign_key
            for foreign_key in model.__table__.foreign_keys
            if foreign_key.target_fullname == "project_revisions.id"
        )
        assert revision_fk.ondelete == "RESTRICT"

    assert "document" in ProjectRevision.__table__.columns
    assert "checksum_sha256" in ProjectRevision.__table__.columns


def test_currency_and_asset_storage_use_safe_database_types():
    assert isinstance(PdfOrder.__table__.c.total_amount.type, Numeric)
    assert PdfOrder.__table__.c.total_amount.type.precision == 12
    assert PdfOrder.__table__.c.total_amount.type.scale == 2
    assert isinstance(PrintOrder.__table__.c.total_amount.type, Numeric)
    assert "storage_key" in ProjectAsset.__table__.columns
    assert all(not isinstance(column.type, LargeBinary) for column in ProjectAsset.__table__.columns)
    assert all(not isinstance(column.type, LargeBinary) for column in PdfOrder.__table__.columns)
    assert "version" in UserProject.__table__.columns
    assert "document" in UserProject.__table__.columns
    assert "elements" in ProjectPage.__table__.columns
    assert "occasion" in BookProduct.__table__.columns
    assert "is_featured" in BookProduct.__table__.columns


def test_payment_and_generated_file_enforce_single_order_target():
    for table in ("payments", "generated_files", "order_status_history", "invoices"):
        check_names = {constraint.name for constraint in db.metadata.tables[table].constraints}
        assert f"ck_{table}_exactly_one_order" in check_names
