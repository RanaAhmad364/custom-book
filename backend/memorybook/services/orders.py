from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from sqlalchemy import func, select
from werkzeug.exceptions import NotFound

from memorybook.errors import ConflictError, ValidationError
from memorybook.extensions import db
from memorybook.integrations.payment_gateways import provider_for
from memorybook.models import (
    BookProduct,
    BookSize,
    BookVariant,
    CoverType,
    DiscountCode,
    OrderStatusHistory,
    PagePricing,
    PaperType,
    PdfOrder,
    PricingTier,
    PrintOrder,
    PrintOrderItem,
    PrintQuote,
    PrintSpecification,
    ShippingAddress,
    ShippingRate,
    UserProject,
)
from memorybook.services.catalog_projects import create_revision
from memorybook.services.payments import serialize_order
from memorybook.services.pricing import (
    calculate_book_price,
    calculate_discount,
    calculate_pdf_price,
    default_currency,
    money,
    validate_order_page_count,
    validate_product_pricing,
)


def pdf_offer(project_id: str, user_id: str) -> dict:
    project, product = _owned_project_and_product(project_id, user_id)
    amount = calculate_pdf_price(product)
    return {
        "amount": str(amount),
        "currency": default_currency(),
        "description": f"High-quality PDF download for {project.title}",
    }


def create_pdf_order(
    project_id: str,
    user_id: str,
    idempotency_key: str,
    provider: str | None,
    payment_method: str | None = None,
) -> dict:
    existing = db.session.scalar(
        select(PdfOrder).where(PdfOrder.user_id == user_id, PdfOrder.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.project_id != project_id:
            raise ConflictError("This idempotency key has already been used for a different order.")
        return serialize_order(existing, "pdf")
    project, product = _owned_project_and_product(project_id, user_id, lock=True)
    if not project.document:
        raise ConflictError("Save your book before placing a PDF order.")
    validate_order_page_count(product, int(project.page_count), print_order=False)
    amount = calculate_pdf_price(product)
    provider_for(default_currency(), provider, payment_method)
    revision = create_revision(project, project.version)
    order = PdfOrder(
        order_number=_order_number("PDF"),
        user_id=user_id,
        project_id=project.id,
        project_revision_id=revision.id,
        status="pending",
        currency=default_currency(),
        service_price=amount,
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=amount,
        price_snapshot={
            "description": "High-quality PDF download",
            "pdfProfiles": ["digital"],
            "taxApplicable": False,
            "projectRevisionId": revision.id,
        },
        page_count=int(project.page_count),
        idempotency_key=idempotency_key,
    )
    db.session.add(order)
    db.session.add(_history_row(order.id, "pdf", "order_placed", "PDF order created; payment is pending."))
    db.session.commit()
    from memorybook.services.payments import create_payment

    return create_payment(order, "pdf", provider, f"{order.id}:payment", payment_method)


def create_print_quote(
    project_id: str,
    user_id: str,
    configuration: dict,
    shipping: dict,
) -> dict:
    project, product = _owned_project_and_product(project_id, user_id)
    if not project.document:
        raise ConflictError("Save your book before requesting a print quote.")
    config = _validate_configuration(configuration)
    address = _validate_address(shipping)
    width = _decimal(project.document.get("book", {}).get("size", {}).get("width"), "book width")
    height = _decimal(project.document.get("book", {}).get("size", {}).get("height"), "book height")
    width_mm = width * Decimal("25.4")
    height_mm = height * Decimal("25.4")

    variant_row = db.session.execute(
        select(BookVariant, BookSize, CoverType, PaperType)
        .join(BookSize, BookSize.id == BookVariant.size_id)
        .join(CoverType, CoverType.id == BookVariant.cover_type_id)
        .join(PaperType, PaperType.id == BookVariant.paper_type_id)
        .where(
            BookVariant.product_id == product.id,
            BookVariant.is_active.is_(True),
            BookSize.is_active.is_(True),
            CoverType.is_active.is_(True),
            PaperType.is_active.is_(True),
        )
    ).all()
    matching_variants = [
        (candidate, size, cover, paper)
        for candidate, size, cover, paper in variant_row
        if abs(Decimal(size.width_mm) - width_mm) <= Decimal("0.5")
        and abs(Decimal(size.height_mm) - height_mm) <= Decimal("0.5")
        and _matches_choice(cover.name, config["cover"])
        and _matches_choice(paper.name, config["paper"])
    ]
    if len(matching_variants) > 1:
        raise ConflictError("The selected print configuration matches multiple variants. Contact support.")
    variant = matching_variants[0] if matching_variants else None
    if variant is None:
        raise ConflictError("The selected size, cover, and paper combination is not configured for this book.")
    selected_variant, size, cover, paper = variant
    product_metadata = product.admin_metadata or {}
    validate_order_page_count(product, int(project.page_count), cover.name)
    for field, option_id in (
        ("sizeOptions", selected_variant.size_id),
        ("coverOptions", selected_variant.cover_type_id),
        ("paperOptions", selected_variant.paper_type_id),
    ):
        configured_options = product_metadata.get(field)
        if isinstance(configured_options, list) and configured_options and option_id not in configured_options:
            raise ConflictError("The selected print option is no longer enabled for this book.")

    tier = db.session.scalar(
        select(PricingTier).where(PricingTier.code == config["tier"].upper(), PricingTier.is_active.is_(True))
    )
    if tier is None:
        raise ConflictError("The selected printing tier is not available.")
    if "printingTiers" in product_metadata:
        configured_tiers = product_metadata["printingTiers"]
        if not isinstance(configured_tiers, list) or config["tier"].upper() not in {
            item.upper() for item in configured_tiers if isinstance(item, str)
        }:
            raise ConflictError("The selected printing tier is not configured for this book.")
    page_count = int(project.page_count)
    page_rules = db.session.scalars(
        select(PagePricing).where(
            PagePricing.tier_id == tier.id,
            PagePricing.minimum_pages <= page_count,
            PagePricing.maximum_pages >= page_count,
        ).limit(2)
    ).all()
    if not page_rules:
        raise ConflictError("No page pricing is configured for this book's page count and tier.")
    if len(page_rules) > 1:
        raise ConflictError("The selected printing tier has overlapping page-pricing ranges.")
    page_rule = page_rules[0]
    shipping_rate = db.session.scalar(
        select(ShippingRate)
        .where(
            ShippingRate.country_code == address["country"],
            ShippingRate.region_code == address["region"],
            ShippingRate.is_active.is_(True),
        )
        .order_by(ShippingRate.service_code)
    )
    if shipping_rate is None:
        shipping_rate = db.session.scalar(
            select(ShippingRate).where(
                ShippingRate.country_code == address["country"],
                ShippingRate.region_code.is_(None),
                ShippingRate.is_active.is_(True),
            ).order_by(ShippingRate.service_code)
        )
    if shipping_rate is None:
        raise ConflictError("Shipping is not configured for the selected destination.")
    currencies = {
        product.currency.upper(),
        selected_variant.currency.upper(),
        tier.currency.upper(),
        shipping_rate.currency.upper(),
    }
    if currencies != {default_currency()}:
        raise ConflictError(f"Product, print, tier, and shipping prices must use {default_currency()}.")

    quantity = config["quantity"]
    book_unit_price = money(product.starting_price, "book price")
    printing_unit_price = money(selected_variant.base_price, "printing charge")
    base_pages = int(product_metadata.get("basePageCount", product.page_count_min or page_rule.minimum_pages))
    extra_page_price = money(product_metadata.get("extraPagePrice", page_rule.price_per_page), "additional-page price")
    shipping_unit_price = money(shipping_rate.price, "shipping")
    undiscounted = calculate_book_price(
        book_unit_price + printing_unit_price,
        page_count,
        base_pages,
        extra_page_price,
        quantity=quantity,
        shipping=shipping_unit_price,
    )
    discount_code = _active_discount(config["discountCode"], default_currency()) if config["discountCode"] else None
    discount_base = undiscounted["basePrice"] + undiscounted["additionalPages"]
    discount = (
        calculate_discount(discount_base, discount_code.discount_type, money(discount_code.value, "discount"))
        if discount_code else Decimal("0.00")
    )
    calculated = calculate_book_price(
        book_unit_price + printing_unit_price,
        page_count,
        base_pages,
        extra_page_price,
        quantity=quantity,
        shipping=shipping_unit_price,
        discount=discount,
    )
    book_price = (book_unit_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    printing_charge = (printing_unit_price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    additional_page_count = int(calculated["extraPageCount"])
    additional_pages = calculated["additionalPages"]
    shipping_amount = calculated["shipping"]
    discount = calculated["discount"]
    tax = Decimal("0.00")
    total = calculated["total"]
    now = datetime.now(UTC)
    production_days = (product.admin_metadata or {}).get("productionDays")
    if isinstance(production_days, bool) or not isinstance(production_days, int) or production_days < 1:
        raise ConflictError("Production timing is not configured for this book.")
    if not shipping_rate.estimated_days_max:
        raise ConflictError("Delivery timing is not configured for this destination.")
    production_estimate = (date.today() + timedelta(days=production_days)).isoformat()
    delivery_estimate = (
        date.today() + timedelta(days=production_days + int(shipping_rate.estimated_days_max))
    ).isoformat()
    revision = create_revision(project, project.version)
    price_snapshot = {
        "bookPrice": str(book_price),
        "printingCharge": str(printing_charge),
        "additionalPages": str(additional_pages),
        "shipping": str(shipping_amount),
        "discount": str(discount),
        "tax": str(tax),
        "taxApplicable": False,
        "total": str(total),
        "quantity": quantity,
        "pageCount": page_count,
        "basePageCount": base_pages,
        "extraPageCount": additional_page_count,
        "extraPagePrice": str(extra_page_price),
        "hardCopyBasePrice": str(book_unit_price + printing_unit_price),
        "plan": validate_product_pricing(product)["plan"],
        "discountCode": discount_code.code if discount_code else None,
        "discountCodeId": discount_code.id if discount_code else None,
        "variantId": selected_variant.id,
        "tierId": tier.id,
        "sizeName": size.name,
        "coverName": cover.name,
        "paperName": paper.name,
        "shippingRateId": shipping_rate.id,
        "productionEstimate": production_estimate,
        "deliveryEstimate": delivery_estimate,
    }
    quote = PrintQuote(
        user_id=user_id,
        project_id=project.id,
        project_revision_id=revision.id,
        currency=default_currency(),
        total_amount=total,
        configuration=config,
        shipping_address_snapshot=address,
        price_snapshot=price_snapshot,
        expires_at=now + timedelta(minutes=15),
    )
    db.session.add(quote)
    db.session.commit()
    return {
        "id": quote.id,
        **price_snapshot,
        "currency": quote.currency,
        "productionEstimate": production_estimate,
        "deliveryEstimate": delivery_estimate,
        "expiresAt": quote.expires_at.isoformat(),
    }


def create_print_order(
    project_id: str,
    user_id: str,
    configuration: dict,
    shipping: dict,
    quote_id: str,
    idempotency_key: str,
    provider: str | None,
    payment_method: str | None = None,
) -> dict:
    existing = db.session.scalar(
        select(PrintOrder).where(PrintOrder.user_id == user_id, PrintOrder.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.project_id != project_id:
            raise ConflictError("This idempotency key has already been used for a different order.")
        from memorybook.services.payments import create_payment

        return create_payment(existing, "print", provider, f"{existing.id}:payment")
    quote = db.session.scalar(
        select(PrintQuote)
        .where(PrintQuote.id == quote_id, PrintQuote.user_id == user_id, PrintQuote.project_id == project_id)
        .with_for_update()
    )
    if quote is None:
        raise NotFound("The print quote was not found.")
    now = datetime.now(UTC)
    quote_expires_at = quote.expires_at
    if quote_expires_at.tzinfo is None:
        quote_expires_at = quote_expires_at.replace(tzinfo=UTC)
    if quote_expires_at <= now or quote.consumed_at is not None:
        raise ConflictError("Refresh the expired or used print quote before placing the order.")
    if _validate_configuration(configuration) != quote.configuration:
        raise ConflictError("Print options changed after this quote was calculated. Refresh the quote.")
    if _validate_address(shipping) != quote.shipping_address_snapshot:
        raise ConflictError("The shipping address changed after this quote was calculated. Refresh the quote.")
    discount_code_id = quote.price_snapshot.get("discountCodeId")
    if discount_code_id:
        discount_code = db.session.scalar(
            select(DiscountCode).where(DiscountCode.id == discount_code_id).with_for_update()
        )
        if discount_code is None or not _discount_is_available(discount_code, quote.currency):
            raise ConflictError("The discount code is no longer available. Refresh the quote.")
        discount_code.uses_count += 1
    provider_for(quote.currency, provider, payment_method)
    project = db.session.scalar(
        select(UserProject).where(UserProject.id == project_id, UserProject.user_id == user_id).with_for_update()
    )
    if project is None:
        raise NotFound("Book project was not found.")
    price = quote.price_snapshot
    address = quote.shipping_address_snapshot
    db_address = ShippingAddress(
        user_id=user_id,
        recipient_name=address["fullName"],
        address_line_1=address["line1"],
        address_line_2=address.get("line2") or None,
        city=address["city"],
        region=address["region"],
        postal_code=address["postalCode"],
        country_code=address["country"],
        phone=address["phone"],
    )
    db.session.add(db_address)
    db.session.flush()
    order = PrintOrder(
        order_number=_order_number("PRT"),
        user_id=user_id,
        project_id=project_id,
        project_revision_id=quote.project_revision_id,
        shipping_address_id=db_address.id,
        shipping_address_snapshot=address,
        status="order_placed",
        currency=quote.currency,
        book_amount=Decimal(price["bookPrice"]),
        printing_amount=Decimal(price["printingCharge"]),
        additional_pages_amount=Decimal(price["additionalPages"]),
        shipping_amount=Decimal(price["shipping"]),
        discount_amount=Decimal(price["discount"]),
        tax_amount=Decimal(price["tax"]),
        total_amount=quote.total_amount,
        price_snapshot={**price, "quoteId": quote.id},
        idempotency_key=idempotency_key,
    )
    db.session.add(order)
    db.session.flush()
    item = PrintOrderItem(
        print_order_id=order.id,
        variant_id=price["variantId"],
        quantity=int(price["quantity"]),
        page_count=int(price["pageCount"]),
        unit_price=(
            Decimal(price["bookPrice"])
            + Decimal(price["printingCharge"])
            + Decimal(price["additionalPages"])
        ) / int(price["quantity"]),
        line_total=(
            Decimal(price["bookPrice"])
            + Decimal(price["printingCharge"])
            + Decimal(price["additionalPages"])
        ),
        specification_snapshot={
            "tier": quote.configuration["tier"],
            "size": price["sizeName"],
            "cover": price["coverName"],
            "paper": price["paperName"],
        },
    )
    db.session.add(item)
    db.session.flush()
    db.session.add(PrintSpecification(
        item_id=item.id,
        tier_code=quote.configuration["tier"].upper(),
        size_name=price["sizeName"],
        cover_name=price["coverName"],
        paper_name=price["paperName"],
        page_count=int(price["pageCount"]),
        specification_data={**quote.configuration, "shippingRateId": price["shippingRateId"]},
    ))
    db.session.add(_history_row(order.id, "print", "order_placed", "Print order created; payment is pending."))
    quote.consumed_at = now
    db.session.commit()
    from memorybook.services.payments import create_payment

    return create_payment(order, "print", provider, f"{order.id}:payment", payment_method)


def get_user_order(kind: str, order_id: str, user_id: str) -> dict:
    model = PdfOrder if kind == "pdf" else PrintOrder
    order = db.session.scalar(select(model).where(model.id == order_id, model.user_id == user_id))
    if order is None:
        raise NotFound("Order was not found.")
    payload = serialize_order(order, kind)
    payload["statusHistory"] = _history(order.id, kind)
    return payload


def list_user_orders(kind: str, user_id: str) -> list[dict]:
    model = PdfOrder if kind == "pdf" else PrintOrder
    orders = db.session.scalars(select(model).where(model.user_id == user_id).order_by(model.created_at.desc())).all()
    return [serialize_order(order, kind) for order in orders]


def request_order_cancellation(order_id: str, user_id: str, reason: str) -> dict:
    order = db.session.scalar(
        select(PrintOrder).where(PrintOrder.id == order_id, PrintOrder.user_id == user_id).with_for_update()
    )
    if order is None:
        raise NotFound("Print order was not found.")
    if order.status in {"cancelled", "delivered"}:
        raise ConflictError("This print order can no longer be cancelled.")
    previous = db.session.scalar(
        select(OrderStatusHistory.id).where(
            OrderStatusHistory.print_order_id == order.id,
            OrderStatusHistory.status == "cancellation_requested",
        )
    )
    if previous:
        return {"status": "pending", "message": "Your cancellation request is already being reviewed."}
    db.session.add(_history_row(order.id, "print", "cancellation_requested", reason))
    db.session.commit()
    from memorybook.services.notifications import queue_order_event

    queue_order_event(
        order.user_id,
        f"cancellation_requested:{order.id}",
        "order",
        "Cancellation request received",
        "We received your request and will update you when it is reviewed.",
        "/dashboard/orders",
    )
    db.session.commit()
    return {"status": "pending", "message": "Your cancellation request has been submitted."}


def _owned_project_and_product(project_id: str, user_id: str, *, lock: bool = False):
    query = select(UserProject).where(UserProject.id == project_id, UserProject.user_id == user_id)
    if lock:
        query = query.with_for_update()
    project = db.session.scalar(query)
    if project is None:
        raise NotFound("Book project was not found.")
    if not project.product_id:
        raise ConflictError("This project is not linked to a purchasable book product.")
    product = db.session.scalar(
        select(BookProduct).where(BookProduct.id == project.product_id, BookProduct.is_active.is_(True))
    )
    if product is None:
        raise ConflictError("The linked book product is not currently available for purchase.")
    return project, product


def _validate_configuration(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValidationError("Print configuration must be an object.")
    tier = _choice(value.get("tier"), "tier")
    paper = _choice(value.get("paper"), "paper")
    cover = _choice(value.get("cover"), "cover")
    quantity = value.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1 or quantity > 100:
        raise ValidationError("Quantity must be between 1 and 100.", {"quantity": "invalid"})
    discount_code = value.get("discountCode", "")
    if not isinstance(discount_code, str) or len(discount_code.strip()) > 80:
        raise ValidationError("Discount code is invalid.", {"discountCode": "invalid"})
    return {
        "tier": tier,
        "paper": paper,
        "cover": cover,
        "quantity": quantity,
        "discountCode": discount_code.strip().upper(),
    }


def quote_project_prices(project_id: str, user_id: str, page_count: int) -> dict:
    project, product = _owned_project_and_product(project_id, user_id)
    plan = validate_order_page_count(product, page_count, print_order=False)
    metadata = product.admin_metadata or {}
    base_pages = int(metadata.get("basePageCount", product.page_count_min or 1))
    variant_prices = db.session.scalars(
        select(BookVariant.base_price).where(
            BookVariant.product_id == product.id,
            BookVariant.is_active.is_(True),
            BookVariant.currency == default_currency(),
        ).order_by(BookVariant.base_price)
    ).all()
    if not variant_prices:
        raise ConflictError("Print pricing is not configured for this book.")
    base_price = money(product.starting_price, "book price") + money(variant_prices[0], "printing charge")
    page_rate = metadata.get("extraPagePrice")
    if page_rate in (None, ""):
        page_rule = db.session.scalar(
            select(PagePricing.price_per_page)
            .join(PricingTier, PricingTier.id == PagePricing.tier_id)
            .where(
                PricingTier.is_active.is_(True),
                PricingTier.currency == default_currency(),
                PagePricing.minimum_pages <= page_count,
                PagePricing.maximum_pages >= page_count,
            )
            .order_by(PagePricing.price_per_page)
        )
        if page_rule is None:
            raise ConflictError("Additional-page pricing is not configured for this book.")
        page_rate = page_rule
    extra_page_price = money(page_rate, "additional-page price")
    price = calculate_book_price(base_price, page_count, base_pages, extra_page_price)
    return {
        "bookId": product.id,
        "pageCount": page_count,
        "basePageCount": base_pages,
        "extraPageCount": price["extraPageCount"],
        "pdfPrice": str(calculate_pdf_price(product)),
        "hardCopyBasePrice": str(base_price),
        "additionalPages": str(price["additionalPages"]),
        "hardCopyEstimate": str(price["total"]),
        "extraPagePrice": str(extra_page_price),
        "plan": plan,
        "currency": default_currency(),
        "estimateOnly": True,
    }


def _active_discount(code: str, currency: str) -> DiscountCode:
    discount = db.session.scalar(
        select(DiscountCode).where(func.upper(DiscountCode.code) == code).with_for_update()
    )
    if discount is None or not _discount_is_available(discount, currency):
        raise ConflictError("The discount code is invalid, expired, or no longer available.")
    return discount


def _discount_is_available(discount: DiscountCode, currency: str) -> bool:
    now = datetime.now(UTC)
    starts_at = discount.starts_at
    ends_at = discount.ends_at
    if starts_at and starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    if ends_at and ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=UTC)
    return bool(
        discount.is_active
        and (discount.currency is None or discount.currency.upper() == currency.upper())
        and (discount.maximum_uses is None or discount.uses_count < discount.maximum_uses)
        and (starts_at is None or starts_at <= now)
        and (ends_at is None or ends_at > now)
    )


def _validate_address(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValidationError("Shipping address must be an object.")
    fields = {
        "fullName": 160,
        "line1": 200,
        "line2": 200,
        "city": 120,
        "region": 120,
        "postalCode": 30,
        "country": 2,
        "phone": 40,
    }
    normalized = {}
    for field, maximum in fields.items():
        raw = value.get(field, "")
        if not isinstance(raw, str) or len(raw.strip()) > maximum:
            raise ValidationError(f"Shipping address field {field} is invalid.", {field: "invalid"})
        text = raw.strip()
        if field != "line2" and not text:
            raise ValidationError(f"Shipping address field {field} is required.", {field: "required"})
        normalized[field] = text.upper() if field == "country" else text
    if len(normalized["country"]) != 2 or not normalized["country"].isalpha():
        raise ValidationError("Country must be a two-letter ISO code.", {"country": "invalid"})
    return normalized


def _choice(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 60:
        raise ValidationError(f"{field} is invalid.", {field: "invalid"})
    return value.strip().lower()


def _matches_choice(name: str, choice: str) -> bool:
    def normalize(value: str) -> str:
        return "".join(char for char in value.casefold() if char.isalnum())

    normalized_name = normalize(name)
    normalized_choice = normalize(choice)
    return normalized_choice == normalized_name or normalized_choice in normalized_name


def _money(value, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as failure:
        raise ConflictError(f"{field} is not configured in the catalog.") from failure
    if not parsed.is_finite() or parsed < 0 or parsed.as_tuple().exponent < -2:
        raise ConflictError(f"{field} is not a valid catalog price.")
    return parsed.quantize(Decimal("0.01"))


def _decimal(value, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as failure:
        raise ValidationError(f"The project {field} is invalid.") from failure
    if not parsed.is_finite() or parsed <= 0:
        raise ValidationError(f"The project {field} is invalid.")
    return parsed


def _order_number(prefix: str) -> str:
    return f"{prefix}-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:10].upper()}"


def _history_row(order_id: str, kind: str, status: str, note: str):
    return OrderStatusHistory(
        pdf_order_id=order_id if kind == "pdf" else None,
        print_order_id=order_id if kind == "print" else None,
        status=status,
        note=note[:500],
    )


def _history(order_id: str, kind: str) -> list[dict]:
    column = OrderStatusHistory.pdf_order_id if kind == "pdf" else OrderStatusHistory.print_order_id
    items = db.session.scalars(
        select(OrderStatusHistory).where(column == order_id).order_by(OrderStatusHistory.created_at)
    ).all()
    return [{"status": item.status, "note": item.note, "createdAt": item.created_at.isoformat()} for item in items]
