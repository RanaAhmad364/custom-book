from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
)
from sqlalchemy import select

from memorybook.errors import ValidationError
from memorybook.extensions import db, limiter
from memorybook.models import NotificationPreference, RefreshToken, ShippingAddress, User, UserSession
from memorybook.permissions import active_user_required, get_authenticated_user
from memorybook.schemas import (
    EmailSchema,
    LoginSchema,
    NotificationPreferenceSchema,
    OtpSchema,
    PasswordChangeSchema,
    ProfileSchema,
    RegistrationSchema,
    ResetPasswordSchema,
    ShippingAddressSchema,
)
from memorybook.services import AuthService

auth_blueprint = Blueprint("auth", __name__)


def _json_body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("A JSON object is required.")
    return body


def _token_response(user: User, *, status: int = 200):
    response = jsonify({"user": user.public_dict()})
    response.status_code = status
    return response


def _issue_tokens(user: User, session: UserSession):
    claims = {"sid": session.id}
    access_token = create_access_token(identity=user.id, additional_claims=claims)
    refresh_token = create_refresh_token(identity=user.id, additional_claims=claims)
    token_id = decode_token(refresh_token)["jti"]
    token_hash = AuthService.digest_token(token_id)
    refresh_expiry = datetime.now(UTC) + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"]
    db.session.add(RefreshToken(
        user_id=user.id,
        session_id=session.id,
        token_hash=token_hash,
        expires_at=refresh_expiry,
    ))
    db.session.commit()
    response = _token_response(user)
    set_access_cookies(response, access_token)
    set_refresh_cookies(response, refresh_token)
    return response


def _serialize_address(address: ShippingAddress) -> dict:
    return {
        "id": address.id,
        "recipientName": address.recipient_name,
        "addressLine1": address.address_line_1,
        "addressLine2": address.address_line_2,
        "city": address.city,
        "region": address.region,
        "postalCode": address.postal_code,
        "countryCode": address.country_code,
        "phone": address.phone,
        "isDefault": address.is_default,
    }


@auth_blueprint.post("/register")
@limiter.limit("5 per minute")
def register():
    credentials = RegistrationSchema.load(_json_body())
    user = AuthService.register(**credentials)
    return jsonify({"user": user.public_dict(), "verificationRequired": True}), 201


@auth_blueprint.post("/login")
@limiter.limit("10 per minute")
def login():
    credentials = LoginSchema.load(_json_body())
    user = AuthService.authenticate(**credentials)
    if not user:
        return jsonify({
            "error": {"code": "INVALID_CREDENTIALS", "message": "Email or password is incorrect."},
            "requestId": request.request_id,
        }), 401
    if user.email_verified_at is None:
        return jsonify({
            "error": {"code": "EMAIL_NOT_VERIFIED", "message": "Verify your email before signing in."},
            "requestId": request.request_id,
        }), 403
    now = datetime.now(UTC)
    session_secret = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user.id,
        session_key_hash=AuthService.digest_token(session_secret),
        user_agent=request.headers.get("User-Agent", "")[:512] or None,
        ip_address=request.remote_addr,
        last_seen_at=now,
        expires_at=now + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"],
    )
    db.session.add(session)
    db.session.flush()
    return _issue_tokens(user, session)


@auth_blueprint.post("/logout")
@active_user_required
def logout():
    session_id = get_jwt().get("sid")
    if session_id:
        AuthService.revoke_session(session_id)
    response = jsonify({"message": "You have been signed out."})
    unset_jwt_cookies(response)
    return response


@auth_blueprint.post("/refresh")
@jwt_required(refresh=True)
@limiter.limit("30 per minute")
def refresh():
    claims = get_jwt()
    session_id = claims.get("sid")
    if not session_id:
        return jsonify({"error": {"code": "SESSION_UNAVAILABLE", "message": "Sign in again to continue."}}), 401
    session = db.session.get(UserSession, session_id)
    user = AuthService.get_active_user(get_jwt_identity())
    old_token = db.session.scalar(
        db.select(RefreshToken)
        .where(
            RefreshToken.session_id == session_id,
            RefreshToken.token_hash == AuthService.digest_token(claims["jti"]),
            RefreshToken.revoked_at.is_(None),
        )
        .with_for_update()
    )
    if session is None or user is None or old_token is None:
        return jsonify({"error": {"code": "SESSION_UNAVAILABLE", "message": "Sign in again to continue."}}), 401
    now = datetime.now(UTC)
    old_token.revoked_at = now
    session.last_seen_at = now
    session.expires_at = now + current_app.config["JWT_REFRESH_TOKEN_EXPIRES"]
    return _issue_tokens(user, session)


@auth_blueprint.get("/me")
@active_user_required
def me():
    return jsonify({"user": get_authenticated_user().public_dict()})


@auth_blueprint.patch("/me")
@active_user_required
def update_profile():
    user = get_authenticated_user()
    profile = ProfileSchema.load(_json_body())
    if "name" in profile:
        user.full_name = profile["name"]
    if "phone" in profile:
        user.phone = profile["phone"]
    db.session.commit()
    return jsonify({"user": user.public_dict()})


@auth_blueprint.get("/me/addresses")
@active_user_required
def list_addresses():
    addresses = db.session.scalars(
        select(ShippingAddress)
        .where(ShippingAddress.user_id == get_authenticated_user().id, ShippingAddress.deleted_at.is_(None))
        .order_by(ShippingAddress.is_default.desc(), ShippingAddress.created_at.desc())
    ).all()
    return jsonify({"items": [_serialize_address(address) for address in addresses]})


@auth_blueprint.post("/me/addresses")
@active_user_required
def create_address():
    data = ShippingAddressSchema.load(_json_body())
    user_id = get_authenticated_user().id
    existing = db.session.scalar(
        select(ShippingAddress.id).where(
            ShippingAddress.user_id == user_id,
            ShippingAddress.deleted_at.is_(None),
        ).limit(1)
    )
    if data["is_default"] or existing is None:
        db.session.query(ShippingAddress).filter(
            ShippingAddress.user_id == user_id,
            ShippingAddress.deleted_at.is_(None),
        ).update({ShippingAddress.is_default: False}, synchronize_session=False)
        data["is_default"] = True
    address = ShippingAddress(user_id=user_id, **data)
    db.session.add(address)
    db.session.commit()
    return jsonify({"address": _serialize_address(address)}), 201


@auth_blueprint.delete("/me/addresses/<string:address_id>")
@active_user_required
def delete_address(address_id: str):
    user_id = get_authenticated_user().id
    address = db.session.scalar(
        select(ShippingAddress).where(
            ShippingAddress.id == address_id,
            ShippingAddress.user_id == user_id,
            ShippingAddress.deleted_at.is_(None),
        )
    )
    if address is None:
        from werkzeug.exceptions import NotFound

        raise NotFound("Address was not found.")
    was_default = address.is_default
    address.deleted_at = datetime.now(UTC)
    if was_default:
        replacement = db.session.scalar(
            select(ShippingAddress)
            .where(
                ShippingAddress.user_id == user_id,
                ShippingAddress.deleted_at.is_(None),
                ShippingAddress.id != address.id,
            )
            .order_by(ShippingAddress.created_at.desc())
        )
        if replacement:
            replacement.is_default = True
    db.session.commit()
    return "", 204


@auth_blueprint.get("/me/notification-preferences")
@active_user_required
def get_notification_preferences():
    preferences = db.session.scalars(
        select(NotificationPreference).where(NotificationPreference.user_id == get_authenticated_user().id)
    ).all()
    stored = {(item.channel, item.category): item.enabled for item in preferences}
    defaults = [
        ("email", "order", True),
        ("email", "account", True),
        ("email", "design_inspiration", False),
        ("email", "product_news", False),
        ("in_app", "order", True),
        ("in_app", "account", True),
    ]
    return jsonify({"items": [
        {"channel": channel, "category": category, "enabled": stored.get((channel, category), enabled)}
        for channel, category, enabled in defaults
    ]})


@auth_blueprint.patch("/me/notification-preferences")
@active_user_required
def update_notification_preference():
    preference = NotificationPreferenceSchema.load(_json_body())
    user_id = get_authenticated_user().id
    record = db.session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
            NotificationPreference.channel == preference["channel"],
            NotificationPreference.category == preference["category"],
        )
    )
    if record is None:
        record = NotificationPreference(user_id=user_id, **preference)
        db.session.add(record)
    else:
        record.enabled = preference["enabled"]
    db.session.commit()
    return jsonify({"preference": preference})


@auth_blueprint.post("/change-password")
@limiter.limit("5 per minute")
@active_user_required
def change_password():
    user = get_authenticated_user()
    data = PasswordChangeSchema.load(_json_body())
    AuthService.change_password(user, **data)
    response = jsonify({"message": "Password updated. Sign in again on your devices."})
    unset_jwt_cookies(response)
    return response


@auth_blueprint.post("/verify-otp")
@limiter.limit("5 per minute")
def verify_otp():
    return _verify_otp_response()


@auth_blueprint.post("/verify-email")
@limiter.limit("5 per minute")
def verify_email():
    return _verify_otp_response()


def _verify_otp_response():
    data = OtpSchema.load(_json_body())
    user = AuthService.verify_email_code(**data)
    return jsonify({"user": user.public_dict(), "verified": True})


@auth_blueprint.post("/resend-otp")
@limiter.limit("3 per hour")
def resend_otp():
    email = EmailSchema.load(_json_body())["email"]
    AuthService.resend_verification(email)
    return jsonify({"message": "If the account requires verification, a new code has been sent."})


@auth_blueprint.post("/forgot-password")
@limiter.limit("3 per hour")
def forgot_password():
    email = EmailSchema.load(_json_body())["email"]
    AuthService.request_password_reset(email)
    return jsonify({"message": "If an account matches that email, password reset instructions have been sent."})


@auth_blueprint.post("/reset-password")
@limiter.limit("5 per hour")
def reset_password():
    data = ResetPasswordSchema.load(_json_body())
    AuthService.reset_password(**data)
    response = jsonify({"message": "Your password has been reset. Sign in with your new password."})
    unset_jwt_cookies(response)
    return response
