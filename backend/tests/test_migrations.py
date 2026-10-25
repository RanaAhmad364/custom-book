import json
from pathlib import Path

from sqlalchemy import inspect, text

from memorybook import create_app


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
        assert {
            "full_name",
            "phone",
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
        assert "idempotency_key" in {column["name"] for column in inspector.get_columns("payments")}
        assert "checkout_url" in {column["name"] for column in inspector.get_columns("payment_attempts")}
        assert "event_key" in {column["name"] for column in inspector.get_columns("notifications")}


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
