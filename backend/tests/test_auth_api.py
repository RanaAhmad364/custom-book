import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse, parse_qs

from flask import Blueprint

from memorybook.errors import ServiceUnavailableError
from memorybook.extensions import db
from memorybook.models import (
    EmailVerification,
    PasswordResetToken,
    RefreshToken,
    Role,
    User,
    UserSession,
    UserRole,
)
from memorybook.permissions import roles_required

PASSWORD = "correct-horse-battery"
EMAIL = "person@example.test"


def cookie_value(response, name):
    for header in response.headers.getlist("Set-Cookie"):
        if header.startswith(f"{name}="):
            return header.split(";", 1)[0].split("=", 1)[1]
    return None


def csrf_header(response, cookie_name):
    value = cookie_value(response, cookie_name)
    assert value
    return {"X-CSRF-TOKEN": value}


def register(client, email=EMAIL, password=PASSWORD, name=""):
    return client.post("/api/v1/auth/register", json={"email": email, "password": password, "name": name})


def unavailable_email_sender(*_args):
    raise ServiceUnavailableError("mail unavailable")


def verification_code(app, recipient=EMAIL, message_index=-1):
    message = app.extensions["auth_email_outbox"][message_index][2]
    match = re.search(r"\b(\d{6})\b", message)
    assert match
    return match.group(1)


def verify_email(app, client, email=EMAIL):
    return client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "code": verification_code(app, email)},
    )


def register_verified(app, client, email=EMAIL):
    response = register(client, email=email)
    assert response.status_code == 201
    verified = verify_email(app, client, email)
    assert verified.status_code == 200
    return response.json["user"]


def test_registration_issues_secure_otp_and_never_exposes_password_hash(app, client):
    response = register(client, email="  Person@Example.Test ", name="Book Maker")

    assert response.status_code == 201
    assert response.json["user"]["email"] == "person@example.test"
    assert "password_hash" not in response.json["user"]
    assert "passwordHash" not in response.json["user"]
    with app.app_context():
        user = db.session.get(User, response.json["user"]["id"])
        verification = db.session.scalar(db.select(EmailVerification))
        assert user.password_hash != PASSWORD
        assert user.password_hash.startswith("scrypt:")
        assert user.full_name == "Book Maker"
        assert verification.token_hash != verification_code(app)
        assert verification.expires_at.replace(tzinfo=UTC) > datetime.now(UTC)


def test_registration_rejects_duplicate_email_case_insensitively(client):
    assert register(client).status_code == 201

    response = register(client, email="PERSON@example.test")

    assert response.status_code == 409
    assert response.json["error"]["code"] == "CONFLICT"


def test_invalid_registration_payload_is_structured(client):
    response = register(client, email="not-an-email", password="short")

    assert response.status_code == 400
    assert response.json["error"]["details"]["email"] == "invalid"


def test_login_requires_verified_email_and_rotates_refresh_cookie(app, client):
    register(client)
    unverified_login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert unverified_login.status_code == 403
    assert unverified_login.json["error"]["code"] == "EMAIL_NOT_VERIFIED"
    assert verify_email(app, client).status_code == 200

    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

    assert login_response.status_code == 200
    assert login_response.json["user"]["email"] == EMAIL
    assert "accessToken" not in login_response.json
    assert "refreshToken" not in login_response.json
    access_cookie = cookie_value(login_response, "access_token_cookie")
    refresh_cookie = cookie_value(login_response, "refresh_token_cookie")
    original_refresh_csrf = cookie_value(login_response, "csrf_refresh_token")
    assert access_cookie and refresh_cookie
    assert "HttpOnly" in ";".join(login_response.headers.getlist("Set-Cookie"))

    me_response = client.get("/api/v1/auth/me")
    refresh_response = client.post(
        "/api/v1/auth/refresh",
        headers=csrf_header(login_response, "csrf_refresh_token"),
    )
    assert me_response.status_code == 200
    assert me_response.json["user"]["emailVerified"] is True
    assert "password_hash" not in me_response.json["user"]
    assert refresh_response.status_code == 200
    assert cookie_value(refresh_response, "refresh_token_cookie") != refresh_cookie
    with app.app_context():
        tokens = db.session.scalars(db.select(RefreshToken)).all()
        assert len(tokens) == 2
        assert sum(token.revoked_at is not None for token in tokens) == 1

    client.delete_cookie("refresh_token_cookie", path="/api/v1/auth/refresh")
    replay = client.post(
        "/api/v1/auth/refresh",
        headers={
            "Authorization": f"Bearer {refresh_cookie}",
            "X-CSRF-TOKEN": original_refresh_csrf,
        },
    )
    assert replay.status_code == 401


def test_complete_registration_verification_login_me_and_logout_lifecycle(app, client):
    email = "auth-lifecycle@example.test"
    registration = register(client, email=email)
    assert registration.status_code == 201

    code = verification_code(app, email)
    wrong_code = "000000" if code != "000000" else "000001"
    verified = client.post("/api/v1/auth/verify-otp", json={"email": email, "code": wrong_code})
    assert verified.status_code == 400
    verified = client.post("/api/v1/auth/verify-otp", json={"email": email, "code": code})
    assert verified.status_code == 200

    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    current_user = client.get("/api/v1/auth/me")
    assert current_user.status_code == 200
    assert current_user.json["user"]["email"] == email

    logged_out = client.post(
        "/api/v1/auth/logout",
        headers=csrf_header(login, "csrf_access_token"),
    )
    assert logged_out.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_failure_does_not_disclose_which_credential_was_wrong(app, client):
    register_verified(app, client)

    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "wrong-password"})

    assert response.status_code == 401
    assert response.json["error"]["code"] == "INVALID_CREDENTIALS"
    assert response.json["error"]["message"] == "Email or password is incorrect."


def test_protected_api_requires_authenticated_session(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_otp_is_one_time_attempt_limited_and_resend_invalidates_previous_code(app, client):
    register(client)
    first_code = verification_code(app)

    resend = client.post("/api/v1/auth/resend-otp", json={"email": EMAIL})
    second_code = verification_code(app)

    assert resend.status_code == 200
    assert first_code != second_code
    assert client.post("/api/v1/auth/verify-otp", json={"email": EMAIL, "code": first_code}).status_code == 400
    assert client.post("/api/v1/auth/verify-otp", json={"email": EMAIL, "code": second_code}).status_code == 200
    assert client.post("/api/v1/auth/verify-otp", json={"email": EMAIL, "code": second_code}).status_code == 400


def test_otp_attempts_are_capped(app, client):
    register(client)
    for _ in range(5):
        response = client.post("/api/v1/auth/verify-otp", json={"email": EMAIL, "code": "000000"})
        assert response.status_code == 400
    correct_code = verification_code(app)
    response = client.post("/api/v1/auth/verify-otp", json={"email": EMAIL, "code": correct_code})
    assert response.status_code == 400


def test_registration_rolls_back_when_verification_email_cannot_be_sent(app, client):
    app.extensions["auth_email_sender"] = unavailable_email_sender

    response = register(client)

    assert response.status_code == 503
    with app.app_context():
        assert db.session.scalar(db.select(User).where(User.email == EMAIL)) is None


def test_registration_without_smtp_or_development_mailbox_returns_503_and_rolls_back(app, client):
    app.extensions.pop("auth_email_sender")
    app.config.update(AUTH_EMAIL_MODE="smtp", SMTP_HOST=None, SMTP_FROM_EMAIL=None)

    response = register(client)

    assert response.status_code == 503
    assert response.json["error"]["code"] == "SERVICE_UNAVAILABLE"
    with app.app_context():
        assert db.session.scalar(db.select(User).where(User.email == EMAIL)) is None


def test_development_file_mailbox_delivers_verification_without_bypassing_otp(app, client, tmp_path):
    app.extensions.pop("auth_email_sender")
    app.config.update(AUTH_EMAIL_MODE="file", ENVIRONMENT="development")
    app.instance_path = str(tmp_path / "instance")

    registration = register(client)

    assert registration.status_code == 201
    mailbox = tmp_path / "instance" / "dev-mailbox.jsonl"
    assert mailbox.exists()
    message = json.loads(mailbox.read_text(encoding="utf-8").splitlines()[0])
    assert message["recipient"] == EMAIL
    code = re.search(r"\b(\d{6})\b", message["body"]).group(1)
    assert client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 403
    assert client.post("/api/v1/auth/verify-otp", json={"email": EMAIL, "code": code}).status_code == 200
    assert client.post("/api/v1/auth/verify-otp", json={"email": EMAIL, "code": code}).status_code == 400
    assert client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200


def test_resend_failure_preserves_previous_usable_verification_code(app, client):
    register(client)
    original_code = verification_code(app)
    app.extensions["auth_email_sender"] = unavailable_email_sender

    response = client.post("/api/v1/auth/resend-otp", json={"email": EMAIL})

    assert response.status_code == 503
    error_message = response.json["error"]["message"].lower()
    assert "try again later" in error_message or "mail unavailable" in error_message
    assert client.post(
        "/api/v1/auth/verify-otp",
        json={"email": EMAIL, "code": original_code},
    ).status_code == 200


def test_expired_otp_is_rejected(app, client):
    register(client)
    with app.app_context():
        verification = db.session.scalar(db.select(EmailVerification))
        verification.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()

    response = client.post(
        "/api/v1/auth/verify-otp",
        json={"email": EMAIL, "code": verification_code(app)},
    )

    assert response.status_code == 400


def test_password_reset_response_does_not_disclose_account_existence(app, client):
    register_verified(app, client)
    known = client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.test"})

    assert known.status_code == unknown.status_code == 200
    assert known.json == unknown.json
    reset_message = app.extensions["auth_email_outbox"][-1][2]
    token = parse_qs(urlparse(re.search(r"https?://\S+", reset_message).group(0)).query)["token"][0]
    with app.app_context():
        reset_record = db.session.scalar(db.select(PasswordResetToken))
        assert reset_record.token_hash != token
        assert reset_record.expires_at.replace(tzinfo=UTC) > datetime.now(UTC)

    reset = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "new-secure-password"})
    assert reset.status_code == 200
    assert client.post("/api/v1/auth/reset-password", json={"token": token, "password": "another-password"}).status_code == 400
    assert client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "new-secure-password"}).status_code == 200


def test_reset_invalidates_existing_session(app, client):
    register_verified(app, client)
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    reset_message = app.extensions["auth_email_outbox"][-1][2]
    token = parse_qs(urlparse(re.search(r"https?://\S+", reset_message).group(0)).query)["token"][0]

    reset = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "new-secure-password"})
    assert reset.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_current_session_and_clears_cookies(app, client):
    register_verified(app, client)
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    access_token = cookie_value(login_response, "access_token_cookie")

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers=csrf_header(login_response, "csrf_access_token"),
    )

    assert logout_response.status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}).status_code == 401
    with app.app_context():
        session = db.session.scalar(db.select(UserSession))
        assert session.revoked_at is not None


def test_profile_update_and_password_change(app, client):
    register_verified(app, client)
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    profile = client.patch(
        "/api/v1/auth/me",
        json={"name": "New Name", "phone": "+1 555 0100"},
        headers=csrf_header(login_response, "csrf_access_token"),
    )
    assert profile.status_code == 200
    assert profile.json["user"]["name"] == "New Name"
    assert profile.json["user"]["phone"] == "+1 555 0100"

    changed = client.post(
        "/api/v1/auth/change-password",
        json={"currentPassword": PASSWORD, "newPassword": "new-secure-password"},
        headers=csrf_header(login_response, "csrf_access_token"),
    )
    assert changed.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "new-secure-password"}).status_code == 200


def test_customer_role_is_assigned_and_role_guard_denies_admin_access(app, client):
    protected = Blueprint("role_test", __name__, url_prefix="/api/v1")

    @protected.get("/role-test")
    @roles_required("admin")
    def role_test():
        return {"ok": True}

    app.register_blueprint(protected)
    assert client.get("/api/v1/admin/dashboard").status_code == 401
    register_verified(app, client)
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    response = client.get("/api/v1/role-test")

    assert response.status_code == 403
    assert client.get("/api/v1/admin/dashboard").status_code == 403
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == EMAIL))
        roles = db.session.scalars(
            db.select(Role.name).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id)
        ).all()
        assert roles == ["customer"]


def test_registration_and_profile_payloads_cannot_assign_admin_role(app, client):
    email = "self-promotion@example.test"
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "role": "admin",
            "roles": ["admin"],
            "isAdmin": True,
        },
    )
    assert registered.status_code == 201
    assert verify_email(app, client, email=email).status_code == 200
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200

    changed = client.patch(
        "/api/v1/auth/me",
        json={"name": "Still a customer", "role": "admin", "roles": ["admin"], "isAdmin": True},
        headers=csrf_header(login, "csrf_access_token"),
    )
    assert changed.status_code == 200
    assert changed.json["user"]["roles"] == ["customer"]
    assert client.get("/api/v1/admin/dashboard").status_code == 403


def test_disabled_user_cannot_refresh_token(app, client):
    register_verified(app, client)
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == EMAIL))
        user.is_active = False
        db.session.commit()

    response = client.post(
        "/api/v1/auth/refresh",
        headers=csrf_header(login_response, "csrf_refresh_token"),
    )

    assert response.status_code == 401


def test_cookie_auth_requires_csrf_header_for_post_put_patch_and_delete(app, client):
    from memorybook.permissions import active_user_required

    protected = Blueprint("csrf_test", __name__, url_prefix="/api/v1")

    @protected.route("/csrf-test", methods=["POST", "PUT", "PATCH", "DELETE"])
    @active_user_required
    def csrf_test():
        return {"ok": True}

    app.register_blueprint(protected)
    register_verified(app, client)
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    csrf = csrf_header(login_response, "csrf_access_token")

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert client.open("/api/v1/csrf-test", method=method).status_code == 401
        accepted = client.open("/api/v1/csrf-test", method=method, headers=csrf)
        assert accepted.status_code == 200, method
        assert accepted.json == {"ok": True}


def test_expired_password_reset_token_is_rejected(app, client):
    register_verified(app, client)
    assert client.post("/api/v1/auth/forgot-password", json={"email": EMAIL}).status_code == 200
    reset_message = app.extensions["auth_email_outbox"][-1][2]
    token = parse_qs(urlparse(re.search(r"https?://\S+", reset_message).group(0)).query)["token"][0]
    with app.app_context():
        reset_record = db.session.scalar(db.select(PasswordResetToken))
        reset_record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()

    response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "new-secure-password"},
    )
    assert response.status_code == 400
    assert client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200


def test_login_and_otp_endpoints_enforce_rate_limits(tmp_path):
    from memorybook import create_app

    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-that-is-not-used-outside-testing",
        "JWT_SECRET_KEY": "test-only-jwt-secret-that-is-not-used-outside-testing",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'rate-limit.sqlite').as_posix()}",
        "MIGRATIONS_DIRECTORY": "../migrations",
        "CORS_ORIGINS": [],
        "LOG_LEVEL": "CRITICAL",
        "RATELIMIT_ENABLED": True,
        "RATE_LIMIT_STORAGE_URI": "memory://",
        "CELERY": {"broker_url": "memory://", "result_backend": "cache+memory://"},
        "REDIS_URL": "redis://localhost:6379/0",
    })
    with application.app_context():
        db.create_all()
    client = application.test_client()

    login_responses = [
        client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
        for _ in range(11)
    ]
    otp_responses = [
        client.post("/api/v1/auth/verify-otp", json={"email": EMAIL, "code": "123456"})
        for _ in range(6)
    ]

    assert login_responses[-1].status_code == 429
    assert otp_responses[-1].status_code == 429
    with application.app_context():
        db.session.remove()
        db.drop_all()


def test_resend_otp_enforces_hourly_rate_limit(tmp_path):
    from memorybook import create_app

    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-that-is-not-used-outside-testing",
        "JWT_SECRET_KEY": "test-only-jwt-secret-that-is-not-used-outside-testing",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'resend-limit.sqlite').as_posix()}",
        "MIGRATIONS_DIRECTORY": "../migrations",
        "CORS_ORIGINS": [],
        "LOG_LEVEL": "CRITICAL",
        "RATELIMIT_ENABLED": True,
        "RATE_LIMIT_STORAGE_URI": "memory://",
    })
    with application.app_context():
        db.create_all()
    client = application.test_client()

    responses = [
        client.post("/api/v1/auth/resend-otp", json={"email": "limit@example.test"})
        for _ in range(4)
    ]

    assert [response.status_code for response in responses] == [200, 200, 200, 429]
    with application.app_context():
        db.session.remove()
        db.drop_all()
