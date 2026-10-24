from pathlib import Path

from sqlalchemy import inspect

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
