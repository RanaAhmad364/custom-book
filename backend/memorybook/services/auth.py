from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from memorybook.errors import ConflictError, ServiceUnavailableError, ValidationError
from memorybook.extensions import db
from memorybook.integrations.email import (
    email_delivery_is_configured,
    send_password_reset,
    send_verification_code,
)
from memorybook.models import (
    EmailVerification,
    PasswordResetToken,
    RefreshToken,
    Role,
    User,
    UserRole,
    UserSession,
)
from memorybook.repositories import UserRepository
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

OTP_MAX_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(UTC)


def _digest(value: str) -> str:
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


class AuthService:
    @staticmethod
    def digest_token(value: str) -> str:
        return _digest(value)

    @staticmethod
    def register(email: str, password: str, full_name: str | None = None) -> User:
        AuthService._require_email_delivery()
        user = UserRepository.get_by_email(email)
        if user:
            raise ConflictError("An account with this email already exists.", {"email": "already_exists"})
        user = User(email=email, full_name=full_name, password_hash=generate_password_hash(password))
        try:
            UserRepository.add(user)
            customer_role = db.session.scalar(db.select(Role).where(Role.name == "customer"))
            if customer_role is None:
                customer_role = Role(name="customer", description="Standard customer account", is_system=True)
                try:
                    with db.session.begin_nested():
                        db.session.add(customer_role)
                        db.session.flush()
                except IntegrityError:
                    customer_role = db.session.scalar(db.select(Role).where(Role.name == "customer"))
                    if customer_role is None:
                        raise
            db.session.add(UserRole(user_id=user.id, role_id=customer_role.id))
            AuthService.issue_email_verification(email)
        except IntegrityError as failure:
            db.session.rollback()
            raise ConflictError("An account with this email already exists.", {"email": "already_exists"}) from failure
        except ServiceUnavailableError:
            db.session.rollback()
            raise
        return user

    @staticmethod
    def authenticate(email: str, password: str) -> User | None:
        user = UserRepository.get_by_email(email)
        if not user or not user.is_active or user.deleted_at or not check_password_hash(user.password_hash, password):
            return None
        return user

    @staticmethod
    def issue_email_verification(email: str) -> None:
        user = UserRepository.get_by_email(email)
        if user is None or user.email_verified_at is not None:
            return
        now = _now()
        db.session.execute(
            update(EmailVerification)
            .where(
                EmailVerification.user_id == user.id,
                EmailVerification.purpose == "email_verification",
                EmailVerification.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        code = f"{secrets.randbelow(1_000_000):06d}"
        verification = EmailVerification(
            user_id=user.id,
            token_hash=_digest(code),
            purpose="email_verification",
            expires_at=now + timedelta(minutes=current_app.config["AUTH_OTP_TTL_MINUTES"]),
        )
        db.session.add(verification)
        try:
            db.session.flush()
            send_verification_code(email, code)
            db.session.commit()
        except ServiceUnavailableError:
            db.session.rollback()
            raise

    @staticmethod
    def resend_verification(email: str) -> None:
        user = UserRepository.get_by_email(email)
        if user is None or not user.is_active or user.deleted_at is not None or user.email_verified_at is not None:
            return
        AuthService.issue_email_verification(email)

    @staticmethod
    def _require_email_delivery() -> None:
        if not email_delivery_is_configured():
            raise ServiceUnavailableError("Email delivery is not configured. Contact the site administrator.")

    @staticmethod
    def verify_email_code(email: str, code: str) -> User:
        user = UserRepository.get_by_email_for_update(email)
        if user is None or not user.is_active or user.deleted_at is not None or user.email_verified_at is not None:
            raise ValidationError("The verification code is invalid or expired.", {"code": "invalid"})
        now = _now()
        verification = db.session.scalar(
            db.select(EmailVerification)
            .where(
                EmailVerification.user_id == user.id,
                EmailVerification.purpose == "email_verification",
                EmailVerification.consumed_at.is_(None),
                EmailVerification.expires_at > now,
            )
            .order_by(EmailVerification.created_at.desc())
            .with_for_update()
        )
        if verification is None or verification.attempts >= OTP_MAX_ATTEMPTS:
            raise ValidationError("The verification code is invalid or expired.", {"code": "invalid"})
        verification.attempts += 1
        if not hmac.compare_digest(verification.token_hash, _digest(code)):
            db.session.commit()
            raise ValidationError("The verification code is invalid or expired.", {"code": "invalid"})
        verification.verified_at = now
        verification.consumed_at = now
        user.email_verified_at = now
        db.session.commit()
        return user

    @staticmethod
    def request_password_reset(email: str) -> None:
        user = UserRepository.get_by_email(email)
        if user is None or not user.is_active or user.deleted_at is not None:
            return
        now = _now()
        db.session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )
        token = secrets.token_urlsafe(32)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=_digest(token),
            expires_at=now + timedelta(minutes=current_app.config["AUTH_RESET_TTL_MINUTES"]),
        )
        db.session.add(reset_token)
        try:
            db.session.flush()
            send_password_reset(email, token)
            db.session.commit()
        except ServiceUnavailableError:
            db.session.rollback()
            current_app.logger.warning("Password reset delivery could not be completed.")

    @staticmethod
    def reset_password(token: str, password: str) -> None:
        now = _now()
        reset = db.session.scalar(
            db.select(PasswordResetToken)
            .where(
                PasswordResetToken.token_hash == _digest(token),
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > now,
            )
            .with_for_update()
        )
        if reset is None:
            raise ValidationError("The password reset link is invalid or expired.", {"token": "invalid"})
        reset.used_at = now
        user = db.session.get(User, reset.user_id)
        if user is None or not user.is_active or user.deleted_at is not None:
            raise ValidationError("The password reset link is invalid or expired.", {"token": "invalid"})
        user.password_hash = generate_password_hash(password)
        AuthService.revoke_all_sessions(user.id, now=now, commit=False)
        db.session.commit()

    @staticmethod
    def verify_password(user: User, password: str) -> bool:
        return check_password_hash(user.password_hash, password)

    @staticmethod
    def change_password(user: User, current_password: str, new_password: str) -> None:
        if not check_password_hash(user.password_hash, current_password):
            raise ValidationError("The current password is incorrect.", {"currentPassword": "invalid"})
        now = _now()
        user.password_hash = generate_password_hash(new_password)
        AuthService.revoke_all_sessions(user.id, now=now, commit=False)
        db.session.commit()

    @staticmethod
    def revoke_all_sessions(user_id: str, *, now: datetime | None = None, commit: bool = True) -> None:
        revoked_at = now or _now()
        db.session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        db.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        if commit:
            db.session.commit()

    @staticmethod
    def revoke_session(session_id: str) -> None:
        now = _now()
        session = db.session.get(UserSession, session_id)
        if session is None:
            return
        session.revoked_at = now
        db.session.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id == session_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.session.commit()

    @staticmethod
    def get_active_user(user_id: str) -> User | None:
        user = UserRepository.get_by_id(user_id)
        return user if user and user.is_active and user.deleted_at is None else None
