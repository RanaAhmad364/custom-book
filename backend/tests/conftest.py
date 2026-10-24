from __future__ import annotations

import pytest

from memorybook import create_app
from memorybook.extensions import db


@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-that-is-not-used-outside-testing",
        "JWT_SECRET_KEY": "test-only-jwt-secret-that-is-not-used-outside-testing",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "RATELIMIT_ENABLED": False,
        "RATE_LIMIT_STORAGE_URI": "memory://",
        "ENVIRONMENT": "testing",
        "MIGRATIONS_DIRECTORY": "../migrations",
        "CORS_ORIGINS": ["http://localhost:5173"],
        "LOG_LEVEL": "CRITICAL",
        "CELERY": {
            "broker_url": "memory://",
            "result_backend": "cache+memory://",
            "task_serializer": "json",
            "result_serializer": "json",
            "accept_content": ["json"],
        },
        "REDIS_URL": "redis://localhost:6379/0",
    })
    with application.app_context():
        db.create_all()
    outbox = []
    application.extensions["auth_email_outbox"] = outbox
    application.extensions["auth_email_sender"] = lambda recipient, subject, body: outbox.append(
        (recipient, subject, body)
    )
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
