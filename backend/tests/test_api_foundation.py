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
