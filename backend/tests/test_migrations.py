import json
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

from memorybook import create_app
from memorybook.extensions import db
from memorybook.models import (
    BookCategory,
    BookProduct,
    BookSize,
    BookVariant,
    CoverType,
    DiscountCode,
    PagePricing,
    PaperType,
    PdfOrder,
    PricingTier,
    ProjectRevision,
    ShippingRate,
    User,
    UserProject,
)


EXPECTED_SCHEMA_TABLES = {
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
    "book_template_versions",
    "template_pages",
    "template_elements",
    "book_variants",
    "book_sizes",
    "cover_types",
    "paper_types",
    "user_projects",
    "project_pages",
    "project_assets",
    "project_elements",
    "project_revisions",
    "project_snapshots",
    "project_settings",
    "pricing_tiers",
    "pricing_rules",
    "page_pricing",
    "shipping_rates",
    "discount_codes",
    "pdf_orders",
    "pdf_jobs",
    "generated_files",
    "download_entitlements",
    "download_history",
    "print_orders",
    "print_quotes",
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
    "background_jobs",
}


def test_initial_migration_upgrades_database(tmp_path):
    database_path = tmp_path / "migration-test.sqlite"
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-that-is-not-used-outside-testing",
        "JWT_SECRET_KEY": "test-only-jwt-secret-that-is-not-used-outside-testing",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "MIGRATIONS_DIRECTORY": str(Path(__file__).resolve().parents[1] / "migrations"),
        "CORS_ORIGINS": [],
        "LOG_LEVEL": "CRITICAL",
        "CELERY": {"broker_url": "memory://", "result_backend": "cache+memory://"},
        "REDIS_URL": "redis://localhost:6379/0",
    })

    result = app.test_cli_runner().invoke(args=["db", "upgrade"])

    assert result.exit_code == 0, result.output
    with app.app_context():
        inspector = inspect(app.extensions["sqlalchemy"].engine)
        assert EXPECTED_SCHEMA_TABLES.issubset(inspector.get_table_names())
        assert "alembic_version" in inspector.get_table_names()
        assert "code" in {column["name"] for column in inspector.get_columns("cover_types")}
        assert "code" in {column["name"] for column in inspector.get_columns("paper_types")}
        assert "per_copy" in {column["name"] for column in inspector.get_columns("shipping_rates")}
        assert {
            "full_name",
            "phone",
            "privacy_mode",
            "email_verified_at",
            "updated_at",
            "deleted_at",
        }.issubset({column["name"] for column in inspector.get_columns("users")})
        assert {
            "purpose",
            "attempts",
            "consumed_at",
        }.issubset({column["name"] for column in inspector.get_columns("email_verifications")})
        assert {"version", "document"}.issubset(
            {column["name"] for column in inspector.get_columns("user_projects")}
        )
        assert {"label", "elements"}.issubset(
            {column["name"] for column in inspector.get_columns("project_pages")}
        )
        assert {"occasion", "book_type", "page_count_min", "page_count_max", "is_featured"}.issubset(
            {column["name"] for column in inspector.get_columns("book_products")}
        )
        assert "admin_metadata" in {column["name"] for column in inspector.get_columns("book_products")}
        assert "template_version" in {column["name"] for column in inspector.get_columns("user_projects")}
        assert "privacy_override" in {column["name"] for column in inspector.get_columns("user_projects")}
        assert "original_deleted_at" in {column["name"] for column in inspector.get_columns("project_assets")}
        assert "idempotency_key" in {column["name"] for column in inspector.get_columns("payments")}
        assert {
            "pkr_amount",
            "usd_amount",
            "exchange_rate",
            "provider_capture_id",
            "provider_capture_amount",
            "provider_capture_currency",
        }.issubset({column["name"] for column in inspector.get_columns("payments")})
        assert "consent_at" in {column["name"] for column in inspector.get_columns("print_orders")}
        assert "checkout_url" in {column["name"] for column in inspector.get_columns("payment_attempts")}
        assert "event_key" in {column["name"] for column in inspector.get_columns("notifications")}


def test_usd_catalog_migration_converts_active_prices_and_preserves_paid_order_currency(app):
    with app.app_context():
        category = BookCategory(name="Migration", slug="migration-usd")
        db.session.add(category)
        tier = PricingTier(code="BASIC", name="Basic", base_price=Decimal("4000"), currency="PKR")
        size = BookSize(code="MIGRATION_SIZE", name="Migration", width_mm=Decimal("200"), height_mm=Decimal("200"))
        cover = CoverType(code="hardcover", name="Hardcover")
        paper = PaperType(code="standard", name="Standard")
        shipping = ShippingRate(
            country_code="PK", service_code="standard", service_name="Standard",
            price=Decimal("1000"), currency="PKR",
        )
        fixed_discount = DiscountCode(
            code="FIXEDUSD", discount_type="fixed", value=Decimal("500"), currency="PKR",
        )
        percent_discount = DiscountCode(
            code="PERCENTUSD", discount_type="percent", value=Decimal("15"), currency="PKR",
        )
        db.session.add_all([tier, size, cover, paper, shipping, fixed_discount, percent_discount])
        db.session.flush()
        band = PagePricing(
            tier_id=tier.id, minimum_pages=24, maximum_pages=80, price_per_page=Decimal("25"),
        )
        product = BookProduct(
            category_id=category.id,
            title="Migration book",
            slug="migration-usd-book",
            description="Migration fixture",
            book_type="BASIC",
            starting_price=Decimal("5000"),
            currency="PKR",
            admin_metadata={"pdfPrice": "500", "printingPrice": "2500"},
        )
        db.session.add_all([band, product])
        db.session.flush()
        variant = BookVariant(
            product_id=product.id,
            size_id=size.id,
            cover_type_id=cover.id,
            paper_type_id=paper.id,
            sku="MIGRATION-USD",
            base_price=Decimal("2500"),
            currency="PKR",
        )
        user = User(email="migration-usd@example.test", password_hash="test-hash")
        db.session.add_all([variant, user])
        db.session.flush()
        project = UserProject(
            user_id=user.id, title="Migration project", page_count=24, version=1, document={"pages": []},
        )
        db.session.add(project)
        db.session.flush()
        revision = ProjectRevision(
            project_id=project.id,
            revision_number=1,
            document_version=1,
            document={"pages": []},
            checksum_sha256="a" * 64,
        )
        db.session.add(revision)
        db.session.flush()
        paid_order = PdfOrder(
            order_number="MIGRATION-PAID-ORDER",
            user_id=user.id,
            project_id=project.id,
            project_revision_id=revision.id,
            status="paid",
            currency="PKR",
            service_price=Decimal("5000"),
            total_amount=Decimal("5000"),
            price_snapshot={"total": "5000.00"},
            page_count=24,
            paid_at=datetime.now(UTC),
        )
        db.session.add(paid_order)
        db.session.commit()

        migration_path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0c5d8a2f71b4_usd_catalog_pricing.py"
        spec = importlib.util.spec_from_file_location("usd_catalog_pricing_migration", migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with db.engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()

        db.session.expire_all()
        assert db.session.get(PricingTier, tier.id).base_price == Decimal("40.00")
        assert db.session.get(PricingTier, tier.id).currency == "USD"
        assert db.session.get(PagePricing, band.id).price_per_page == Decimal("0.25")
        assert db.session.get(ShippingRate, shipping.id).price == Decimal("5.99")
        assert db.session.get(DiscountCode, fixed_discount.id).value == Decimal("5.00")
        assert db.session.get(DiscountCode, fixed_discount.id).currency == "USD"
        assert db.session.get(DiscountCode, percent_discount.id).value == Decimal("15.00")
        assert db.session.get(DiscountCode, percent_discount.id).currency is None
        migrated_product = db.session.get(BookProduct, product.id)
        assert migrated_product.starting_price == Decimal("30.00")
        assert migrated_product.currency == "USD"
        assert migrated_product.admin_metadata["pdfPrice"] == "5.99"
        assert db.session.get(BookVariant, variant.id).base_price == Decimal("10.00")
        assert db.session.get(BookVariant, variant.id).currency == "USD"
        assert db.session.get(PdfOrder, paid_order.id).currency == "PKR"


def test_collection_category_migration_maps_only_unambiguous_legacy_references(tmp_path):
    database_path = tmp_path / "collection-category-migration.sqlite"
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-that-is-not-used-outside-testing",
        "JWT_SECRET_KEY": "test-only-jwt-secret-that-is-not-used-outside-testing",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "MIGRATIONS_DIRECTORY": str(Path(__file__).resolve().parents[1] / "migrations"),
        "CORS_ORIGINS": [],
        "LOG_LEVEL": "CRITICAL",
        "CELERY": {"broker_url": "memory://", "result_backend": "cache+memory://"},
        "REDIS_URL": "redis://localhost:6379/0",
    })
    runner = app.test_cli_runner()
    before_migration = runner.invoke(args=["db", "upgrade", "4bc81f02d9a7"])
    assert before_migration.exit_code == 0, before_migration.output

    categories = [
        ("00000000-0000-4000-8000-000000000001", "Travel", "travel"),
        ("00000000-0000-4000-8000-000000000002", "Rare", "rare"),
        ("00000000-0000-4000-8000-000000000003", "Echo", "echo"),
        ("00000000-0000-4000-8000-000000000004", "Echo", "echo-two"),
    ]
    collections = [
        ("00000000-0000-4000-8000-000000000101", "by-id", [categories[0][0]]),
        ("00000000-0000-4000-8000-000000000102", "by-slug", ["travel"]),
        ("00000000-0000-4000-8000-000000000103", "by-name", ["Rare"]),
        ("00000000-0000-4000-8000-000000000104", "stale", ["unknown"]),
        ("00000000-0000-4000-8000-000000000105", "multiple", ["travel", "rare"]),
        ("00000000-0000-4000-8000-000000000106", "ambiguous", ["Echo"]),
        ("00000000-0000-4000-8000-000000000107", "empty", []),
    ]
    with app.app_context():
        engine = app.extensions["sqlalchemy"].engine
        with engine.begin() as connection:
            for category_id, name, slug in categories:
                connection.execute(
                    text(
                        "INSERT INTO book_categories (id, name, slug, created_at, updated_at) "
                        "VALUES (:id, :name, :slug, :created_at, :updated_at)"
                    ),
                    {
                        "id": category_id,
                        "name": name,
                        "slug": slug,
                        "created_at": "2025-01-01 00:00:00",
                        "updated_at": "2025-01-01 00:00:00",
                    },
                )
            for collection_id, slug, references in collections:
                connection.execute(
                    text(
                        "INSERT INTO book_collections "
                        "(id, name, slug, related_categories, created_at, updated_at) "
                        "VALUES (:id, :name, :slug, :references, :created_at, :updated_at)"
                    ),
                    {
                        "id": collection_id,
                        "name": slug,
                        "slug": slug,
                        "references": json.dumps(references),
                        "created_at": "2025-01-01 00:00:00",
                        "updated_at": "2025-01-01 00:00:00",
                    },
                )

    migrated = runner.invoke(args=["db", "upgrade"])
    assert migrated.exit_code == 0, migrated.output
    with app.app_context():
        engine = app.extensions["sqlalchemy"].engine
        with engine.connect() as connection:
            assigned = dict(connection.execute(
                text("SELECT slug, category_id FROM book_collections")
            ).all())
        assert assigned["by-id"] == categories[0][0]
        assert assigned["by-slug"] == categories[0][0]
        assert assigned["by-name"] == categories[1][0]
        assert assigned["stale"] is None
        assert assigned["multiple"] is None
        assert assigned["ambiguous"] is None
        assert assigned["empty"] is None
        inspector = inspect(engine)
        assert {"related_categories", "category_id"}.issubset(
            {column["name"] for column in inspector.get_columns("book_collections")}
        )
        assert any(
            foreign_key["referred_table"] == "book_categories"
            and foreign_key["constrained_columns"] == ["category_id"]
            for foreign_key in inspector.get_foreign_keys("book_collections")
        )
        assert "ix_book_collections_category_id" in {
            index["name"] for index in inspector.get_indexes("book_collections")
        }
