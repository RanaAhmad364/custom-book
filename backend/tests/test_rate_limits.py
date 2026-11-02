from datetime import UTC, datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token

from memorybook import create_app
from memorybook.extensions import db
from memorybook.models import User, UserSession


@pytest.fixture()
def rate_limit_app(tmp_path):
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-that-is-not-used-outside-testing",
        "JWT_SECRET_KEY": "test-only-jwt-secret-that-is-not-used-outside-testing",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'rate-limit.sqlite').as_posix()}",
        "MIGRATIONS_DIRECTORY": "../migrations",
        "CORS_ORIGINS": [],
        "LOG_LEVEL": "CRITICAL",
        "RATELIMIT_ENABLED": True,
        "RATELIMIT_DEFAULT": "2000 per day; 300 per hour",
        "RATELIMIT_HEADERS_ENABLED": True,
        "RATE_LIMIT_STORAGE_URI": "memory://",
        "CELERY": {"broker_url": "memory://", "result_backend": "cache+memory://"},
        "REDIS_URL": "redis://localhost:6379/0",
    })
    with application.app_context():
        db.create_all()
        users = [
            User(
                email=f"rate-limit-{index}@example.test",
                password_hash="unused",
                email_verified_at=datetime.now(UTC),
            )
            for index in (1, 2)
        ]
        db.session.add_all(users)
        db.session.commit()
        sessions = [
            UserSession(
                user_id=user.id,
                session_key_hash=f"rate-limit-test-session-{index}",
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
            for index, user in enumerate(users, start=1)
        ]
        db.session.add_all(sessions)
        db.session.commit()
        tokens = [
            create_access_token(identity=user.id, additional_claims={"sid": session.id})
            for user, session in zip(users, sessions)
        ]
    application.config["RATE_LIMIT_TEST_TOKENS"] = tokens
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_order_status_polling_allows_100_requests(rate_limit_app):
    client = rate_limit_app.test_client()
    token = rate_limit_app.config["RATE_LIMIT_TEST_TOKENS"][0]

    responses = [
        client.get("/api/v1/pdf/orders/not-an-order", headers=_headers(token))
        for _ in range(100)
    ]

    assert all(response.status_code == 404 for response in responses)


def test_private_asset_route_allows_100_requests(rate_limit_app, monkeypatch):
    class TestStorage:
        def download_token(self, _token):
            return "projects/not-owned/photo.jpg"

    monkeypatch.setattr(
        "memorybook.api.v1.assets.get_asset_storage",
        lambda: TestStorage(),
    )
    client = rate_limit_app.test_client()
    token = rate_limit_app.config["RATE_LIMIT_TEST_TOKENS"][0]

    responses = [
        client.get("/api/v1/assets/private/test-token", headers=_headers(token))
        for _ in range(100)
    ]

    assert all(response.status_code == 404 for response in responses)


def test_auth_and_payment_action_limits_remain_strict(rate_limit_app):
    client = rate_limit_app.test_client()
    token = rate_limit_app.config["RATE_LIMIT_TEST_TOKENS"][0]

    login_responses = [
        client.post("/api/v1/auth/login", json={"email": "missing@example.test", "password": "wrong"})
        for _ in range(11)
    ]
    payment_responses = [
        client.post(
            "/api/v1/payments/not-a-payment/paypal/create-order",
            headers=_headers(token),
        )
        for _ in range(11)
    ]

    assert login_responses[-1].status_code == 429
    assert payment_responses[-1].status_code == 429


def test_authenticated_users_have_separate_counters_on_shared_ip(rate_limit_app):
    client = rate_limit_app.test_client()
    first, second = rate_limit_app.config["RATE_LIMIT_TEST_TOKENS"]

    first_responses = [
        client.post(
            "/api/v1/payments/not-a-payment/paypal/create-order",
            headers=_headers(first),
        )
        for _ in range(10)
    ]
    second_response = client.post(
        "/api/v1/payments/not-a-payment/paypal/create-order",
        headers=_headers(second),
    )
    first_retry = client.post(
        "/api/v1/payments/not-a-payment/paypal/create-order",
        headers=_headers(first),
    )

    assert all(response.status_code == 404 for response in first_responses)
    assert second_response.status_code == 404
    assert first_retry.status_code == 429
    assert first_retry.json["error"]["message"] == (
        "You are making requests too quickly. Please wait a moment and try again."
    )
    assert first_retry.headers.get("Retry-After")
