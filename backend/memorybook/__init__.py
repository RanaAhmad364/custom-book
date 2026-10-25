from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import hashlib
import hmac
from datetime import UTC, datetime

from flask import Flask, current_app
from werkzeug.middleware.proxy_fix import ProxyFix

from memorybook.api.v1 import create_v1_blueprint
from memorybook.config import config_for_environment
from memorybook.errors import register_error_handlers
from memorybook.extensions import cors, db, jwt, limiter, migrate
from memorybook.logging_config import configure_logging
from memorybook.middleware import register_middleware
from memorybook.integrations.redis_client import create_redis_client
from memorybook.tasks.celery_app import create_celery


def create_app(
    config: type | Mapping[str, Any] | None = None,
) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    selected_config = config if config is not None else config_for_environment()
    if isinstance(selected_config, Mapping):
        app.config.from_object(config_for_environment())
        app.config.from_mapping(selected_config)
    else:
        app.config.from_object(selected_config)
    if config is None:
        app.config.from_prefixed_env()
    app.config.setdefault("ENVIRONMENT", "testing" if app.testing else "development")
    _validate_configuration(app)
    trusted_proxy_hops = int(app.config.get("TRUSTED_PROXY_HOPS", 0))
    if trusted_proxy_hops:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=trusted_proxy_hops,
            x_proto=trusted_proxy_hops,
            x_host=trusted_proxy_hops,
            x_port=trusted_proxy_hops,
        )

    configure_logging(app)
    db.init_app(app)
    migrate.init_app(app, db, directory=app.config["MIGRATIONS_DIRECTORY"])
    jwt.init_app(app)
    _configure_jwt_revocation()
    limiter.init_app(app)
    _configure_jwt_errors()
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID", "X-CSRF-TOKEN"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    )

    from memorybook import models  # noqa: F401

    from memorybook.integrations.admin_events import register_admin_event_listeners

    register_admin_event_listeners()
    app.register_blueprint(create_v1_blueprint())
    register_error_handlers(app)
    register_middleware(app)
    celery = create_celery(app)
    from memorybook.tasks.admin_email import register_admin_email_task
    from memorybook.tasks.notifications import register_notification_task
    from memorybook.tasks.pdf_generation import register_pdf_generation_task

    register_admin_email_task(celery)
    register_notification_task(celery)
    register_pdf_generation_task(celery)
    app.extensions["celery"] = celery
    app.extensions["redis"] = create_redis_client(app)
    _register_cli_commands(app)
    return app


def _configure_jwt_errors() -> None:
    from flask import jsonify, request

    @jwt.unauthorized_loader
    def missing_token(_reason: str):
        return jsonify({
            "error": {"code": "AUTHENTICATION_REQUIRED", "message": "An authenticated session is required."},
            "requestId": getattr(request, "request_id", None),
        }), 401

    @jwt.invalid_token_loader
    def invalid_token(_reason: str):
        return jsonify({
            "error": {"code": "INVALID_TOKEN", "message": "The bearer token is invalid."},
            "requestId": getattr(request, "request_id", None),
        }), 401

    @jwt.expired_token_loader
    def expired_token(_header: dict, _payload: dict):
        return jsonify({
            "error": {"code": "TOKEN_EXPIRED", "message": "The bearer token has expired."},
            "requestId": getattr(request, "request_id", None),
        }), 401

    @jwt.revoked_token_loader
    def revoked_token(_header: dict, _payload: dict):
        return jsonify({
            "error": {"code": "TOKEN_REVOKED", "message": "The bearer token is no longer valid."},
            "requestId": getattr(request, "request_id", None),
        }), 401


def _validate_configuration(app: Flask) -> None:
    if int(app.config.get("TRUSTED_PROXY_HOPS", 0)) < 0:
        raise RuntimeError("TRUSTED_PROXY_HOPS must not be negative.")
    for name in ("SECRET_KEY", "JWT_SECRET_KEY"):
        value = app.config.get(name)
        if not value or not isinstance(value, str):
            raise RuntimeError(f"{name} must be provided through the environment or app configuration.")
        if not app.testing and len(value) < 32:
            raise RuntimeError(f"{name} must contain at least 32 characters outside tests.")

    database_url = app.config.get("SQLALCHEMY_DATABASE_URI")
    if not database_url:
        raise RuntimeError("DATABASE_URL must point to PostgreSQL.")
    if not app.testing and not str(database_url).startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("DATABASE_URL must use PostgreSQL outside the test environment.")
    email_mode = app.config.get("AUTH_EMAIL_MODE", "smtp")
    if email_mode not in {"smtp", "file"}:
        raise RuntimeError("AUTH_EMAIL_MODE must be either smtp or file.")
    if email_mode == "file" and app.config.get("ENVIRONMENT") != "development":
        raise RuntimeError("AUTH_EMAIL_MODE=file is available only in development.")
    if not app.testing and app.config.get("ENVIRONMENT") == "production":
        if app.config.get("ASSET_STORAGE_BACKEND") != "s3":
            raise RuntimeError("Production asset storage must use the configured S3-compatible backend.")
        if not app.config.get("REDIS_URL", "").startswith(("redis://", "rediss://")):
            raise RuntimeError("REDIS_URL must point to Redis in production.")
        if app.config.get("RATE_LIMIT_STORAGE_URI", "").startswith("memory://"):
            raise RuntimeError("Production rate limiting requires shared Redis storage.")
        if not app.config.get("JWT_COOKIE_SECURE"):
            raise RuntimeError("Production authentication cookies must be secure.")


def _configure_jwt_revocation() -> None:
    from memorybook.models import RefreshToken, UserSession

    @jwt.token_in_blocklist_loader
    def is_token_revoked(_header: dict, payload: dict) -> bool:
        session_id = payload.get("sid")
        if not session_id:
            return True
        now = datetime.now(UTC)
        session = db.session.get(UserSession, session_id)
        if (
            session is None
            or session.revoked_at is not None
            or (
                session.expires_at.replace(tzinfo=UTC)
                if session.expires_at.tzinfo is None
                else session.expires_at
            ) <= now
        ):
            return True
        if payload.get("type") == "refresh":
            jti = payload.get("jti")
            if not isinstance(jti, str):
                return True
            digest = hmac.new(
                current_app.config["SECRET_KEY"].encode(),
                jti.encode(),
                hashlib.sha256,
            ).hexdigest()
            refresh = db.session.scalar(
                db.select(RefreshToken).where(
                    RefreshToken.token_hash == digest,
                    RefreshToken.session_id == session_id,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > now,
                )
            )
            return refresh is None
        return False


def _register_cli_commands(app: Flask) -> None:
    import click
    from sqlalchemy import text
    from sqlalchemy import select
    from pathlib import Path
    import json

    @app.cli.command("db-check")
    def db_check() -> None:
        """Verify PostgreSQL connectivity without displaying credentials."""
        try:
            with app.app_context():
                db.session.execute(text("SELECT 1"))
        except Exception as failure:
            raise click.ClickException(f"Database connectivity failed: {failure}") from failure
        click.echo("Database connection successful.")

    @app.cli.command("config-check")
    def config_check() -> None:
        """Validate backend configuration without printing secret values."""
        click.echo("Backend configuration is valid.")

    @app.cli.command("grant-admin")
    @click.argument("email")
    def grant_admin(email: str) -> None:
        """Grant the admin role to an existing account."""
        from memorybook.models import Role, User, UserRole

        normalized_email = email.strip().lower()
        with app.app_context():
            user = db.session.scalar(select(User).where(User.email == normalized_email, User.deleted_at.is_(None)))
            if user is None:
                raise click.ClickException("No active account exists with that email.")
            role = db.session.scalar(select(Role).where(Role.name == "admin"))
            if role is None:
                role = Role(name="admin", description="MemoryBook administrator", is_system=True)
                db.session.add(role)
                db.session.flush()
            existing = db.session.scalar(
                select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
            )
            if existing is None:
                db.session.add(UserRole(user_id=user.id, role_id=role.id))
                db.session.commit()
        click.echo(f"Admin role ensured for {normalized_email}.")

    @app.cli.command("dev-provision-admin")
    def dev_provision_admin() -> None:
        """Create or promote the local MemoryBook administrator account."""
        from memorybook.errors import ServiceUnavailableError
        from memorybook.models import Role, User, UserRole
        from memorybook.schemas import EmailSchema
        from memorybook.services import AuthService

        if app.config.get("ENVIRONMENT") != "development":
            raise click.ClickException("Local administrator provisioning is available only in development.")

        email = EmailSchema.load({"email": "ra7514770@gmail.com"})["email"]
        with app.app_context():
            user = db.session.scalar(
                select(User).where(User.email == email, User.deleted_at.is_(None)).with_for_update()
            )
            if user is None:
                password = click.prompt("Initial administrator password", hide_input=True, confirmation_prompt=True)
                if len(password) < 8 or len(password) > 256:
                    raise click.ClickException("Use a password between 8 and 256 characters.")
                try:
                    user = AuthService.register(email=email, password=password, full_name="MemoryBook Administrator")
                except ServiceUnavailableError as failure:
                    raise click.ClickException(str(failure)) from failure

            role = db.session.scalar(select(Role).where(Role.name == "admin"))
            if role is None:
                role = Role(name="admin", description="MemoryBook administrator", is_system=True)
                db.session.add(role)
                db.session.flush()
            existing = db.session.scalar(
                select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
            )
            if existing is None:
                db.session.add(UserRole(user_id=user.id, role_id=role.id))
            db.session.commit()
            verified = user.email_verified_at is not None

        click.echo(f"Administrator role ensured for {email}.")
        if not verified:
            click.echo("Email verification is still required. Complete the OTP flow using the development mailbox.")

    @app.cli.command("dev-mailbox")
    @click.option("--email", "recipient_filter", help="Show only messages for this recipient.")
    @click.option("--clear", is_flag=True, help="Clear the local mailbox after displaying messages.")
    def dev_mailbox(recipient_filter: str | None, clear: bool) -> None:
        """Read local test email; never exposes a web route."""
        if app.config.get("ENVIRONMENT") != "development" or app.config.get("AUTH_EMAIL_MODE") != "file":
            raise click.ClickException("The development mailbox requires AUTH_EMAIL_MODE=file in development.")
        mailbox = Path(app.instance_path) / "dev-mailbox.jsonl"
        if not mailbox.exists():
            click.echo("The development mailbox is empty.")
            return
        try:
            messages = [
                json.loads(line)
                for line in mailbox.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError) as failure:
            raise click.ClickException("The development mailbox could not be read.") from failure
        selected = [
            message for message in messages
            if recipient_filter is None or message.get("recipient", "").lower() == recipient_filter.lower()
        ]
        if not selected:
            click.echo("No development email messages matched.")
            return
        for message in selected:
            click.echo(f"To: {message['recipient']}\nSubject: {message['subject']}\n\n{message['body']}\n")
        if clear:
            try:
                remaining = [message for message in messages if message not in selected]
                if remaining:
                    mailbox.write_text(
                        "".join(json.dumps(message) + "\n" for message in remaining),
                        encoding="utf-8",
                    )
                else:
                    mailbox.unlink(missing_ok=True)
            except OSError as failure:
                raise click.ClickException("The development mailbox messages were displayed but could not be cleared.") from failure

    @app.cli.command("dev-reset-test-password")
    @click.argument("email")
    def dev_reset_test_password(email: str) -> None:
        """Reset a dedicated development test account password interactively."""
        allowed = {
            "admin.test@memorybook.local",
            "user1.test@memorybook.local",
            "user2.test@memorybook.local",
            "demo.customer.1@memorybook.local",
            "demo.customer.2@memorybook.local",
            "demo.customer.3@memorybook.local",
        }
        normalized_email = email.strip().lower()
        if app.config.get("ENVIRONMENT") != "development":
            raise click.ClickException("Test-account password resets are available only in development.")
        if normalized_email not in allowed:
            raise click.ClickException("This command only resets documented local test accounts in development.")
        password = click.prompt("New development password", hide_input=True, confirmation_prompt=True)
        if len(password) < 16 or len(password) > 256:
            raise click.ClickException("Use a password between 16 and 256 characters.")
        from werkzeug.security import generate_password_hash

        from memorybook.services.auth import AuthService
        from memorybook.models import User

        with app.app_context():
            user = db.session.scalar(select(User).where(
                User.email == normalized_email,
                User.deleted_at.is_(None),
            ))
            if user is None:
                raise click.ClickException("No active test account exists with that email.")
            user.password_hash = generate_password_hash(password)
            AuthService.revoke_all_sessions(user.id, commit=False)
            db.session.commit()
        click.echo(f"Password reset for {normalized_email}.")

    @app.cli.command("seed-demo-catalog")
    @click.option("--apply", "apply_changes", is_flag=True, help="Write demo records and local original artwork.")
    @click.option(
        "--confirm-local-database",
        is_flag=True,
        help="Confirm the loopback PostgreSQL database is a dedicated non-production development database.",
    )
    def seed_demo_catalog(apply_changes: bool, confirm_local_database: bool) -> None:
        """Preview or add the repeatable development-only demo catalog."""
        import json

        from memorybook.demo_catalog import (
            preview_demo_catalog,
            seed_demo_catalog as apply_demo_catalog,
            seed_environment_error,
            seed_schema_error,
        )

        error = seed_environment_error(
            app,
            confirm_local_database,
            require_confirmation=apply_changes,
        )
        if error:
            raise click.ClickException(error)
        with app.app_context():
            if not apply_changes:
                preview = preview_demo_catalog()
                click.echo("Dry run only; no records or assets were written.")
                click.echo(json.dumps(preview, indent=2))
                click.echo("Pass --apply to seed; local PostgreSQL also requires --confirm-local-database.")
                return
            schema_error = seed_schema_error(app)
            if schema_error:
                raise click.ClickException(schema_error)
            try:
                with app.test_request_context("/dev/seed-demo-catalog"):
                    summary = apply_demo_catalog()
            except ValueError as failure:
                db.session.rollback()
                raise click.ClickException(str(failure)) from failure
        click.echo("Demo catalog seed completed and verified.")
        click.echo(json.dumps(summary, indent=2))
