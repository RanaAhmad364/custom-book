from pathlib import Path

import pytest


def test_live_health_and_security_headers(client):
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "qa-request_13"})

    assert response.status_code == 200
    assert response.json == {"status": "ok", "apiVersion": "v1"}
    assert response.headers["X-Request-ID"] == "qa-request_13"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"


def test_invalid_request_id_is_replaced(client):
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "invalid request id"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "invalid request id"


def test_database_readiness(client):
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json == {"status": "ready", "dependencies": {"database": "available"}}


def test_health_endpoint_remains_outside_auth():
    from memorybook import create_app

    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-that-is-not-used-outside-testing",
        "JWT_SECRET_KEY": "test-only-jwt-secret-that-is-not-used-outside-testing",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "MIGRATIONS_DIRECTORY": "../migrations",
        "CORS_ORIGINS": [],
        "LOG_LEVEL": "CRITICAL",
        "ENVIRONMENT": "testing",
        "CELERY": {"broker_url": "memory://", "result_backend": "cache+memory://"},
        "REDIS_URL": "redis://localhost:6379/0",
    })
    assert app.test_client().get("/api/v1/health/live").status_code == 200


def test_default_rate_limits_parse_and_allow_health_request():
    from memorybook import create_app

    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-that-is-not-used-outside-testing",
        "JWT_SECRET_KEY": "test-only-jwt-secret-that-is-not-used-outside-testing",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "MIGRATIONS_DIRECTORY": "../migrations",
        "CORS_ORIGINS": [],
        "LOG_LEVEL": "CRITICAL",
        "ENVIRONMENT": "testing",
        "RATE_LIMIT_STORAGE_URI": "memory://",
        "RATELIMIT_STORAGE_URI": "memory://",
        "RATELIMIT_DEFAULT": "200 per day; 60 per hour",
        "RATELIMIT_ENABLED": True,
        "CELERY": {"broker_url": "memory://", "result_backend": "cache+memory://"},
        "REDIS_URL": "redis://localhost:6379/0",
    })

    assert app.test_client().get("/api/v1/health/live").status_code == 200


def test_configured_trusted_proxy_hops_control_forwarded_client_address():
    from flask import request

    from memorybook import create_app

    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-that-is-not-used-outside-testing",
        "JWT_SECRET_KEY": "test-only-jwt-secret-that-is-not-used-outside-testing",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "MIGRATIONS_DIRECTORY": "../migrations",
        "CORS_ORIGINS": [],
        "LOG_LEVEL": "CRITICAL",
        "ENVIRONMENT": "testing",
        "TRUSTED_PROXY_HOPS": 1,
        "CELERY": {"broker_url": "memory://", "result_backend": "cache+memory://"},
        "REDIS_URL": "redis://localhost:6379/0",
    })
    app.add_url_rule("/test/remote-address", view_func=lambda: request.remote_addr)

    response = app.test_client().get(
        "/test/remote-address",
        headers={"X-Forwarded-For": "198.51.100.23"},
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    )

    assert response.get_data(as_text=True) == "198.51.100.23"


def test_production_filesystem_assets_require_an_external_absolute_directory():
    from flask import Flask

    from memorybook import _validate_configuration

    application_directory = Path(__file__).resolve().parents[2]
    app = Flask(__name__)
    app.config.update(
        ENVIRONMENT="production",
        SECRET_KEY="production-secret-key-that-is-at-least-thirty-two-characters",
        JWT_SECRET_KEY="production-jwt-secret-that-is-at-least-thirty-two-characters",
        SQLALCHEMY_DATABASE_URI="postgresql+psycopg://user:password@localhost/memorybook",
        AUTH_EMAIL_MODE="smtp",
        SMTP_USE_TLS=False,
        SMTP_USE_SSL=False,
        BACKGROUND_JOB_BACKEND="inprocess",
        ASSET_STORAGE_BACKEND="filesystem",
        ASSET_LOCAL_DIRECTORY=str(application_directory.parent / ".memorybook-test-assets"),
        ASSET_S3_PRESIGNED_URL_TTL=900,
        RATE_LIMIT_STORAGE_URI="redis://localhost:6379/2",
        JWT_COOKIE_SECURE=True,
    )

    _validate_configuration(app)
    with app.app_context():
        from memorybook.integrations.asset_storage import (
            LocalFilesystemAssetStorage,
            get_asset_storage,
        )

        assert isinstance(get_asset_storage(), LocalFilesystemAssetStorage)

    app.config["ASSET_LOCAL_DIRECTORY"] = str(application_directory)
    with pytest.raises(RuntimeError, match="outside the application directory"):
        _validate_configuration(app)


def test_unhandled_route_uses_structured_not_found_response(client):
    response = client.get("/api/v1/not-a-route")

    assert response.status_code == 404
    assert response.json["error"]["code"] == "NOT_FOUND"
    assert response.json["requestId"]


def test_cors_preflight_is_limited_to_configured_frontend(client):
    response = client.options(
        "/api/v1/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"


def test_backend_cli_checks_are_registered(app):
    runner = app.test_cli_runner()

    config_result = runner.invoke(args=["config-check"])
    database_result = runner.invoke(args=["db-check"])

    assert config_result.exit_code == 0
    assert "configuration is valid" in config_result.output
    assert database_result.exit_code == 0
    assert "Database connection successful" in database_result.output


def test_local_app_uses_in_process_jobs_without_redis_or_celery(app):
    assert app.config["BACKGROUND_JOB_BACKEND"] == "inprocess"
    assert "background_jobs" in app.extensions
    assert "celery" not in app.extensions
    assert "redis" not in app.extensions
