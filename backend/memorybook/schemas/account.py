from __future__ import annotations

from memorybook.errors import ValidationError


def _text(data: dict, field: str, maximum: int, *, required: bool = True) -> str:
    value = data.get(field)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value.strip()) > maximum:
        raise ValidationError(f"{field} is invalid.", {field: "invalid"})
    return value.strip()


class ShippingAddressSchema:
    @staticmethod
    def load(value: object) -> dict:
        if not isinstance(value, dict):
            raise ValidationError("A JSON object is required.")
        country = _text(value, "countryCode", 2).upper()
        if len(country) != 2 or not country.isalpha():
            raise ValidationError("Country code must contain two letters.", {"countryCode": "invalid"})
        is_default = value.get("isDefault", False)
        if not isinstance(is_default, bool):
            raise ValidationError("isDefault must be a boolean.", {"isDefault": "invalid"})
        return {
            "recipient_name": _text(value, "recipientName", 160),
            "address_line_1": _text(value, "addressLine1", 200),
            "address_line_2": _text(value, "addressLine2", 200, required=False) or None,
            "city": _text(value, "city", 120),
            "region": _text(value, "region", 120, required=False) or None,
            "postal_code": _text(value, "postalCode", 30),
            "country_code": country,
            "phone": _text(value, "phone", 40, required=False) or None,
            "is_default": is_default,
        }


class NotificationPreferenceSchema:
    CHANNELS = {"email", "in_app"}
    CATEGORIES = {"order", "account", "design_inspiration", "product_news"}

    @classmethod
    def load(cls, value: object) -> dict:
        if not isinstance(value, dict):
            raise ValidationError("A JSON object is required.")
        channel = _text(value, "channel", 30)
        category = _text(value, "category", 50)
        enabled = value.get("enabled")
        if channel not in cls.CHANNELS:
            raise ValidationError("Notification channel is invalid.", {"channel": "invalid"})
        if category not in cls.CATEGORIES:
            raise ValidationError("Notification category is invalid.", {"category": "invalid"})
        if not isinstance(enabled, bool):
            raise ValidationError("enabled must be a boolean.", {"enabled": "invalid"})
        return {"channel": channel, "category": category, "enabled": enabled}
