from __future__ import annotations

import re

from memorybook.errors import ValidationError

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _required_string(data: dict, field: str, *, max_length: int) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} is required.", {field: "required"})
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValidationError(f"{field} is too long.", {field: f"maximum length is {max_length}"})
    return normalized


def _email(data: dict) -> str:
    email = _required_string(data, "email", max_length=320).lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise ValidationError("Enter a valid email address.", {"email": "invalid"})
    return email


class RegistrationSchema:
    @staticmethod
    def load(data: object) -> dict[str, str]:
        if not isinstance(data, dict):
            raise ValidationError("A JSON object is required.")
        email = _email(data)
        password = data.get("password")
        if not isinstance(password, str) or not password:
            raise ValidationError("Password is required.", {"password": "required"})
        if len(password) < 8:
            raise ValidationError("Password must contain at least 8 characters.", {"password": "too_short"})
        if len(password) > 256:
            raise ValidationError("Password is too long.", {"password": "too_long"})
        name = data.get("name", "")
        if not isinstance(name, str) or len(name.strip()) > 100:
            raise ValidationError("Name must be 100 characters or fewer.", {"name": "invalid"})
        return {"email": email, "password": password, "full_name": name.strip() or None}


class LoginSchema:
    @staticmethod
    def load(data: object) -> dict[str, str]:
        if not isinstance(data, dict):
            raise ValidationError("A JSON object is required.")
        return {
            "email": _email(data),
            "password": _password(data),
        }


def _password(data: dict) -> str:
    password = data.get("password")
    if not isinstance(password, str) or not password:
        raise ValidationError("Password is required.", {"password": "required"})
    if len(password) > 256:
        raise ValidationError("password is too long.", {"password": "maximum length is 256"})
    return password


class EmailSchema:
    @staticmethod
    def load(data: object) -> dict[str, str]:
        if not isinstance(data, dict):
            raise ValidationError("A JSON object is required.")
        return {"email": _email(data)}


class OtpSchema:
    @staticmethod
    def load(data: object) -> dict[str, str]:
        if not isinstance(data, dict):
            raise ValidationError("A JSON object is required.")
        email = _email(data)
        code = data.get("code")
        if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
            raise ValidationError("Enter the six-digit verification code.", {"code": "invalid"})
        return {"email": email, "code": code}


class ResetPasswordSchema:
    @staticmethod
    def load(data: object) -> dict[str, str]:
        if not isinstance(data, dict):
            raise ValidationError("A JSON object is required.")
        token = _required_string(data, "token", max_length=256)
        password = _password(data)
        if len(password) < 8:
            raise ValidationError("Password must contain at least 8 characters.", {"password": "too_short"})
        return {"token": token, "password": password}


class PasswordChangeSchema:
    @staticmethod
    def load(data: object) -> dict[str, str]:
        if not isinstance(data, dict):
            raise ValidationError("A JSON object is required.")
        current_password = _password_field(data, "currentPassword")
        new_password = _password_field(data, "newPassword")
        if len(new_password) < 8:
            raise ValidationError("Password must contain at least 8 characters.", {"newPassword": "too_short"})
        if current_password == new_password:
            raise ValidationError("Choose a password different from the current one.", {"newPassword": "unchanged"})
        return {"current_password": current_password, "new_password": new_password}


def _password_field(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValidationError(f"{field} is required.", {field: "invalid"})
    return value


class ProfileSchema:
    @staticmethod
    def load(data: object) -> dict[str, str | None]:
        if not isinstance(data, dict):
            raise ValidationError("A JSON object is required.")
        result: dict[str, str | None] = {}
        for field, maximum in (("name", 100), ("phone", 40)):
            if field in data:
                value = data[field]
                if value is not None and (not isinstance(value, str) or len(value.strip()) > maximum):
                    raise ValidationError(f"{field} must be {maximum} characters or fewer.", {field: "invalid"})
                result[field] = value.strip() if isinstance(value, str) else None
        if not result:
            raise ValidationError("Provide at least one profile field.")
        return result
