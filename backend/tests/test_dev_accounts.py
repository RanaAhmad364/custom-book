from memorybook.extensions import db
from memorybook.models import Role, User, UserRole

from test_auth_api import PASSWORD, register, verification_code, verify_email


TEST_EMAIL = "user1.test@memorybook.local"
NEW_PASSWORD = "a-strong-local-test-password-2026!"
ADMIN_EMAIL = "ra7514770@gmail.com"
ADMIN_PASSWORD = "admin-test-password-2026"


def test_development_password_reset_is_interactive_and_revokes_existing_sessions(app, client):
    app.config["ENVIRONMENT"] = "development"
    assert register(client, email=TEST_EMAIL).status_code == 201
    assert verify_email(app, client, email=TEST_EMAIL).status_code == 200
    assert client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": PASSWORD},
    ).status_code == 200

    result = app.test_cli_runner().invoke(
        args=["dev-reset-test-password", TEST_EMAIL],
        input=f"{NEW_PASSWORD}\n{NEW_PASSWORD}\n",
    )

    assert result.exit_code == 0, result.output
    assert TEST_EMAIL in result.output
    assert NEW_PASSWORD not in result.output
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": NEW_PASSWORD},
    ).status_code == 200
    with app.app_context():
        account = db.session.scalar(db.select(User).where(User.email == TEST_EMAIL))
        assert account is not None
        assert account.password_hash != NEW_PASSWORD


def test_development_password_reset_rejects_other_identities(app):
    app.config["ENVIRONMENT"] = "development"
    result = app.test_cli_runner().invoke(
        args=["dev-reset-test-password", "other@example.test"],
    )
    assert result.exit_code != 0
    assert "documented local test accounts" in result.output


def test_development_mailbox_is_cli_only_and_clear_preserves_unmatched_messages(app, tmp_path):
    app.config.update(AUTH_EMAIL_MODE="file", ENVIRONMENT="development")
    app.instance_path = str(tmp_path / "instance")
    mailbox = tmp_path / "instance" / "dev-mailbox.jsonl"
    mailbox.parent.mkdir(parents=True)
    mailbox.write_text(
        '{"recipient":"user1.test@memorybook.local","subject":"OTP","body":"000123"}\n'
        '{"recipient":"user2.test@memorybook.local","subject":"OTP","body":"000456"}\n',
        encoding="utf-8",
    )

    result = app.test_cli_runner().invoke(
        args=["dev-mailbox", "--email", "user1.test@memorybook.local", "--clear"],
    )

    assert result.exit_code == 0, result.output
    assert "000123" in result.output
    assert "000456" not in result.output
    remaining = mailbox.read_text(encoding="utf-8")
    assert "user2.test@memorybook.local" in remaining
    assert "user1.test@memorybook.local" not in remaining
    assert not any(rule.rule.startswith("/api") and "dev-mailbox" in rule.rule for rule in app.url_map.iter_rules())


def test_development_admin_provisioning_uses_registration_otp_and_is_idempotent(app, client):
    app.config["ENVIRONMENT"] = "development"
    result = app.test_cli_runner().invoke(
        args=["dev-provision-admin"],
        input=f"{ADMIN_PASSWORD}\n{ADMIN_PASSWORD}\n",
    )

    assert result.exit_code == 0, result.output
    assert ADMIN_EMAIL in result.output
    assert ADMIN_PASSWORD not in result.output
    with app.app_context():
        account = db.session.scalar(db.select(User).where(User.email == ADMIN_EMAIL))
        assert account is not None
        account_id = account.id
        original_password_hash = account.password_hash
        assert account.password_hash != ADMIN_PASSWORD
        assert account.email_verified_at is None
        role_names = db.session.scalars(
            db.select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == account.id)
        ).all()
        assert sorted(role_names) == ["admin", "customer"]

    repeated = app.test_cli_runner().invoke(args=["dev-provision-admin"])
    assert repeated.exit_code == 0, repeated.output
    assert "Initial administrator password" not in repeated.output
    with app.app_context():
        account = db.session.scalar(db.select(User).where(User.email == ADMIN_EMAIL))
        assert account.id == account_id
        assert account.password_hash == original_password_hash
        assert db.session.scalar(
            db.select(db.func.count()).select_from(User).where(User.email == ADMIN_EMAIL)
        ) == 1

    assert client.post(
        "/api/v1/auth/verify-otp",
        json={"email": ADMIN_EMAIL, "code": verification_code(app, ADMIN_EMAIL)},
    ).status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    assert "admin" in login.json["user"]["roles"]
    assert "password_hash" not in login.json["user"]
    assert client.get("/api/v1/auth/me").json["user"]["roles"] == login.json["user"]["roles"]
    assert client.get("/api/v1/admin/dashboard").status_code == 200


def test_development_admin_provisioning_refuses_non_development(app):
    app.config["ENVIRONMENT"] = "production"
    result = app.test_cli_runner().invoke(args=["dev-provision-admin"])

    assert result.exit_code != 0
    assert "only in development" in result.output
