from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import g, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from memorybook.extensions import db
from memorybook.models import Role, UserRole
from memorybook.services import AuthService


def active_user_required(view: Callable) -> Callable:
    @wraps(view)
    @jwt_required()
    def wrapped(*args: Any, **kwargs: Any):
        user = AuthService.get_active_user(get_jwt_identity())
        if not user:
            return jsonify({
                "error": {"code": "ACCOUNT_UNAVAILABLE", "message": "The authenticated account is unavailable."},
                "requestId": getattr(g, "request_id", None),
            }), 401
        g.current_user = user
        return view(*args, **kwargs)

    return wrapped


def get_authenticated_user():
    return getattr(g, "current_user", None)


def roles_required(*required_roles: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        @active_user_required
        def wrapped(*args: Any, **kwargs: Any):
            user = get_authenticated_user()
            roles = db.session.scalars(
                db.select(Role.name)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user.id)
            ).all()
            if not set(required_roles).intersection(roles):
                return jsonify({
                    "error": {"code": "FORBIDDEN", "message": "You are not authorized to access this resource."},
                    "requestId": getattr(g, "request_id", None),
                }), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator
