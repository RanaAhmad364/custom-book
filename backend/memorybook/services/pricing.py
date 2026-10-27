from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import current_app

from memorybook.errors import ConflictError, ValidationError

CENT = Decimal("0.01")
PLAN_RULES = {
    "BASIC": {
        "maximumPages": 80,
        "tagline": "A lovely everyday keepsake",
        "features": ["Up to 80 pages", "Softcover or standard hardcover", "Standard and premium paper"],
    },
    "MEDIUM": {
        "maximumPages": 120,
        "tagline": "More room for your story",
        "features": ["Up to 120 pages", "Hardcover and linen cover options", "Premium paper choices"],
    },
    "PREMIUM": {
        "maximumPages": 200,
        "tagline": "A keepsake made to treasure",
        "features": ["Up to 200 pages", "All available cover finishes", "Premium paper and print finish"],
    },
}


def default_currency() -> str:
    return str(current_app.config.get("PAYMENT_DEFAULT_CURRENCY", "PKR")).upper()


def plan_code(book_type: str | None) -> str:
    code = (book_type or "BASIC").strip().upper()
    return "BASIC" if code in {"LIGHT", "BASIC"} else code


def plan_details(book_type: str | None) -> dict:
    code = plan_code(book_type)
    if code not in PLAN_RULES:
        raise ConflictError("This book has an unsupported plan.")
    return {"code": code, **PLAN_RULES[code]}


def money(value: object, label: str, *, error_type=ConflictError) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as failure:
        raise error_type(f"{label} is not configured in the catalog.") from failure
    if not parsed.is_finite() or parsed < 0 or parsed.as_tuple().exponent < -2:
        raise error_type(f"{label} is not a valid catalog price.")
    return parsed.quantize(CENT, rounding=ROUND_HALF_UP)


def validate_product_pricing(product, *, admin=False) -> dict:
    metadata = product.admin_metadata or {}
    currency = str(product.currency or "").upper()
    if currency != default_currency():
        error = ValidationError if admin else ConflictError
        raise error(
            f"Book pricing must use the configured {default_currency()} currency.",
            {"currency": "mismatch"},
        )
    code = plan_code(product.book_type)
    if code not in PLAN_RULES:
        raise ValidationError("Book type must be BASIC, MEDIUM, or PREMIUM.", {"bookType": "invalid"})
    minimum = product.page_count_min
    maximum = product.page_count_max
    if minimum is not None and maximum is not None and maximum > PLAN_RULES[code]["maximumPages"]:
        raise ValidationError(
            f"{code.title()} books cannot exceed {PLAN_RULES[code]['maximumPages']} pages.",
            {"pageCountMax": "plan_limit"},
        )
    base_pages = metadata.get("basePageCount", minimum)
    if base_pages is not None and (
        isinstance(base_pages, bool)
        or not isinstance(base_pages, int)
        or base_pages < (minimum or 1)
        or maximum is not None and base_pages > maximum
    ):
        raise ValidationError("Base page count must be within the product page range.", {"basePageCount": "invalid"})
    even_required = metadata.get("evenPageCountRequired", False)
    if not isinstance(even_required, bool):
        raise ValidationError("evenPageCountRequired must be a boolean.", {"evenPageCountRequired": "invalid"})
    for field in ("pdfPrice", "printingPrice", "extraPagePrice"):
        if field in metadata and metadata[field] not in (None, ""):
            money(metadata[field], field, error_type=ValidationError)
    return {
        "basePageCount": int(base_pages or minimum or 1),
        "evenPageCountRequired": even_required,
        "plan": code,
    }


def validate_order_page_count(
    product,
    page_count: int,
    cover_name: str | None = None,
    *,
    print_order: bool = True,
) -> dict:
    plan = validate_product_pricing(product)
    if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 1:
        raise ConflictError("Book page count must be a positive integer.")
    if product.page_count_min is not None and page_count < product.page_count_min:
        raise ConflictError("The saved book has fewer pages than this product allows.")
    maximum = min(product.page_count_max or 500, PLAN_RULES[plan["plan"]]["maximumPages"])
    if page_count > maximum:
        raise ConflictError(f"{plan['plan'].title()} books cannot exceed {maximum} pages.")
    if print_order and plan["evenPageCountRequired"] and page_count % 2:
        raise ConflictError("This print product requires an even page count.")
    cover_rules = (product.admin_metadata or {}).get("planCoverOptions")
    if cover_name and isinstance(cover_rules, dict):
        allowed = cover_rules.get(plan["plan"])
        if isinstance(allowed, list) and cover_name not in allowed:
            raise ConflictError(f"This cover finish is not included in the {plan['plan'].title()} plan.")
    return plan


def calculate_book_price(
    base_price: Decimal,
    page_count: int,
    base_page_count: int,
    extra_page_price: Decimal,
    *,
    quantity: int = 1,
    shipping: Decimal = Decimal("0.00"),
    discount: Decimal = Decimal("0.00"),
) -> dict[str, Decimal | int]:
    extras = max(0, page_count - base_page_count)
    base = (base_price * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
    additional = (extra_page_price * extras * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
    shipping_total = (shipping * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
    discount_total = min(discount.quantize(CENT, rounding=ROUND_HALF_UP), base + additional)
    total = (base + additional + shipping_total - discount_total).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "basePrice": base,
        "additionalPages": additional,
        "extraPageCount": extras,
        "shipping": shipping_total,
        "discount": discount_total,
        "total": total,
    }


def calculate_discount(subtotal: Decimal, discount_type: str, value: Decimal) -> Decimal:
    if discount_type == "percent":
        amount = subtotal * value / Decimal("100")
    elif discount_type == "fixed":
        amount = value
    else:
        raise ConflictError("The discount code has an unsupported type.")
    return min(amount.quantize(CENT, rounding=ROUND_HALF_UP), subtotal)


def calculate_pdf_price(product) -> Decimal:
    validate_product_pricing(product)
    return money((product.admin_metadata or {}).get("pdfPrice"), "PDF price")


def public_plan_catalog(products: list) -> list[dict]:
    result = []
    for code, rule in PLAN_RULES.items():
        matching = [product for product in products if plan_code(product.book_type) == code]
        result.append({
            "id": code.lower(),
            "name": code,
            "tagline": rule["tagline"],
            "features": rule["features"],
            "maximumPages": rule["maximumPages"],
            "startingPrice": (
                str(min(money(product.starting_price, "starting price") for product in matching))
                if matching else None
            ),
            "currency": default_currency(),
        })
    return result
