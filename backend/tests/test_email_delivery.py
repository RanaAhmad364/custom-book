import smtplib
import sys

import pytest

from memorybook.errors import ServiceUnavailableError
from memorybook.integrations import email


class FakeSMTP:
    def __init__(self, *_args, **_kwargs):
        self.started_tls = False
        self.logged_in = False
        self.sent = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, _username, _password):
        self.logged_in = True

    def send_message(self, _message):
        self.sent = True


def configure_smtp(app, **overrides):
    app.extensions.pop("auth_email_sender", None)
    config = {
        "AUTH_EMAIL_MODE": "smtp",
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": 587,
        "SMTP_USERNAME": "mail-user",
        "SMTP_PASSWORD": "test-only-private-marker",
        "SMTP_FROM_EMAIL": "MemoryBook <no-reply@example.test>",
        "SMTP_USE_TLS": True,
        "SMTP_USE_SSL": False,
        **overrides,
    }
    app.config.update(config)


def test_smtp_587_uses_starttls_without_implicit_ssl(app, monkeypatch):
    connection = FakeSMTP()
    monkeypatch.setattr(email.smtplib, "SMTP", lambda *_args, **_kwargs: connection)

    with app.app_context():
        configure_smtp(app)
        email.send_email("reader@example.test", "Subject", "Message")

    assert connection.started_tls
    assert connection.logged_in
    assert connection.sent


def test_smtp_465_uses_ssl_without_starttls(app, monkeypatch):
    connection = FakeSMTP()
    calls = []

    def create_ssl(*args, **kwargs):
        calls.append((args, kwargs))
        return connection

    monkeypatch.setattr(email.smtplib, "SMTP_SSL", create_ssl)

    with app.app_context():
        configure_smtp(
            app,
            SMTP_PORT=465,
            SMTP_USE_TLS=False,
            SMTP_USE_SSL=True,
        )
        email.send_email("reader@example.test", "Subject", "Message")

    assert calls[0][0] == ("smtp.example.test", 465)
    assert "context" in calls[0][1]
    assert not connection.started_tls
    assert connection.sent


def test_smtp_failure_logs_exception_and_returns_safe_user_message(app, monkeypatch):
    class FailingSMTP(FakeSMTP):
        def send_message(self, _message):
            raise smtplib.SMTPRecipientsRefused({"reader@example.test": (550, b"sender rejected")})

    monkeypatch.setattr(email.smtplib, "SMTP", lambda *_args, **_kwargs: FailingSMTP())
    logged = []

    def capture_exception(message):
        logged.append((message, sys.exc_info()[1]))

    with app.app_context():
        monkeypatch.setattr(app.logger, "exception", capture_exception)
        configure_smtp(app)
        with pytest.raises(ServiceUnavailableError, match="Email delivery failed"):
            email.send_email("reader@example.test", "Subject", "Message")

    assert logged[0][0] == "Authentication email delivery failed."
    assert isinstance(logged[0][1], smtplib.SMTPRecipientsRefused)
    assert "test-only-private-marker" not in str(logged[0][1])
