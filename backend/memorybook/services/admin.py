from __future__ import annotations

import hashlib
import copy
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from flask import request
from sqlalchemy import case, func, or_, select
from werkzeug.exceptions import NotFound

from memorybook.errors import ConflictError, ServiceUnavailableError, ValidationError
from memorybook.extensions import db
from memorybook.integrations.asset_storage import get_asset_storage
from memorybook.integrations.image_validation import validate_and_sanitize_image
from memorybook.integrations.email import send_email
from memorybook.models import (
    AdminActivityLog,
    BookCategory,
    BookCollection,
    BookProduct,
    BookSize,
    BookTemplate,
    BookTemplateVersion,
    BookVariant,
    CoverType,
    DiscountCode,
    DownloadEntitlement,
    DownloadHistory,
    EmailLog,
    Favorite,
    GeneratedFile,
    OrderStatusHistory,
    PagePricing,
    PaperType,
    Payment,
    PaymentAttempt,
    PdfOrder,
    PdfJob,
    ProjectAsset,
    PlatformSetting,
    PricingRule,
    PricingTier,
    PrintOrder,
    PrintOrderItem,
    ProjectRevision,
    Refund,
    Shipment,
    ShippingRate,
    SupportMessage,
    SupportTicket,
    TemplateElement,
    TemplatePage,
    User,
    UserProject,
)
from memorybook.schemas.catalog_projects import AssetMetadataSchema, ProjectDocumentSchema
from memorybook.services.catalog_projects import (
    is_project_private,
    serialize_book,
    serialize_category,
    serialize_collection,
    serialize_template,
)
from memorybook.services.notifications import queue_order_event
from memorybook.services.pricing import default_currency, validate_product_pricing

ADMIN_PRINT_STATES = {
    "pending_payment",
    "order_placed",
    "payment_confirmed",
    "processing",
    "printed",
    "design_verified",
    "in_production",
    "quality_check",
    "packed",
    "shipped",
    "out_for_delivery",
    "delivered",
    "cancelled",
    "cancellation_requested",
    "refunded",
}

PRINT_STATUS_TRANSITIONS = {
    "pending_payment": {"payment_confirmed", "cancelled"},
    "order_placed": {"payment_confirmed", "cancellation_requested", "cancelled"},
    "payment_confirmed": {"processing", "cancellation_requested"},
    "processing": {"printed", "cancellation_requested"},
    "printed": {"shipped"},
    "design_verified": {"processing"},
    "in_production": {"printed"},
    "quality_check": {"printed", "packed"},
    "packed": {"shipped"},
    "shipped": {"out_for_delivery", "delivered"},
    "out_for_delivery": {"delivered"},
    "cancellation_requested": {"cancelled"},
}


def _new_book_design_document(book: BookProduct, template: BookTemplate, page_count: int) -> dict:
    page_ids = [str(uuid4()) for _ in range(page_count + 1)]
    category = db.session.get(BookCategory, book.category_id)
    pages = [{
        "id": page_ids[0],
        "type": "cover",
        "label": "Cover",
        "background": {"color": "#e8ece5"},
        "layout": "cover",
        "elements": [],
    }]
    pages.extend({
        "id": page_ids[index],
        "type": "page",
        "label": f"Page {index}",
        "background": {"color": "#fffdf9"},
        "layout": "blank",
        "elements": [],
    } for index in range(1, len(page_ids)))
    title = book.title
    now = datetime.now(UTC).isoformat()
    return {
        "schemaVersion": 1,
        "metadata": {
            "id": template.id,
            "title": title,
            "createdAt": now,
            "updatedAt": now,
        },
        "book": {
            "size": {"width": 8, "height": 8} if book.book_type == "LIGHT" else {"width": 10, "height": 10},
            "pageCount": page_count,
            "coverType": "Hardcover",
            "template": {
                "id": template.id,
                "title": template.name,
                "category": category.name if category else "Custom",
                "image": None,
            },
        },
        "pageOrder": page_ids,
        "pages": pages,
        "assets": [],
        "styles": {"fontFamily": "DM Sans", "color": "#1d2824", "background": "#fffdf9"},
        "cover": {
            "pageId": page_ids[0],
            "title": title,
            "finish": "Hardcover",
            "design": {
                "bleedInches": 0.125,
                "front": {
                    "title": title, "subtitle": "", "backgroundColor": "#e8ece5", "textColor": "#20352d",
                    "fontFamily": "Georgia", "layout": "center", "photoAssetId": None,
                },
                "spine": {
                    "title": title, "backgroundColor": "#e8ece5", "textColor": "#20352d", "fontFamily": "Georgia",
                },
                "back": {
                    "title": title, "description": "", "backgroundColor": "#f4eee5", "textColor": "#20352d",
                    "fontFamily": "Georgia",
                },
            },
        },
    }


def ensure_book_design(product_id: str) -> dict:
    book = db.session.scalar(
        select(BookProduct).where(BookProduct.id == product_id, BookProduct.deleted_at.is_(None)).with_for_update()
    )
    if book is None:
        raise NotFound("Book product was not found.")
    template = db.session.scalar(
        select(BookTemplate).where(BookTemplate.product_id == book.id, BookTemplate.deleted_at.is_(None))
        .order_by(BookTemplate.updated_at.desc())
    )
    if template is None:
        template = BookTemplate(
            product_id=book.id,
            category_id=book.category_id,
            name=book.title,
            slug=f"{book.slug}-design-{uuid4().hex[:8]}"[:180],
            description=book.description,
            version=1,
            is_active=False,
        )
        db.session.add(template)
        db.session.flush()
    if template.design_document is None:
        template.design_document = _new_book_design_document(
            book, template, min(max(book.page_count_min or 24, 1), 500)
        )
        _commit("book.design_created", "book_template", template.id, {"productId": book.id})
    return {
        "product": _product_dict(book),
        "template": serialize_template(template, include_pages=True, include_design=True),
    }


def _validated_book_design(document: object, template: BookTemplate) -> dict:
    validated = ProjectDocumentSchema.load(document)
    assets_by_id = {}
    for asset in validated["assets"]:
        key = asset.get("assetKey")
        filename = asset.get("name")
        mime_type = asset.get("mimeType")
        size = asset.get("size")
        checksum = asset.get("checksum")
        if not isinstance(key, str) or not key.startswith(("catalog/", "admin-design/")) or len(key) > 1024:
            raise ValidationError("Design images must reference persisted image assets.", {"assets": "invalid_key"})
        AssetMetadataSchema.load(filename, mime_type, size)
        if not isinstance(checksum, str) or len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum.lower()):
            raise ValidationError("Design image checksums are invalid.", {"assets": "invalid_checksum"})
        if key in assets_by_id.values():
            raise ValidationError("A catalog asset may only appear once in the design.", {"assets": "duplicate"})
        assets_by_id[asset["id"]] = key
        asset.pop("src", None)
    for page in validated["pages"]:
        for element in page.get("elements", []):
            if element.get("type") == "image":
                if element.get("assetId") not in assets_by_id:
                    raise ValidationError("Design photos must reference uploaded catalog assets.", {"assetId": "invalid"})
                element.pop("src", None)
    cover = validated.get("cover", {}).get("design", {})
    front_asset_id = (cover.get("front") or {}).get("photoAssetId")
    if front_asset_id is not None and front_asset_id not in assets_by_id:
        raise ValidationError("The cover photo must reference an uploaded catalog asset.", {"photoAssetId": "invalid"})
    validated["metadata"]["id"] = template.id
    validated["metadata"].pop("owner", None)
    return validated


def save_book_design(product_id: str, document: object, expected_version: int) -> dict:
    result = ensure_book_design(product_id)
    template = db.session.get(BookTemplate, result["template"]["id"])
    if template.version != expected_version:
        raise ConflictError(
            "This book design changed in another session. Reload the latest design before saving.",
            {"expectedVersion": expected_version, "currentVersion": template.version},
        )
    if template.is_active:
        db.session.add(BookTemplateVersion(
            template_id=template.id,
            version=template.version,
            document=_template_document(template),
        ))
    template.design_document = _validated_book_design(document, template)
    template.version += 1
    _commit("book.design_saved", "book_template", template.id, {"version": template.version})
    return {
        "product": _product_dict(db.session.get(BookProduct, product_id)),
        "template": serialize_template(template, include_pages=True, include_design=True),
    }


def publish_book_design(product_id: str, expected_version: int | None = None) -> dict:
    result = ensure_book_design(product_id)
    book = db.session.get(BookProduct, product_id)
    template = db.session.get(BookTemplate, result["template"]["id"])
    if expected_version is not None and template.version != expected_version:
        raise ConflictError(
            "This book design changed in another session. Reload the latest design before publishing.",
            {"expectedVersion": expected_version, "currentVersion": template.version},
        )
    if not template.design_document:
        raise ValidationError("Save a book design before publishing.", {"design": "required"})
    document = _validated_book_design(template.design_document, template)
    if not document["pages"] or not any(page.get("elements") for page in document["pages"]):
        raise ValidationError("Add at least one designed page element before publishing.", {"design": "incomplete"})
    template.published_design_document = copy.deepcopy(document)
    template.published_version = template.version
    template.is_active = True
    _commit("book.design_published", "book_product", book.id, {
        "templateId": template.id,
        "templateVersion": template.published_version,
    })
    return {
        "product": _product_dict(book),
        "template": serialize_template(template, include_pages=True, include_design=True),
    }


def unpublish_book_design(product_id: str) -> dict:
    book = db.session.get(BookProduct, product_id)
    if book is None or book.deleted_at is not None:
        raise NotFound("Book product was not found.")
    if book.is_active:
        raise ConflictError(
            "Unpublish the product before unpublishing its master design.",
            {"product": "published"},
        )
    templates = db.session.scalars(
        select(BookTemplate).where(BookTemplate.product_id == book.id, BookTemplate.deleted_at.is_(None))
    ).all()
    for template in templates:
        template.is_active = False
    _commit("book.design_unpublished", "book_product", book.id)
    return {
        "product": _product_dict(book),
        "template": serialize_template(templates[0], include_pages=True, include_design=True) if templates else None,
    }


def _text(data: dict, field: str, *, required: bool = False, maximum: int = 200) -> str | None:
    value = data.get(field)
    if value is None:
        if required:
            raise ValidationError(f"{field} is required.", {field: "required"})
        return None
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > maximum:
        raise ValidationError(f"{field} is invalid.", {field: "invalid"})
    return value.strip()


def _money(value, field: str, *, optional: bool = False) -> Decimal | None:
    if value is None and optional:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as failure:
        raise ValidationError(f"{field} must be a valid amount.", {field: "invalid"}) from failure
    if not parsed.is_finite() or parsed < 0 or parsed.as_tuple().exponent < -2:
        raise ValidationError(f"{field} must be a nonnegative amount with at most two decimal places.", {field: "invalid"})
    return parsed


def _positive_int(value, field: str, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a positive integer.", {field: "invalid"})
    try:
        parsed = int(value)
    except (ValueError, TypeError) as failure:
        raise ValidationError(f"{field} must be a positive integer.", {field: "invalid"}) from failure
    if parsed < 1 or str(value).strip() not in {str(parsed), f"{parsed}.0"}:
        raise ValidationError(f"{field} must be a positive integer.", {field: "invalid"})
    return parsed


def _body_dict(value, field: str) -> dict:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be an object.", {field: "invalid"})
    return value


def _audit(action: str, target_type: str, target_id: str | None, details: dict | None = None) -> None:
    from memorybook.permissions import get_authenticated_user

    user = get_authenticated_user()
    db.session.add(AdminActivityLog(
        actor_user_id=user.id if user else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
        ip_address=request.remote_addr,
    ))


def _commit(action: str, target_type: str, target_id: str | None, details: dict | None = None) -> None:
    _audit(action, target_type, target_id, details)
    db.session.commit()


def _paginate(query, page: int, per_page: int) -> dict:
    if page < 1 or per_page < 1 or per_page > 100:
        raise ValidationError("Pagination must use a positive page and perPage between 1 and 100.", {"pagination": "invalid"})
    total = db.session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    items = db.session.scalars(query.offset((page - 1) * per_page).limit(per_page)).all()
    return {"items": items, "pagination": {
        "page": page, "perPage": per_page, "totalItems": total,
        "totalPages": (total + per_page - 1) // per_page,
    }}


def _page_params(args) -> tuple[int, int]:
    try:
        return int(args.get("page", "1")), int(args.get("perPage", "25"))
    except ValueError as failure:
        raise ValidationError("Pagination values must be integers.", {"pagination": "invalid"}) from failure


def _upload_admin_image(file, owner: User, namespace: str) -> dict:
    file.stream.seek(0, 2)
    byte_size = file.stream.tell()
    file.stream.seek(0)
    metadata = AssetMetadataSchema.load(file.filename, file.mimetype, byte_size)
    image, width, height = validate_and_sanitize_image(file.stream, metadata["mime_type"])
    metadata["byte_size"] = image.getbuffer().nbytes
    digest = hashlib.sha256(image.getbuffer()).hexdigest()
    key = f"{namespace}/{owner.id}/{uuid4().hex}"
    storage = get_asset_storage()
    storage.upload(key, image, metadata["mime_type"])
    event = "catalog_asset.uploaded" if namespace == "catalog" else "admin_design_asset.uploaded"
    _commit(event, "catalog_asset" if namespace == "catalog" else "admin_design_asset", owner.id, {
        "assetKey": key,
        "filename": metadata["filename"],
        "mimeType": metadata["mime_type"],
        "size": metadata["byte_size"],
        "checksum": digest,
        "width": width,
        "height": height,
    })
    return {
        "assetKey": key,
        "url": storage.public_download_url(key) if namespace == "catalog" else storage.private_download_url(key),
        "filename": metadata["filename"],
        "mimeType": metadata["mime_type"],
        "size": metadata["byte_size"],
        "checksum": digest,
        "width": width,
        "height": height,
    }


def upload_catalog_asset(file, owner: User) -> dict:
    return _upload_admin_image(file, owner, "catalog")


def upload_admin_design_asset(file, owner: User) -> dict:
    return _upload_admin_image(file, owner, "admin-design")


def _template_document(template: BookTemplate) -> dict:
    pages = db.session.scalars(
        select(TemplatePage).where(TemplatePage.template_id == template.id).order_by(TemplatePage.page_number)
    ).all()
    return {
        "name": template.name,
        "slug": template.slug,
        "description": template.description,
        "productId": template.product_id,
        "categoryId": template.category_id,
        "previewAssetKey": template.preview_asset_key,
        "designDocument": template.design_document,
        "publishedDesignDocument": template.published_design_document,
        "publishedVersion": template.published_version,
        "pages": [{
            "pageNumber": page.page_number,
            "type": page.page_type,
            "layout": page.layout_key,
            "background": page.background,
            "elements": [{
                "type": element.element_type,
                "sortOrder": element.sort_order,
                "x": float(element.x),
                "y": float(element.y),
                "width": float(element.width),
                "height": float(element.height),
                "content": element.content or {},
            } for element in db.session.scalars(
                select(TemplateElement).where(TemplateElement.template_page_id == page.id)
                .order_by(TemplateElement.sort_order)
            ).all()],
        } for page in pages],
    }


def _validate_template_pages(pages) -> list[dict]:
    if not isinstance(pages, list) or len(pages) > 300:
        raise ValidationError("Template pages must be a list of at most 300 pages.", {"pages": "invalid"})
    validated = []
    for expected_number, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            raise ValidationError("Each template page must be an object.", {"pages": "invalid"})
        number = _positive_int(page.get("pageNumber", expected_number), "pageNumber")
        if number != expected_number:
            raise ValidationError("Template pages must be in sequential order.", {"pages": "order_invalid"})
        page_type = page.get("type", "interior")
        layout = page.get("layout", "single-photo")
        elements = page.get("elements", [])
        if page_type not in {"cover", "interior", "back_cover"} or not isinstance(layout, str) or len(layout) > 100:
            raise ValidationError("Template page type or layout is invalid.", {"pages": "invalid"})
        if not isinstance(elements, list) or len(elements) > 100:
            raise ValidationError("Template page elements must be a list of at most 100 items.", {"pages": "invalid"})
        valid_elements = []
        for order, element in enumerate(elements):
            if not isinstance(element, dict) or element.get("type") not in {"image", "text", "shape"}:
                raise ValidationError("Template element type is invalid.", {"elements": "invalid"})
            try:
                geometry = {key: float(element.get(key)) for key in ("x", "y", "width", "height")}
            except (TypeError, ValueError) as failure:
                raise ValidationError("Template element geometry is invalid.", {"elements": "invalid"}) from failure
            if not (
                0 <= geometry["x"] <= 1 and 0 <= geometry["y"] <= 1
                and 0 < geometry["width"] <= 1 and 0 < geometry["height"] <= 1
                and geometry["x"] + geometry["width"] <= 1
                and geometry["y"] + geometry["height"] <= 1
            ):
                raise ValidationError("Template elements must use normalized page coordinates.", {"elements": "out_of_bounds"})
            content = element.get("content", {})
            if not isinstance(content, dict):
                raise ValidationError("Template element content must be an object.", {"elements": "invalid"})
            valid_elements.append({
                **geometry,
                "type": element["type"],
                "sortOrder": order,
                "content": content,
            })
        background = page.get("background")
        if background is not None and (not isinstance(background, str) or len(background) > 100):
            raise ValidationError("Template page background is invalid.", {"background": "invalid"})
        validated.append({
            "pageNumber": number,
            "type": page_type,
            "layout": layout,
            "background": background,
            "elements": valid_elements,
        })
    return validated


def _save_template_pages(template: BookTemplate, pages: list[dict]) -> None:
    existing = db.session.scalars(select(TemplatePage).where(TemplatePage.template_id == template.id)).all()
    for page in existing:
        db.session.delete(page)
    db.session.flush()
    for data in pages:
        page = TemplatePage(
            template_id=template.id,
            page_number=data["pageNumber"],
            page_type=data["type"],
            layout_key=data["layout"],
            background=data["background"],
        )
        db.session.add(page)
        db.session.flush()
        for element in data["elements"]:
            db.session.add(TemplateElement(
                template_page_id=page.id,
                element_type=element["type"],
                sort_order=element["sortOrder"],
                x=element["x"],
                y=element["y"],
                width=element["width"],
                height=element["height"],
                content=element["content"],
            ))


def _analytics_days(value: object) -> int:
    try:
        days = int(value or 30)
    except (TypeError, ValueError) as failure:
        raise ValidationError("Analytics days must be an integer from 1 to 366.", {"days": "invalid"}) from failure
    if not 1 <= days <= 366:
        raise ValidationError("Analytics days must be an integer from 1 to 366.", {"days": "invalid"})
    return days


def _daily_totals(model, amount_column, start: datetime, *, paid_only: bool = False) -> dict[str, Decimal]:
    query = select(func.date(model.created_at), func.coalesce(func.sum(amount_column), 0)).where(
        model.created_at >= start,
    )
    if paid_only:
        query = query.where(model.paid_at.is_not(None))
    rows = db.session.execute(query.group_by(func.date(model.created_at))).all()
    return {str(day): Decimal(amount or 0) for day, amount in rows}


def _book_sales(start: datetime) -> list[dict]:
    sales: dict[str, dict] = {}
    for model in (PdfOrder, PrintOrder):
        rows = db.session.execute(
            select(
                BookProduct.id,
                BookProduct.title,
                func.count(model.id),
                func.coalesce(func.sum(model.total_amount), 0),
            )
            .select_from(model)
            .join(UserProject, UserProject.id == model.project_id)
            .join(BookProduct, BookProduct.id == UserProject.product_id)
            .where(model.paid_at.is_not(None), model.created_at >= start)
            .group_by(BookProduct.id, BookProduct.title)
        ).all()
        for book_id, title, count, revenue in rows:
            item = sales.setdefault(book_id, {"id": book_id, "title": title, "orders": 0, "revenue": Decimal("0")})
            item["orders"] += count
            item["revenue"] += Decimal(revenue or 0)
    return [
        {**item, "revenue": str(item["revenue"])}
        for item in sorted(sales.values(), key=lambda row: (row["orders"], row["revenue"]), reverse=True)[:8]
    ]


def _downloaded_books(start: datetime) -> list[dict]:
    rows = db.session.execute(
        select(BookProduct.id, BookProduct.title, func.count(DownloadHistory.id))
        .select_from(DownloadHistory)
        .join(DownloadEntitlement, DownloadEntitlement.id == DownloadHistory.entitlement_id)
        .join(PdfOrder, PdfOrder.id == DownloadEntitlement.pdf_order_id)
        .join(UserProject, UserProject.id == PdfOrder.project_id)
        .join(BookProduct, BookProduct.id == UserProject.product_id)
        .where(DownloadHistory.downloaded_at >= start)
        .group_by(BookProduct.id, BookProduct.title)
        .order_by(func.count(DownloadHistory.id).desc(), BookProduct.title)
        .limit(8)
    ).all()
    return [{"id": book_id, "title": title, "downloads": count} for book_id, title, count in rows]


def _favorited_books() -> list[dict]:
    rows = db.session.execute(
        select(BookProduct.id, BookProduct.title, func.count(Favorite.id))
        .select_from(Favorite)
        .join(BookProduct, BookProduct.id == Favorite.book_id)
        .group_by(BookProduct.id, BookProduct.title)
        .order_by(func.count(Favorite.id).desc(), BookProduct.title)
        .limit(8)
    ).all()
    return [{"id": book_id, "title": title, "favorites": count} for book_id, title, count in rows]


def revenue_chart(days: object = 30) -> list[dict]:
    count = _analytics_days(days)
    start = datetime.now(UTC) - timedelta(days=count - 1)
    pdf = _daily_totals(PdfOrder, PdfOrder.total_amount, start, paid_only=True)
    printing = _daily_totals(PrintOrder, PrintOrder.total_amount, start, paid_only=True)
    return [{
        "date": (start + timedelta(days=offset)).date().isoformat(),
        "revenue": str(
            pdf.get((start + timedelta(days=offset)).date().isoformat(), Decimal("0"))
            + printing.get((start + timedelta(days=offset)).date().isoformat(), Decimal("0"))
        ),
    } for offset in range(count)]


def downloads_chart(days: object = 30) -> list[dict]:
    count = _analytics_days(days)
    start = datetime.now(UTC) - timedelta(days=count - 1)
    rows = db.session.execute(
        select(func.date(DownloadHistory.downloaded_at), func.count(DownloadHistory.id))
        .where(DownloadHistory.downloaded_at >= start)
        .group_by(func.date(DownloadHistory.downloaded_at))
    ).all()
    values = {str(day): total for day, total in rows}
    return [{
        "date": (start + timedelta(days=offset)).date().isoformat(),
        "downloads": values.get((start + timedelta(days=offset)).date().isoformat(), 0),
    } for offset in range(count)]


def recent_admin_payments(limit: int = 10) -> list[dict]:
    rows = db.session.execute(
        select(Payment, User.full_name, User.email, PdfOrder.order_number, PrintOrder.order_number)
        .join(User, User.id == Payment.user_id)
        .outerjoin(PdfOrder, PdfOrder.id == Payment.pdf_order_id)
        .outerjoin(PrintOrder, PrintOrder.id == Payment.print_order_id)
        .order_by(Payment.created_at.desc())
        .limit(max(1, min(limit, 50)))
    ).all()
    return [{
        "id": payment.id,
        "userName": name or "Name not provided",
        "userEmail": email,
        "orderNumber": pdf_number or print_number,
        "status": payment.status,
        "provider": payment.provider,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "createdAt": payment.created_at.isoformat(),
    } for payment, name, email, pdf_number, print_number in rows]


def top_selling_books(days: object = 30) -> list[dict]:
    count = _analytics_days(days)
    return _book_sales(datetime.now(UTC) - timedelta(days=count - 1))


def most_downloaded_books(days: object = 30) -> list[dict]:
    count = _analytics_days(days)
    return _downloaded_books(datetime.now(UTC) - timedelta(days=count - 1))


def most_favorited_books() -> list[dict]:
    return _favorited_books()


def recent_admin_users(limit: int = 10) -> list[dict]:
    users = db.session.scalars(
        select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc()).limit(max(1, min(limit, 50)))
    ).all()
    return [{
        "id": user.id,
        "name": user.full_name or "Name not provided",
        "email": user.email,
        "createdAt": user.created_at.isoformat(),
    } for user in users]


def dashboard_metrics(days: object = 30) -> dict:
    days = _analytics_days(days)
    start = datetime.now(UTC) - timedelta(days=days - 1)
    revenue_pdf = db.session.scalar(select(func.coalesce(func.sum(PdfOrder.total_amount), 0)).where(PdfOrder.paid_at.is_not(None)))
    revenue_print = db.session.scalar(select(func.coalesce(func.sum(PrintOrder.total_amount), 0)).where(PrintOrder.paid_at.is_not(None)))
    pdf_count = db.session.scalar(select(func.count()).select_from(PdfOrder).where(PdfOrder.paid_at.is_not(None))) or 0
    print_count = db.session.scalar(select(func.count()).select_from(PrintOrder)) or 0
    pending = (db.session.scalar(select(func.count()).select_from(PdfOrder).where(PdfOrder.status == "pending")) or 0) + (
        db.session.scalar(select(func.count()).select_from(PrintOrder).where(PrintOrder.status.in_(["pending", "payment_confirmed"]))) or 0
    )
    production = db.session.scalar(select(func.count()).select_from(PrintOrder).where(PrintOrder.status == "in_production")) or 0
    recent_prints = db.session.scalars(select(PrintOrder).order_by(PrintOrder.created_at.desc()).limit(6)).all()
    recent_pdfs = db.session.scalars(select(PdfOrder).order_by(PdfOrder.created_at.desc()).limit(6)).all()
    recent = [
        {"id": row.id, "orderNumber": row.order_number, "type": kind, "status": row.status,
         "amount": str(row.total_amount), "createdAt": row.created_at.isoformat()}
        for kind, rows in (("print", recent_prints), ("pdf", recent_pdfs)) for row in rows
    ]
    recent.sort(key=lambda item: item["createdAt"], reverse=True)
    revenue_series = revenue_chart(days)
    downloads_series = downloads_chart(days)
    pending_manual = db.session.scalar(
        select(func.count(func.distinct(Payment.id)))
        .join(PaymentAttempt, PaymentAttempt.payment_id == Payment.id)
        .where(
            Payment.provider == "manual",
            Payment.status == "pending",
            PaymentAttempt.status == "submitted",
        )
    ) or 0
    orders_to_ship = db.session.scalar(
        select(func.count()).select_from(PrintOrder).where(PrintOrder.status.in_(("printed", "packed")))
    ) or 0
    recent_users = db.session.scalars(
        select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc()).limit(8)
    ).all()
    return {
        "totalUsers": db.session.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))) or 0,
        "activeProjects": db.session.scalar(select(func.count()).select_from(UserProject).where(UserProject.status != "deleted")) or 0,
        "pdfPurchases": pdf_count,
        "printOrders": print_count,
        "revenue": str(Decimal(revenue_pdf or 0) + Decimal(revenue_print or 0)),
        "pendingOrders": pending,
        "booksInProduction": production,
        "favoritesCount": db.session.scalar(select(func.count()).select_from(Favorite)) or 0,
        "recentOrders": recent[:8],
        "currency": default_currency(),
        "analyticsDays": days,
        "revenueSeries": revenue_series,
        "downloadsSeries": downloads_series,
        "bestSellingBooks": _book_sales(start),
        "mostDownloadedBooks": _downloaded_books(start),
        "mostFavoritedBooks": _favorited_books(),
        "recentUsers": [{
            "id": user.id,
            "name": user.full_name or "Name not provided",
            "email": user.email,
            "createdAt": user.created_at.isoformat(),
        } for user in recent_users],
        "needsAttention": {"manualPayments": pending_manual, "ordersToShip": orders_to_ship},
    }


def list_users(args) -> dict:
    page, per_page = _page_params(args)
    query = select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc())
    search = args.get("search", "").strip()[:120]
    if search:
        term = f"%{search}%"
        query = query.where(or_(User.email.ilike(term), User.full_name.ilike(term)))
    result = _paginate(query, page, per_page)
    result["items"] = [{
        **user.public_dict(), "createdAt": user.created_at.isoformat(),
    } for user in result["items"]]
    return result


def set_user_status(user_id: str, data: dict) -> dict:
    user = db.session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFound("User was not found.")
    if not isinstance(data.get("isActive"), bool):
        raise ValidationError("isActive must be a boolean.", {"isActive": "invalid"})
    from memorybook.permissions import get_authenticated_user
    if user.id == get_authenticated_user().id and not data["isActive"]:
        raise ConflictError("You cannot disable your own active admin account.")
    if user.is_active != data["isActive"]:
        user.is_active = data["isActive"]
        _commit("user.status_changed", "user", user.id, {"isActive": user.is_active})
    return user.public_dict()


def _category_by_id(category_id: str | None):
    if not category_id:
        return None
    item = db.session.get(BookCategory, category_id)
    if item is None or item.deleted_at is not None:
        raise ValidationError("The selected category does not exist.", {"categoryId": "not_found"})
    return item


def _collection_by_id(collection_id: str | None):
    if not collection_id:
        return None
    item = db.session.get(BookCollection, collection_id)
    if item is None or item.deleted_at is not None:
        raise ValidationError("The selected collection does not exist.", {"collectionId": "not_found"})
    return item


def _product_dict(book: BookProduct) -> dict:
    master_design = db.session.scalar(
        select(BookTemplate)
        .where(BookTemplate.product_id == book.id, BookTemplate.deleted_at.is_(None))
        .order_by(BookTemplate.updated_at.desc())
        .limit(1)
    )
    return {
        **serialize_book(book, include_favorite_count=True),
        "isPublished": book.is_active,
        "coverAssetKey": book.cover_asset_key,
        "adminMetadata": book.admin_metadata or {},
        "masterDesignStatus": (
            "published"
            if master_design and master_design.is_active and master_design.published_design_document
            else "draft" if master_design and master_design.design_document
            else "not_started"
        ),
        "masterDesignVersion": master_design.version if master_design else None,
        "publishedDesignVersion": master_design.published_version if master_design else None,
    }


def _validate_product_metadata(value: dict, previous: dict | None = None) -> dict:
    metadata = dict(value)
    for field, model in (
        ("sizeOptions", BookSize),
        ("coverOptions", CoverType),
        ("paperOptions", PaperType),
    ):
        if field in metadata:
            identifiers = metadata[field]
            if not isinstance(identifiers, list) or len(identifiers) > 50 or any(not isinstance(item, str) for item in identifiers):
                raise ValidationError(f"{field} must be a list of option IDs.", {field: "invalid"})
            found = set(db.session.scalars(select(model.id).where(model.id.in_(identifiers))).all()) if identifiers else set()
            if set(identifiers) != found:
                raise ValidationError(f"{field} contains an unknown option.", {field: "not_found"})
    if "pageCountOptions" in metadata:
        page_counts = metadata["pageCountOptions"]
        if not isinstance(page_counts, list) or len(page_counts) > 100:
            raise ValidationError("pageCountOptions must be a list.", {"pageCountOptions": "invalid"})
        metadata["pageCountOptions"] = [_positive_int(item, "pageCountOptions") for item in page_counts]
    if "basePageCount" in metadata:
        metadata["basePageCount"] = _positive_int(metadata["basePageCount"], "basePageCount")
    if "evenPageCountRequired" in metadata and not isinstance(metadata["evenPageCountRequired"], bool):
        raise ValidationError("evenPageCountRequired must be a boolean.", {"evenPageCountRequired": "invalid"})
    if "printingTiers" in metadata:
        tiers = metadata["printingTiers"]
        if not isinstance(tiers, list) or len(tiers) > 20 or any(not isinstance(item, str) or not item.strip() for item in tiers):
            raise ValidationError("printingTiers contains an unsupported tier.", {"printingTiers": "invalid"})
        if len(set(tiers)) != len(tiers):
            raise ValidationError("printingTiers cannot contain duplicates.", {"printingTiers": "duplicate"})
        unavailable = set(tiers) - set((previous or {}).get("printingTiers", []))
        found = set(db.session.scalars(
            select(PricingTier.code).where(
                PricingTier.code.in_(unavailable),
                PricingTier.is_active.is_(True),
            )
        ).all()) if unavailable else set()
        if found != unavailable:
            raise ValidationError("printingTiers contains an inactive or unavailable tier.", {"printingTiers": "unavailable"})
    if "previewImageKeys" in metadata:
        image_keys = metadata["previewImageKeys"]
        if not isinstance(image_keys, list) or len(image_keys) > 12 or any(
            not isinstance(item, str) or not item.startswith("catalog/") or len(item) > 1024 for item in image_keys
        ):
            raise ValidationError("previewImageKeys must contain at most 12 catalog asset keys.", {"previewImageKeys": "invalid"})
    if "dimensions" in metadata:
        dimensions = _body_dict(metadata["dimensions"], "dimensions")
        width = _money(dimensions.get("widthMm"), "dimensions.widthMm")
        height = _money(dimensions.get("heightMm"), "dimensions.heightMm")
        if width == 0 or height == 0:
            raise ValidationError("Book dimensions must be greater than zero.", {"dimensions": "invalid"})
        metadata["dimensions"] = {"widthMm": str(width), "heightMm": str(height)}
    for field in ("pdfPrice", "printingPrice", "extraPagePrice"):
        if field in metadata:
            if field == "extraPagePrice" and metadata[field] in (None, ""):
                metadata.pop(field)
            else:
                metadata[field] = str(_money(metadata[field], field))
    if "productionDays" in metadata:
        metadata["productionDays"] = _positive_int(metadata["productionDays"], "productionDays")
    return metadata


def list_products(args) -> dict:
    page, per_page = _page_params(args)
    query = select(BookProduct).where(BookProduct.deleted_at.is_(None)).order_by(BookProduct.updated_at.desc())
    if args.get("published") in {"true", "false"}:
        query = query.where(BookProduct.is_active.is_(args.get("published") == "true"))
    if args.get("categoryId"):
        query = query.where(BookProduct.category_id == args["categoryId"])
    search = args.get("search", "").strip()[:120]
    if search:
        query = query.where(BookProduct.title.ilike(f"%{search}%"))
    result = _paginate(query, page, per_page)
    result["items"] = [_product_dict(item) for item in result["items"]]
    return result


def save_product(data: dict, product_id: str | None = None) -> dict:
    item = db.session.get(BookProduct, product_id) if product_id else BookProduct()
    if product_id and (item is None or item.deleted_at is not None):
        raise NotFound("Book product was not found.")
    category = _category_by_id(data.get("categoryId", item.category_id))
    if category is None:
        raise ValidationError("categoryId is required.", {"categoryId": "required"})
    if not category.is_active and category.id != item.category_id:
        raise ValidationError("Choose an active category for a book product.", {"categoryId": "inactive"})
    collection = _collection_by_id(data.get("collectionId", item.collection_id))
    if collection is not None:
        if collection.category_id is None:
            raise ValidationError(
                "The selected collection has no resolved category. Assign a category to it before using it for a book.",
                {"collectionId": "unresolved_category"},
            )
        if collection.category_id != category.id:
            raise ValidationError(
                "The selected collection does not belong to the chosen category.",
                {"collectionId": "category_mismatch"},
            )
        if not collection.is_active and collection.id != item.collection_id:
            raise ValidationError("Choose an active collection.", {"collectionId": "inactive"})
    if "title" in data:
        item.title = _text(data, "title", required=True, maximum=200)
    elif not product_id:
        raise ValidationError("title is required.", {"title": "required"})
    if not product_id and not data.get("description", "").strip():
        raise ValidationError("description is required.", {"description": "required"})
    if "slug" in data:
        item.slug = _text(data, "slug", required=True, maximum=220)
    elif not product_id:
        raise ValidationError("slug is required.", {"slug": "required"})
    item.category_id = category.id
    item.collection_id = collection.id if collection else None
    if not product_id and "currency" not in data:
        item.currency = default_currency()
    for source, target, maximum in (
        ("description", "description", 10000), ("style", "style", 60), ("occasion", "occasion", 60),
        ("bookType", "book_type", 40), ("currency", "currency", 3), ("coverAssetKey", "cover_asset_key", 1024),
    ):
        if source in data:
            value = _text(data, source, required=source == "description", maximum=maximum)
            if source == "currency" and value and (len(value) != 3 or not value.isalpha()):
                raise ValidationError("currency must be a three-letter code.", {"currency": "invalid"})
            if source == "currency" and value and product_id and value.upper() != item.currency.upper():
                variants = db.session.scalars(
                    select(BookVariant).where(BookVariant.product_id == item.id)
                ).all()
                if any(variant.currency.upper() != value.upper() for variant in variants):
                    raise ConflictError(
                        "The product currency cannot change while its variants use a different currency.",
                        {"currency": "variant_mismatch"},
                    )
            setattr(item, target, value.upper() if source == "currency" and value else value)
    for source, target in (("pageCountMin", "page_count_min"), ("pageCountMax", "page_count_max")):
        if source in data:
            setattr(item, target, _positive_int(data[source], source, optional=True))
    if item.page_count_min and item.page_count_max and item.page_count_min > item.page_count_max:
        raise ValidationError("Minimum page count cannot exceed maximum page count.", {"pageCount": "invalid_range"})
    if "startingPrice" in data:
        item.starting_price = _money(data["startingPrice"], "startingPrice")
    if "featured" in data:
        if not isinstance(data["featured"], bool):
            raise ValidationError("featured must be a boolean.", {"featured": "invalid"})
        item.is_featured = data["featured"]
    if "adminMetadata" in data:
        previous_metadata = item.admin_metadata or {}
        submitted_metadata = _body_dict(data["adminMetadata"], "adminMetadata")
        metadata = {**previous_metadata, **submitted_metadata}
        if "dimensions" in submitted_metadata and isinstance(submitted_metadata["dimensions"], dict):
            metadata["dimensions"] = {
                **previous_metadata.get("dimensions", {}),
                **submitted_metadata["dimensions"],
            }
        item.admin_metadata = _validate_product_metadata(
            metadata,
            previous_metadata,
        )
    validate_product_pricing(item, admin=True)
    if not product_id:
        item.is_active = False
    db.session.add(item)
    db.session.flush()
    _commit("book.saved", "book_product", item.id, {"published": item.is_active})
    return _product_dict(item)


def set_product_published(product_id: str, published: bool) -> dict:
    item = db.session.get(BookProduct, product_id)
    if item is None or item.deleted_at is not None:
        raise NotFound("Book product was not found.")
    if published:
        validate_product_pricing(item, admin=True)
        master_design = db.session.scalar(
            select(BookTemplate).where(
                BookTemplate.product_id == item.id,
                BookTemplate.is_active.is_(True),
                BookTemplate.deleted_at.is_(None),
                BookTemplate.published_design_document.is_not(None),
            )
        )
        if master_design is None:
            raise ValidationError("Publish the master design before publishing the product.", {"design": "required"})
        category = _category_by_id(item.category_id)
        if not item.title.strip():
            raise ValidationError("A product title is required before publishing.", {"title": "required"})
        if not item.slug.strip():
            raise ValidationError("A product slug is required before publishing.", {"slug": "required"})
        if not item.description.strip():
            raise ValidationError("A product description is required before publishing.", {"description": "required"})
        if not category.is_active:
            raise ValidationError("Activate the product category before publishing.", {"categoryId": "inactive"})
        if item.collection_id:
            collection = _collection_by_id(item.collection_id)
            if not collection.is_active or collection.category_id != category.id:
                raise ValidationError("The product collection must be active and assigned to its category.", {"collectionId": "invalid"})
        if not item.cover_asset_key or not item.cover_asset_key.startswith("catalog/"):
            raise ValidationError("Add a catalog cover image before publishing.", {"coverAssetKey": "required"})
        if not item.page_count_min or not item.page_count_max or item.page_count_min > item.page_count_max:
            raise ValidationError("Set a valid minimum and maximum page count before publishing.", {"pageCount": "invalid_range"})
        metadata = item.admin_metadata or {}
        page_count_options = metadata.get("pageCountOptions")
        if not page_count_options or any(
            not isinstance(page_count, int) or isinstance(page_count, bool)
            or page_count < item.page_count_min or page_count > item.page_count_max
            for page_count in page_count_options
        ):
            raise ValidationError("Configure page-count options within the product page range.", {"pageCountOptions": "invalid"})
        if not metadata.get("productionDays"):
            raise ValidationError("Set a production estimate before publishing.", {"productionDays": "required"})
        if not metadata.get("sizeOptions") or not metadata.get("coverOptions") or not metadata.get("paperOptions"):
            raise ValidationError("Configure size, cover, and paper options before publishing.", {"variants": "required"})
        variants = db.session.scalars(
            select(BookVariant)
            .join(BookSize, BookVariant.size_id == BookSize.id)
            .join(CoverType, BookVariant.cover_type_id == CoverType.id)
            .join(PaperType, BookVariant.paper_type_id == PaperType.id)
            .where(
                BookVariant.product_id == item.id,
                BookVariant.is_active.is_(True),
                BookSize.is_active.is_(True),
                CoverType.is_active.is_(True),
                PaperType.is_active.is_(True),
                BookVariant.size_id.in_(metadata["sizeOptions"]),
                BookVariant.cover_type_id.in_(metadata["coverOptions"]),
                BookVariant.paper_type_id.in_(metadata["paperOptions"]),
                BookVariant.currency == item.currency,
            )
        ).all()
        if not variants:
            raise ValidationError("Add at least one active, compatible product variant using the product currency.", {"variants": "required"})
        tiers = metadata.get("printingTiers", [])
        active_tiers = db.session.scalars(
            select(PricingTier).where(
                PricingTier.is_active.is_(True),
                PricingTier.code.in_(tiers),
                PricingTier.currency == item.currency,
            )
        ).all() if tiers else []
        covered_tiers = db.session.scalars(
            select(PricingTier.id)
            .join(PagePricing, PagePricing.tier_id == PricingTier.id)
            .where(
                PricingTier.id.in_([tier.id for tier in active_tiers]),
                PagePricing.minimum_pages <= item.page_count_min,
                PagePricing.maximum_pages >= item.page_count_max,
            )
            .distinct()
        ).all() if active_tiers else []
        if not covered_tiers:
            raise ValidationError("Configure active printing tiers and page pricing that cover the product page range.", {"printingTiers": "unavailable"})
        if not db.session.scalar(
            select(ShippingRate.id).where(
                ShippingRate.is_active.is_(True),
                ShippingRate.currency == item.currency,
            ).limit(1)
        ):
            raise ValidationError("Configure at least one active shipping rate in the product currency.", {"shipping": "required"})
    item.is_active = published
    _commit("book.published" if published else "book.unpublished", "book_product", item.id)
    return _product_dict(item)


def delete_product(product_id: str) -> None:
    item = db.session.get(BookProduct, product_id)
    if item is None or item.deleted_at is not None:
        raise NotFound("Book product was not found.")
    templates = db.session.scalars(
        select(BookTemplate).where(
            BookTemplate.product_id == item.id,
            BookTemplate.deleted_at.is_(None),
        )
    ).all()
    now = datetime.now(UTC)
    for template in templates:
        template.deleted_at = now
        template.is_active = False
    item.deleted_at = now
    item.is_active = False
    _commit("book.deleted", "book_product", item.id)


def _save_simple_catalog(model, data: dict, object_id: str | None, kind: str) -> dict:
    item = db.session.get(model, object_id) if object_id else model()
    if object_id and (item is None or item.deleted_at is not None):
        raise NotFound(f"{kind.title()} was not found.")
    if kind == "collection":
        if not object_id and not data.get("categoryId"):
            raise ValidationError("categoryId is required for a new collection.", {"categoryId": "required"})
        if "categoryId" in data:
            category_id = _text(data, "categoryId", required=not object_id, maximum=36)
            current_category_id = item.category_id if object_id else None
            if category_id:
                if category_id != current_category_id:
                    category = _category_by_id(category_id)
                    if not category.is_active:
                        raise ValidationError(
                            "Choose an active category for a collection.",
                            {"categoryId": "inactive"},
                        )
                    mismatched_products = 0
                    if object_id:
                        mismatched_products = db.session.scalar(
                            select(func.count(BookProduct.id)).where(
                                BookProduct.collection_id == item.id,
                                BookProduct.category_id != category_id,
                            )
                        ) or 0
                    if mismatched_products:
                        raise ConflictError(
                            "This collection category cannot change while books assigned to it use another category.",
                            {"books": mismatched_products},
                        )
                item.category_id = category_id
            elif current_category_id:
                raise ValidationError("A collection category cannot be cleared.", {"categoryId": "required"})
    name_limit = 120 if kind == "category" else 160
    slug_limit = 140 if kind == "category" else 180
    name = _text(data, "name", required=not object_id or (kind == "category" and "name" in data), maximum=name_limit)
    slug = _text(data, "slug", required=not object_id or (kind == "category" and "slug" in data), maximum=slug_limit)
    previous_slug = item.slug if kind == "category" and object_id else None
    if kind == "category" and slug is not None:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValidationError("Category slug must use lowercase letters, numbers, and single hyphens.", {"slug": "invalid"})
        duplicate_query = select(BookCategory.id).where(BookCategory.slug == slug)
        if object_id:
            duplicate_query = duplicate_query.where(BookCategory.id != item.id)
        if db.session.scalar(duplicate_query) is not None:
            raise ConflictError("A category with this slug already exists.", {"slug": "duplicate"})
    if name is not None:
        item.name = name
    if slug is not None:
        item.slug = slug
    for field, attr, max_length in (
        ("description", "description", 5000), ("style", "style", 60), ("heroAssetKey", "hero_asset_key", 1024),
        ("eyebrow", "eyebrow", 120),
    ):
        if field in data and hasattr(item, attr):
            value = _text(data, field, maximum=max_length)
            if kind == "category" and field == "heroAssetKey" and value and not (
                value.startswith("catalog/") or value.startswith(("https://", "http://"))
            ):
                raise ValidationError("Category images must use a catalog asset key or an external HTTP URL.", {"heroAssetKey": "invalid"})
            setattr(item, attr, value)
    if "sortOrder" in data and hasattr(item, "sort_order"):
        try:
            sort_order = int(data["sortOrder"])
        except (ValueError, TypeError) as failure:
            raise ValidationError("sortOrder must be an integer.", {"sortOrder": "invalid"}) from failure
        if (
            isinstance(data["sortOrder"], bool)
            or isinstance(data["sortOrder"], float) and not data["sortOrder"].is_integer()
            or sort_order < 0
        ):
            raise ValidationError("sortOrder must be a non-negative integer.", {"sortOrder": "invalid"})
        item.sort_order = sort_order
    if "recommendedLayouts" in data and hasattr(item, "recommended_layouts"):
        if not isinstance(data["recommendedLayouts"], list):
            raise ValidationError("recommendedLayouts must be a list.", {"recommendedLayouts": "invalid"})
        item.recommended_layouts = data["recommendedLayouts"]
    if "relatedCategories" in data and hasattr(item, "related_categories"):
        if not isinstance(data["relatedCategories"], list):
            raise ValidationError("relatedCategories must be a list.", {"relatedCategories": "invalid"})
        item.related_categories = data["relatedCategories"]
    if "isPublished" in data and hasattr(item, "is_active"):
        if not isinstance(data["isPublished"], bool):
            raise ValidationError("isPublished must be a boolean.", {"isPublished": "invalid"})
        if kind == "category" and not data["isPublished"]:
            published_count = db.session.scalar(
                select(func.count(BookProduct.id)).where(
                    BookProduct.category_id == item.id,
                    BookProduct.is_active.is_(True),
                    BookProduct.deleted_at.is_(None),
                )
            ) or 0
            if published_count:
                raise ConflictError(
                    f"This category cannot be deactivated because {published_count} published book"
                    f"{'s' if published_count != 1 else ''} use it.",
                    {"publishedBooks": published_count},
                )
        item.is_active = data["isPublished"]
    if kind == "category" and previous_slug and slug and previous_slug != slug:
        collections = db.session.scalars(select(BookCollection)).all()
        for collection in collections:
            related = collection.related_categories
            if isinstance(related, list) and previous_slug in related:
                collection.related_categories = [
                    slug if category_slug == previous_slug else category_slug
                    for category_slug in related
                ]
    db.session.add(item)
    db.session.flush()
    _commit(f"{kind}.saved", kind, item.id)
    return _simple_dict(item, kind)


def _simple_dict(item, kind: str) -> dict:
    if kind == "category":
        return {**serialize_category(item), "isPublished": item.is_active, "heroAssetKey": item.hero_asset_key}
    return {**serialize_collection(item), "isPublished": item.is_active, "heroAssetKey": item.hero_asset_key}


def list_simple_catalog(model, kind: str, args) -> dict:
    page, per_page = _page_params(args)
    query = select(model).where(model.deleted_at.is_(None)).order_by(model.updated_at.desc())
    search = args.get("search", "").strip()[:120]
    if search:
        query = query.where(model.name.ilike(f"%{search}%"))
    if args.get("published") in {"true", "false"}:
        query = query.where(model.is_active.is_(args.get("published") == "true"))
    result = _paginate(query, page, per_page)
    result["items"] = [_simple_dict(item, kind) for item in result["items"]]
    if kind == "category" and result["items"]:
        visible_ids = {item["id"] for item in result["items"]}
        product_rows = db.session.execute(
            select(
                BookProduct.category_id,
                func.count(BookProduct.id),
                func.sum(case((
                    BookProduct.is_active.is_(True) & BookProduct.deleted_at.is_(None),
                    1,
                ), else_=0)),
                func.sum(case((BookProduct.deleted_at.is_(None), 1), else_=0)),
            )
            .where(BookProduct.category_id.in_(visible_ids))
            .group_by(BookProduct.category_id)
        ).all()
        product_counts = {
            category_id: (int(total), int(published or 0), int(visible or 0))
            for category_id, total, published, visible in product_rows
        }
        category_keys = {
            key: item["id"]
            for item in result["items"]
            for key in (item["id"], item["slug"])
        }
        collection_counts = {category_id: 0 for category_id in visible_ids}
        collection_rows = db.session.execute(
            select(BookCollection.id, BookCollection.category_id, BookCollection.related_categories)
        ).all()
        for _, relational_category_id, related_categories in collection_rows:
            referenced_category_ids = {relational_category_id} if relational_category_id in visible_ids else set()
            if not isinstance(related_categories, list):
                related_categories = []
            for related_category in {key for key in related_categories if isinstance(key, str)}:
                category_id = category_keys.get(related_category)
                if category_id is not None:
                    referenced_category_ids.add(category_id)
            for category_id in referenced_category_ids:
                collection_counts[category_id] += 1
        for item in result["items"]:
            total, published, visible = product_counts.get(item["id"], (0, 0, 0))
            item.update({
                "bookCount": total,
                "publishedBookCount": published,
                "draftBookCount": visible - published,
                "collectionCount": collection_counts[item["id"]],
            })
    return result


def save_simple_catalog(model, kind: str, data: dict, object_id: str | None = None) -> dict:
    return _save_simple_catalog(model, data, object_id, kind)


def delete_simple_catalog(model, kind: str, object_id: str) -> None:
    item = db.session.get(model, object_id)
    if item is None or item.deleted_at is not None:
        raise NotFound(f"{kind.title()} was not found.")
    if kind == "category":
        product_count = db.session.scalar(
            select(func.count(BookProduct.id)).where(
                BookProduct.category_id == item.id,
                BookProduct.deleted_at.is_(None),
            )
        ) or 0
        collection_ids = set(db.session.scalars(
            select(BookCollection.id).where(
                BookCollection.category_id == item.id,
                BookCollection.deleted_at.is_(None),
            )
        ).all())
        for collection_id, related_categories in db.session.execute(
            select(BookCollection.id, BookCollection.related_categories).where(
                BookCollection.deleted_at.is_(None)
            )
        ).all():
            if isinstance(related_categories, list) and any(
                isinstance(category_key, str) and category_key in {item.slug, item.id}
                for category_key in related_categories
            ):
                collection_ids.add(collection_id)
        collection_count = len(collection_ids)
        if product_count or collection_count:
            raise ConflictError(
                "This category cannot be deleted while products or collections reference it.",
                {"books": product_count, "collections": collection_count},
            )
    item.deleted_at = datetime.now(UTC)
    item.is_active = False
    _commit(f"{kind}.deleted", kind, item.id)


def list_templates_admin(args) -> dict:
    page, per_page = _page_params(args)
    query = select(BookTemplate).where(BookTemplate.deleted_at.is_(None)).order_by(BookTemplate.updated_at.desc())
    if args.get("published") in {"true", "false"}:
        query = query.where(BookTemplate.is_active.is_(args.get("published") == "true"))
    search = args.get("search", "").strip()[:120]
    if search:
        query = query.where(BookTemplate.name.ilike(f"%{search}%"))
    result = _paginate(query, page, per_page)
    result["items"] = [serialize_template(item, include_pages=True) for item in result["items"]]
    return result


def save_template(data: dict, template_id: str | None = None) -> dict:
    template = db.session.get(BookTemplate, template_id) if template_id else BookTemplate()
    if template_id and (template is None or template.deleted_at is not None):
        raise NotFound("Template was not found.")
    if template_id and template.is_active:
        db.session.add(BookTemplateVersion(
            template_id=template.id,
            version=template.version,
            document=_template_document(template),
        ))
    if "name" in data or not template_id:
        template.name = _text(data, "name", required=True, maximum=160)
    if "slug" in data or not template_id:
        template.slug = _text(data, "slug", required=True, maximum=180)
    for key, attr, limit in (("description", "description", 5000), ("previewAssetKey", "preview_asset_key", 1024)):
        if key in data:
            setattr(template, attr, _text(data, key, maximum=limit))
    if "productId" in data:
        template.product_id = data["productId"] or None
        if template.product_id and db.session.get(BookProduct, template.product_id) is None:
            raise ValidationError("productId does not exist.", {"productId": "not_found"})
    if "categoryId" in data:
        template.category_id = data["categoryId"] or None
        if template.category_id:
            _category_by_id(template.category_id)
    pages = _validate_template_pages(data["pages"]) if "pages" in data else None
    if not template_id:
        template.is_active = False
        template.version = 1
    else:
        template.version += 1
    db.session.add(template)
    db.session.flush()
    if pages is not None:
        _save_template_pages(template, pages)
    _commit("template.saved", "book_template", template.id, {"version": template.version})
    return serialize_template(template, include_pages=True)


def get_template_versions(template_id: str) -> list[dict]:
    template = db.session.get(BookTemplate, template_id)
    if template is None or template.deleted_at is not None:
        raise NotFound("Template was not found.")
    versions = db.session.scalars(
        select(BookTemplateVersion).where(BookTemplateVersion.template_id == template_id)
        .order_by(BookTemplateVersion.version.desc())
    ).all()
    return [{"version": item.version, "createdAt": item.created_at.isoformat(), "document": item.document} for item in versions]


def publish_template(template_id: str, published: bool) -> dict:
    template = db.session.get(BookTemplate, template_id)
    if template is None or template.deleted_at is not None:
        raise NotFound("Template was not found.")
    if template.product_id:
        if published:
            result = publish_book_design(template.product_id)
            return result["template"]
        unpublish_book_design(template.product_id)
        return serialize_template(template, include_pages=True, include_design=True)
    if published:
        pages = _template_document(template)["pages"]
        if not template.name.strip() or not pages:
            raise ValidationError("A template must have a title and at least one page before publishing.", {"template": "incomplete"})
        if not any(page["elements"] for page in pages):
            raise ValidationError("A template must include at least one image or text placeholder.", {"template": "no_placeholders"})
    template.is_active = published
    _commit("template.published" if published else "template.unpublished", "book_template", template.id, {"version": template.version})
    return serialize_template(template, include_pages=True)


def delete_template(template_id: str) -> None:
    template = db.session.get(BookTemplate, template_id)
    if template is None or template.deleted_at is not None:
        raise NotFound("Template was not found.")
    template.deleted_at = datetime.now(UTC)
    template.is_active = False
    _commit("template.deleted", "book_template", template.id)


def _order_dict(
    order,
    kind: str,
    *,
    user: User | None = None,
    project: UserProject | None = None,
    book: BookProduct | None = None,
    payment_status: str | None = None,
) -> dict:
    user = user or db.session.get(User, order.user_id)
    project = project or db.session.get(UserProject, order.project_id)
    book = book or (db.session.get(BookProduct, project.product_id) if project and project.product_id else None)
    private_project = bool(project and is_project_private(project))
    payload = {
        "id": order.id,
        "orderNumber": order.order_number,
        "type": kind,
        "userId": order.user_id,
        "userName": (user.full_name if user else None) or "Name not provided",
        "userEmail": user.email if user else None,
        "projectId": order.project_id,
        "projectTitle": project.title if project else None,
        "bookTitle": book.title if book else None,
        "pageCount": (
            (order.price_snapshot or {}).get("pageCount", project.page_count if project else None)
            if kind == "print"
            else order.page_count if kind == "pdf"
            else project.page_count if project else None
        ),
        "privateProject": private_project,
        "revisionId": order.project_revision_id,
        "status": order.status,
        "paymentStatus": payment_status or ("successful" if order.paid_at else "pending"),
        "currency": order.currency,
        "amount": str(order.total_amount),
        "paidAt": order.paid_at.isoformat() if order.paid_at else None,
        "createdAt": order.created_at.isoformat(),
    }
    if not private_project:
        revision = db.session.get(ProjectRevision, order.project_revision_id)
        if revision is not None:
            payload["projectRevision"] = {
                "id": revision.id,
                "revisionNumber": revision.revision_number,
                "documentVersion": revision.document_version,
                "document": revision.document,
                "createdAt": revision.immutable_at.isoformat(),
            }
    if kind == "print":
        items = db.session.scalars(
            select(PrintOrderItem).where(PrintOrderItem.print_order_id == order.id)
        ).all()
        specification = items[0].specification_snapshot if items else {}
        payload["customer"] = {
            "name": (user.full_name if user else None) or "Name not provided",
            "email": user.email if user else None,
            "phone": user.phone if user else None,
        }
        payload["deliveryAddress"] = order.shipping_address_snapshot
        payload["priceSnapshot"] = order.price_snapshot or {}
        payload["configuration"] = {
            **specification,
            "quantity": items[0].quantity if items else (order.price_snapshot or {}).get("quantity"),
            "pageCount": items[0].page_count if items else (order.price_snapshot or {}).get("pageCount"),
        }
        print_pdf_order = db.session.scalar(
            select(PdfOrder).where(PdfOrder.idempotency_key == f"print-free:{order.id}")
        )
        if print_pdf_order:
            payload["printPdfOrderId"] = print_pdf_order.id
            payload["printPdf"] = {}
            for profile in ("digital", "print"):
                job = db.session.scalar(
                    select(PdfJob).where(
                        PdfJob.order_id == print_pdf_order.id,
                        PdfJob.generation_profile == profile,
                    )
                )
                payload["printPdf"][profile] = {
                    "status": job.status if job else "not_started",
                    "error": {
                        "code": job.error_code,
                        "message": job.error_message,
                    } if job and job.status == "failed" else None,
                }
        payload["photosAvailable"] = bool(
            private_project and order.paid_at is not None and order.status == "in_production"
        )
        payload["items"] = [{
            "quantity": item.quantity, "pageCount": item.page_count, "specification": item.specification_snapshot,
        } for item in items]
        shipment = db.session.scalar(select(Shipment).where(Shipment.print_order_id == order.id).order_by(Shipment.created_at.desc()))
        payload["shipment"] = ({
            "id": shipment.id, "carrier": shipment.carrier, "trackingNumber": shipment.tracking_number,
            "status": shipment.status, "estimatedDeliveryAt": shipment.estimated_delivery_at.isoformat() if shipment.estimated_delivery_at else None,
            "shippedAt": shipment.shipped_at.isoformat() if shipment.shipped_at else None,
            "deliveredAt": shipment.delivered_at.isoformat() if shipment.delivered_at else None,
        } if shipment else None)
        if shipment:
            payload["carrier"] = shipment.carrier
            payload["trackingNumber"] = shipment.tracking_number
            payload["estimatedDeliveryAt"] = shipment.estimated_delivery_at.isoformat() if shipment.estimated_delivery_at else None
    else:
        payload["pageCount"] = order.page_count
    return payload


def get_private_print_order_assets(order_id: str) -> tuple[PrintOrder, list[ProjectAsset]]:
    order = db.session.get(PrintOrder, order_id)
    if order is None:
        raise NotFound("Print order was not found.")
    if order.paid_at is None or order.status != "in_production":
        raise NotFound("Photos are available only for paid orders in production.")
    project = db.session.get(UserProject, order.project_id)
    revision = db.session.get(ProjectRevision, order.project_revision_id)
    if (
        project is None
        or project.user_id != order.user_id
        or revision is None
        or revision.project_id != project.id
        or not is_project_private(project)
    ):
        raise NotFound("Photos are not available for this order.")
    document = revision.document if isinstance(revision.document, dict) else {}
    asset_ids = {
        asset.get("id")
        for asset in document.get("assets", [])
        if isinstance(asset, dict) and isinstance(asset.get("id"), str)
    }
    assets = db.session.scalars(
        select(ProjectAsset)
        .where(
            ProjectAsset.project_id == project.id,
            ProjectAsset.id.in_(asset_ids),
            ProjectAsset.original_deleted_at.is_(None),
        )
        .order_by(ProjectAsset.created_at)
    ).all() if asset_ids else []
    return order, assets


def log_private_print_photo_access(order: PrintOrder, actor_id: str, asset_id: str | None = None) -> None:
    db.session.add(AdminActivityLog(
        actor_user_id=actor_id,
        action="private_print_order.photos_accessed",
        target_type="print_order",
        target_id=order.id,
        details={"projectId": order.project_id, "assetId": asset_id},
        ip_address=request.remote_addr,
    ))
    db.session.commit()


def get_paid_print_order_pdf(order_id: str) -> tuple[PrintOrder, GeneratedFile]:
    order = db.session.scalar(
        select(PrintOrder).where(PrintOrder.id == order_id)
    )
    if order is None:
        raise NotFound("Print order was not found.")
    if order.paid_at is None or not _order_has_successful_payment(order.id):
        raise NotFound("The print PDF is available only for paid print orders.")
    pdf_order = db.session.scalar(
        select(PdfOrder).where(PdfOrder.idempotency_key == f"print-free:{order.id}")
    )
    if pdf_order is None or pdf_order.paid_at is None:
        raise NotFound("The print PDF is not available for this order.")
    generated_file = db.session.scalar(
        select(GeneratedFile).where(
            GeneratedFile.pdf_order_id == pdf_order.id,
            GeneratedFile.generation_profile == "print",
        )
    )
    if generated_file is None:
        raise NotFound("The print PDF has not finished generating.")
    return order, generated_file


def log_private_print_pdf_access(order: PrintOrder, actor_id: str, generated_file: GeneratedFile) -> None:
    db.session.add(AdminActivityLog(
        actor_user_id=actor_id,
        action="private_print_order.pdf_accessed",
        target_type="print_order",
        target_id=order.id,
        details={
            "projectId": order.project_id,
            "generatedFileId": generated_file.id,
            "generationProfile": generated_file.generation_profile,
        },
        ip_address=request.remote_addr,
    ))
    db.session.commit()


def cleanup_delivered_project_uploads(retention_days: int) -> int:
    if retention_days < 0:
        raise ValidationError("Upload retention days must be zero or greater.", {"days": "out_of_range"})
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    delivered_orders = db.session.scalars(
        select(PrintOrder)
        .join(Shipment, Shipment.print_order_id == PrintOrder.id)
        .where(
            PrintOrder.paid_at.is_not(None),
            PrintOrder.status == "delivered",
            Shipment.status == "delivered",
            Shipment.delivered_at.is_not(None),
            Shipment.delivered_at <= cutoff,
        )
    ).all()
    storage = get_asset_storage()
    deleted_count = 0
    eligible_assets: dict[str, set[str]] = {}
    for order in delivered_orders:
        revision = db.session.get(ProjectRevision, order.project_revision_id)
        if revision is None or not isinstance(revision.document, dict):
            continue
        asset_ids = {
            item.get("id")
            for item in revision.document.get("assets", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        if asset_ids:
            eligible_assets.setdefault(order.project_id, set()).update(asset_ids)
    for project_id, asset_ids in eligible_assets.items():
        active_order = db.session.scalar(
            select(PrintOrder.id).where(
                PrintOrder.project_id == project_id,
                PrintOrder.status.not_in({"delivered", "cancelled"}),
            ).limit(1)
        )
        ungenerated_pdf = db.session.scalar(
            select(PdfOrder.id)
            .where(
                PdfOrder.project_id == project_id,
                PdfOrder.paid_at.is_not(None),
                ~select(GeneratedFile.id)
                .where(GeneratedFile.pdf_order_id == PdfOrder.id)
                .exists(),
            )
            .limit(1)
        )
        if active_order is not None or ungenerated_pdf is not None:
            continue
        assets = db.session.scalars(
            select(ProjectAsset).where(
                ProjectAsset.project_id == project_id,
                ProjectAsset.id.in_(asset_ids),
                ProjectAsset.original_deleted_at.is_(None),
            )
        ).all()
        for asset in assets:
            storage.delete(asset.storage_key)
            asset.original_deleted_at = datetime.now(UTC)
            db.session.commit()
            deleted_count += 1
    return deleted_count


def _date_filter(args, key: str, *, end_of_day: bool = False) -> datetime | None:
    value = args.get(key, "").strip()
    if not value:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValidationError(f"{key} must be a date in YYYY-MM-DD format.", {key: "invalid"})
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as failure:
        raise ValidationError(f"{key} must be a date in YYYY-MM-DD format.", {key: "invalid"}) from failure
    if end_of_day:
        parsed += timedelta(days=1)
    return parsed.replace(tzinfo=UTC)


def _apply_order_filters(query, model, payment_model, args, *, search: str):
    start = _date_filter(args, "dateFrom")
    end = _date_filter(args, "dateTo", end_of_day=True)
    if args.get("status"):
        query = query.where(model.status == args["status"][:30])
    if args.get("paymentStatus"):
        query = query.where(payment_model.status == args["paymentStatus"][:30])
    if start:
        query = query.where(model.created_at >= start)
    if end:
        query = query.where(model.created_at < end)
    user_filter = args.get("user", "").strip()[:120]
    book_filter = args.get("book", "").strip()[:120]
    if user_filter:
        term = f"%{user_filter}%"
        query = query.where(or_(
            User.id == user_filter,
            User.full_name.ilike(term),
            User.email.ilike(term),
        ))
    if book_filter:
        term = f"%{book_filter}%"
        query = query.where(or_(
            BookProduct.id == book_filter,
            BookProduct.title.ilike(term),
            UserProject.title.ilike(term),
        ))
    if search:
        term = f"%{search}%"
        query = query.where(or_(
            model.order_number.ilike(term),
            User.full_name.ilike(term),
            User.email.ilike(term),
            UserProject.title.ilike(term),
            BookProduct.title.ilike(term),
        ))
    return query


def list_orders(args) -> dict:
    page, per_page = _page_params(args)
    kind = args.get("type", "all")
    if kind not in {"all", "pdf", "print"}:
        raise ValidationError("Order type must be all, pdf, or print.", {"type": "invalid"})
    result = []
    limit = page * per_page
    total = 0
    search = args.get("search", "").strip()[:120]
    for model, order_kind in ((PdfOrder, "pdf"), (PrintOrder, "print")):
        if kind not in {"all", order_kind}:
            continue
        payment_join = Payment.pdf_order_id == model.id if order_kind == "pdf" else Payment.print_order_id == model.id
        query = (
            select(model, User, UserProject, BookProduct, Payment.status)
            .join(User, User.id == model.user_id)
            .outerjoin(UserProject, UserProject.id == model.project_id)
            .outerjoin(BookProduct, BookProduct.id == UserProject.product_id)
            .outerjoin(Payment, payment_join)
        )
        if order_kind == "print" and kind == "print":
            query = query.where(
                PrintOrder.paid_at.is_not(None),
                Payment.status == "successful",
            )
        query = _apply_order_filters(query, model, Payment, args, search=search)
        count_query = (
            select(func.count(model.id))
            .join(User, User.id == model.user_id)
            .outerjoin(UserProject, UserProject.id == model.project_id)
            .outerjoin(BookProduct, BookProduct.id == UserProject.product_id)
            .outerjoin(Payment, payment_join)
        )
        count_query = _apply_order_filters(count_query, model, Payment, args, search=search)
        if order_kind == "print" and kind == "print":
            count_query = count_query.where(
                PrintOrder.paid_at.is_not(None),
                Payment.status == "successful",
            )
        total += db.session.scalar(count_query) or 0
        rows = db.session.execute(query.order_by(model.created_at.desc()).limit(limit)).all()
        result.extend(_order_dict(
            order,
            order_kind,
            user=user,
            project=project,
            book=book,
            payment_status=payment_status,
        ) for order, user, project, book, payment_status in rows)
    result.sort(key=lambda item: item["createdAt"], reverse=True)
    return {"items": result[(page - 1) * per_page:page * per_page], "pagination": {
        "page": page, "perPage": per_page, "totalItems": total, "totalPages": (total + per_page - 1) // per_page,
    }}


def list_downloads(args) -> dict:
    page, per_page = _page_params(args)
    download_type = args.get("type", "pdf").strip().lower()
    if download_type not in {"all", "pdf"}:
        raise ValidationError("Download type must be pdf or all.", {"type": "invalid"})
    query = (
        select(DownloadHistory, DownloadEntitlement, PdfOrder, User, UserProject, BookProduct, Payment.status)
        .join(DownloadEntitlement, DownloadEntitlement.id == DownloadHistory.entitlement_id)
        .join(PdfOrder, PdfOrder.id == DownloadEntitlement.pdf_order_id)
        .join(User, User.id == DownloadEntitlement.user_id)
        .join(UserProject, UserProject.id == PdfOrder.project_id)
        .outerjoin(BookProduct, BookProduct.id == UserProject.product_id)
        .outerjoin(Payment, Payment.pdf_order_id == PdfOrder.id)
    )
    count_query = (
        select(func.count(DownloadHistory.id))
        .join(DownloadEntitlement, DownloadEntitlement.id == DownloadHistory.entitlement_id)
        .join(PdfOrder, PdfOrder.id == DownloadEntitlement.pdf_order_id)
        .join(User, User.id == DownloadEntitlement.user_id)
        .join(UserProject, UserProject.id == PdfOrder.project_id)
        .outerjoin(BookProduct, BookProduct.id == UserProject.product_id)
        .outerjoin(Payment, Payment.pdf_order_id == PdfOrder.id)
    )
    search = args.get("search", "").strip()[:120]
    user_filter = args.get("user", "").strip()[:120]
    book_filter = args.get("book", "").strip()[:120]
    if search:
        term = f"%{search}%"
        conditions = or_(
            User.full_name.ilike(term),
            User.email.ilike(term),
            UserProject.title.ilike(term),
            BookProduct.title.ilike(term),
            PdfOrder.order_number.ilike(term),
        )
        query = query.where(conditions)
        count_query = count_query.where(conditions)
    if user_filter:
        term = f"%{user_filter}%"
        condition = or_(User.id == user_filter, User.full_name.ilike(term), User.email.ilike(term))
        query = query.where(condition)
        count_query = count_query.where(condition)
    if book_filter:
        term = f"%{book_filter}%"
        condition = or_(BookProduct.id == book_filter, BookProduct.title.ilike(term), UserProject.title.ilike(term))
        query = query.where(condition)
        count_query = count_query.where(condition)
    start = _date_filter(args, "dateFrom")
    end = _date_filter(args, "dateTo", end_of_day=True)
    if start:
        query = query.where(DownloadHistory.downloaded_at >= start)
        count_query = count_query.where(DownloadHistory.downloaded_at >= start)
    if end:
        query = query.where(DownloadHistory.downloaded_at < end)
        count_query = count_query.where(DownloadHistory.downloaded_at < end)
    payment_status = args.get("paymentStatus") or args.get("status")
    if payment_status:
        query = query.where(Payment.status == payment_status[:30])
        count_query = count_query.where(Payment.status == payment_status[:30])
    total = db.session.scalar(count_query) or 0
    rows = db.session.execute(
        query.order_by(DownloadHistory.downloaded_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    items = [{
        "id": history.id,
        "userId": entitlement.user_id,
        "userName": user.full_name or "Name not provided",
        "userEmail": user.email,
        "bookTitle": book.title if book else project.title,
        "orderNumber": order.order_number,
        "type": "pdf",
        "pageCount": order.page_count,
        "currency": order.currency,
        "amount": str(order.total_amount),
        "paymentStatus": payment_status or ("successful" if order.paid_at else "pending"),
        "downloadedAt": history.downloaded_at.isoformat(),
    } for history, entitlement, order, user, project, book, payment_status in rows]
    return {"items": items, "pagination": {
        "page": page, "perPage": per_page, "totalItems": total,
        "totalPages": (total + per_page - 1) // per_page,
    }}


def get_order_history(order_id: str, kind: str) -> list[dict]:
    if kind == "pdf":
        order = db.session.get(PdfOrder, order_id)
        filter_column = OrderStatusHistory.pdf_order_id
    elif kind == "print":
        order = db.session.get(PrintOrder, order_id)
        filter_column = OrderStatusHistory.print_order_id
    else:
        raise ValidationError("Order type must be pdf or print.", {"type": "invalid"})
    if order is None:
        raise NotFound("Order was not found.")
    rows = db.session.scalars(
        select(OrderStatusHistory)
        .where(filter_column == order_id)
        .order_by(OrderStatusHistory.created_at.asc(), OrderStatusHistory.id.asc())
    ).all()
    return [{
        "id": row.id,
        "status": row.status,
        "note": row.note,
        "changedByUserId": row.changed_by_user_id,
        "createdAt": row.created_at.isoformat(),
    } for row in rows]


def list_user_orders(user_id: str, args) -> dict:
    user = db.session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFound("User was not found.")
    filters = args.copy()
    filters["user"] = user_id
    return list_orders(filters)


def list_book_orders(book_id: str, args) -> dict:
    book = db.session.get(BookProduct, book_id)
    if book is None or book.deleted_at is not None:
        raise NotFound("Book product was not found.")
    filters = args.copy()
    filters["book"] = book_id
    return list_orders(filters)


def update_order(order_id: str, kind: str, data: dict, actor_id: str) -> dict:
    if kind not in {"pdf", "print"}:
        raise ValidationError("Order type must be pdf or print.", {"type": "invalid"})
    model = PdfOrder if kind == "pdf" else PrintOrder
    order = db.session.get(model, order_id)
    if order is None:
        raise NotFound("Order was not found.")
    shipment = None
    existing_shipment = None
    if "status" in data:
        state = _text(data, "status", required=True, maximum=40)
        allowed = {"cancellation_requested", "cancelled"} if kind == "pdf" else ADMIN_PRINT_STATES
        if state not in allowed:
            raise ValidationError("The requested order status is not allowed.", {"status": "invalid"})
        if state != order.status:
            if kind == "print" and state == "refunded":
                raise ConflictError("Refunded status is set only after a refund is confirmed.")
            if kind == "print" and state not in PRINT_STATUS_TRANSITIONS.get(order.status, set()):
                raise ConflictError(f"Print orders cannot move from {order.status} to {state}.")
            if kind == "print" and state in {
                "payment_confirmed", "processing", "printed", "design_verified",
                "in_production", "quality_check", "packed", "shipped",
                "out_for_delivery", "delivered",
            } and (order.paid_at is None or not _order_has_successful_payment(order.id)):
                raise ConflictError("Production can begin only after payment is confirmed.")
            if state == "cancelled" and order.paid_at is not None:
                raise ConflictError("Paid orders must be refunded through the payment provider before cancellation.")
            if kind == "print" and state == "shipped":
                existing_shipment = db.session.scalar(
                    select(Shipment).where(Shipment.print_order_id == order.id).order_by(Shipment.created_at.desc())
                )
                tracking_number = data.get("trackingNumber") or (
                    existing_shipment.tracking_number if existing_shipment else None
                )
                if not isinstance(tracking_number, str) or not tracking_number.strip():
                    raise ValidationError("A tracking number is required before shipping.", {"trackingNumber": "required"})
            old_status = order.status
            order.status = state
            db.session.add(OrderStatusHistory(
                pdf_order_id=order.id if kind == "pdf" else None,
                print_order_id=order.id if kind == "print" else None,
                status=state,
                note=f"Admin status update from {old_status}",
                changed_by_user_id=actor_id,
            ))
            status_messages = {
                "processing": (
                    "Your book is being prepared",
                    "Your book is being prepared.",
                ),
                "printed": (
                    "Your book has been printed",
                    "Your book has been printed.",
                ),
                "shipped": (
                    "Your book has been shipped",
                    f"Your book has been shipped (tracking: "
                    f"{(data.get('trackingNumber') or (existing_shipment.tracking_number if existing_shipment else 'not provided')).strip()}).",
                ),
                "out_for_delivery": (
                    "Your book is out for delivery",
                    "Your book is out for delivery.",
                ),
                "delivered": (
                    "Your book has been delivered",
                    "Your book has been delivered.",
                ),
            }
            title, message = status_messages.get(
                state,
                ("Order status updated", f"Order {order.order_number} is now {state.replace('_', ' ')}."),
            )
            queue_order_event(
                order.user_id,
                f"order_status:{kind}:{order.id}:{state}",
                "order",
                title,
                message,
                "/dashboard/orders",
            )
        if kind == "print" and state in {"shipped", "out_for_delivery", "delivered"}:
            shipment = db.session.scalar(
                select(Shipment).where(Shipment.print_order_id == order.id).order_by(Shipment.created_at.desc())
            )
            if shipment is None:
                shipment = Shipment(print_order_id=order.id)
                db.session.add(shipment)
            shipment.status = state
            if state in {"shipped", "out_for_delivery", "delivered"} and shipment.shipped_at is None:
                shipment.shipped_at = datetime.now(UTC)
            if state == "delivered":
                shipment.delivered_at = datetime.now(UTC)
    if kind == "print" and any(key in data for key in ("carrier", "trackingNumber", "estimatedDeliveryAt")):
        if shipment is None:
            shipment = db.session.scalar(
                select(Shipment).where(Shipment.print_order_id == order.id).order_by(Shipment.created_at.desc())
            )
        if shipment is None:
            shipment = Shipment(print_order_id=order.id)
            db.session.add(shipment)
        if "carrier" in data:
            shipment.carrier = _text(data, "carrier", maximum=100)
        if "trackingNumber" in data:
            shipment.tracking_number = _text(data, "trackingNumber", maximum=160)
        if "estimatedDeliveryAt" in data:
            raw_date = data["estimatedDeliveryAt"]
            if raw_date is not None:
                try:
                    shipment.estimated_delivery_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                except (AttributeError, ValueError) as failure:
                    raise ValidationError("estimatedDeliveryAt must be an ISO date/time.", {"estimatedDeliveryAt": "invalid"}) from failure
    _commit("order.updated", f"{kind}_order", order.id, {"fields": sorted(data)})
    return _order_dict(order, kind)


def _order_has_successful_payment(order_id: str) -> bool:
    return db.session.scalar(
        select(Payment.id).where(
            Payment.print_order_id == order_id,
            Payment.status == "successful",
        ).limit(1)
    ) is not None


def list_payments(args, *, refunds: bool = False) -> dict:
    page, per_page = _page_params(args)
    model = Refund if refunds else Payment
    query = select(model).order_by(model.created_at.desc())
    search = args.get("search", "").strip()[:100]
    status = args.get("status", "").strip()[:30]
    currency = args.get("currency", "").strip().upper()[:3]
    if status:
        query = query.where(model.status == status)
    if currency:
        query = query.where(model.currency == currency)
    if search and refunds:
        query = query.where(or_(
            Refund.provider_refund_id.ilike(f"%{search}%"),
            Refund.reason.ilike(f"%{search}%"),
            Refund.status.ilike(f"%{search}%"),
        ))
    elif search:
        query = query.where(or_(
            Payment.provider_payment_id.ilike(f"%{search}%"),
            Payment.status.ilike(f"%{search}%"),
            Payment.provider.ilike(f"%{search}%"),
        ))
    if not refunds:
        provider = args.get("provider", "").strip()[:60]
        if provider:
            query = query.where(Payment.provider == provider)
    result = _paginate(query, page, per_page)
    if refunds:
        result["items"] = [{
            "id": item.id, "paymentId": item.payment_id, "status": item.status,
            "providerRefundId": item.provider_refund_id,
            "amount": str(item.amount), "currency": item.currency, "reason": item.reason,
            "createdAt": item.created_at.isoformat(),
        } for item in result["items"]]
    else:
        result["items"] = [_admin_payment_dict(item) for item in result["items"]]
    return result


def _admin_payment_dict(payment: Payment) -> dict:
    attempt = db.session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.payment_id == payment.id)
        .order_by(PaymentAttempt.attempt_number.desc())
    )
    return {
        "id": payment.id, "userId": payment.user_id, "provider": payment.provider,
        "purpose": payment.purpose, "paymentMethod": payment.payment_method,
        "providerPaymentId": payment.provider_payment_id,
        "submittedReference": attempt.provider_reference if attempt and attempt.status == "submitted" else None,
        "attemptStatus": attempt.status if attempt else None,
        "status": payment.status, "amount": str(payment.amount), "currency": payment.currency,
        "orderId": payment.pdf_order_id or payment.print_order_id, "createdAt": payment.created_at.isoformat(),
    }


def record_manual_payment_action(payment_id: str, details: dict) -> None:
    _commit("payment.manual_reviewed", "payment", payment_id, details)
def record_manual_refund_action(refund_id: str, details: dict) -> None:
    _commit("refund.manual_processed", "refund", refund_id, details)


def list_pricing() -> dict:
    tiers = db.session.scalars(select(PricingTier).order_by(PricingTier.name)).all()
    page_pricing = db.session.scalars(select(PagePricing).order_by(PagePricing.tier_id, PagePricing.minimum_pages)).all()
    rules = db.session.scalars(select(PricingRule).order_by(PricingRule.name)).all()
    shipping = db.session.scalars(select(ShippingRate).order_by(ShippingRate.country_code, ShippingRate.service_code)).all()
    sizes = db.session.scalars(select(BookSize).order_by(BookSize.name)).all()
    covers = db.session.scalars(select(CoverType).order_by(CoverType.name)).all()
    papers = db.session.scalars(select(PaperType).order_by(PaperType.name)).all()
    discounts = db.session.scalars(select(DiscountCode).order_by(DiscountCode.code)).all()
    variants = db.session.execute(
        select(BookVariant, BookProduct.title, BookSize.name, CoverType.name, PaperType.name)
        .join(BookProduct, BookProduct.id == BookVariant.product_id)
        .join(BookSize, BookSize.id == BookVariant.size_id)
        .join(CoverType, CoverType.id == BookVariant.cover_type_id)
        .join(PaperType, PaperType.id == BookVariant.paper_type_id)
        .order_by(BookProduct.title, BookSize.name, CoverType.name, PaperType.name)
    ).all()
    return {
        "currency": default_currency(),
        "tiers": [{"id": x.id, "code": x.code, "name": x.name, "description": x.description, "basePrice": str(x.base_price), "currency": x.currency, "active": x.is_active} for x in tiers],
        "pagePricing": [{
            "id": x.id,
            "tierId": x.tier_id,
            "tierCode": db.session.get(PricingTier, x.tier_id).code,
            "minimumPages": x.minimum_pages,
            "maximumPages": x.maximum_pages,
            "pricePerPage": str(x.price_per_page),
        } for x in page_pricing],
        "rules": [{"id": x.id, "code": x.code, "name": x.name, "type": x.adjustment_type, "amount": str(x.amount), "active": x.is_active} for x in rules],
        "shipping": [{
            "id": x.id,
            "countryCode": x.country_code,
            "regionCode": x.region_code,
            "serviceCode": x.service_code,
            "serviceName": x.service_name,
            "price": str(x.price),
            "currency": x.currency,
            "estimatedDaysMin": x.estimated_days_min,
            "estimatedDaysMax": x.estimated_days_max,
            "active": x.is_active,
        } for x in shipping],
        "sizes": [{"id": x.id, "code": x.code, "name": x.name, "widthMm": str(x.width_mm), "heightMm": str(x.height_mm), "active": x.is_active} for x in sizes],
        "covers": [{"id": x.id, "name": x.name, "description": x.description, "active": x.is_active} for x in covers],
        "papers": [{"id": x.id, "name": x.name, "description": x.description, "weightGsm": x.weight_gsm, "active": x.is_active} for x in papers],
        "discounts": [{"id": x.id, "code": x.code, "type": x.discount_type, "value": str(x.value), "currency": x.currency, "active": x.is_active, "maximumUses": x.maximum_uses, "usesCount": x.uses_count} for x in discounts],
        "variants": [{
            "id": row[0].id,
            "productId": row[0].product_id,
            "sku": row[0].sku,
            "sizeId": row[0].size_id,
            "coverTypeId": row[0].cover_type_id,
            "paperTypeId": row[0].paper_type_id,
            "book": row[1],
            "size": row[2],
            "cover": row[3],
            "paper": row[4],
            "basePrice": str(row[0].base_price),
            "currency": row[0].currency,
            "active": row[0].is_active,
            "kind": "variant",
        } for row in variants],
    }


def _pricing_currency(value, field: str = "currency") -> str:
    currency = _text({"value": value}, "value", required=True, maximum=3).upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValidationError(f"{field} must be a three-letter currency code.", {field: "invalid"})
    if currency != default_currency():
        raise ValidationError(
            f"{field} must use the configured {default_currency()} currency.",
            {field: "mismatch"},
        )
    return currency


def _validate_page_pricing_range(tier_id: str, minimum: int, maximum: int, *, item_id: str | None = None) -> None:
    query = select(PagePricing.id).where(
        PagePricing.tier_id == tier_id,
        PagePricing.minimum_pages <= maximum,
        PagePricing.maximum_pages >= minimum,
    )
    if item_id:
        query = query.where(PagePricing.id != item_id)
    if db.session.scalar(query) is not None:
        raise ConflictError(
            "Page pricing ranges for the same tier cannot overlap.",
            {"tierId": "overlapping_range"},
        )


def create_pricing(kind: str, data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("Pricing data must be an object.")
    active = data.get("active", True)
    if not isinstance(active, bool):
        raise ValidationError("active must be a boolean.", {"active": "invalid"})
    if kind == "tier":
        code = _text(data, "code", required=True, maximum=40).upper()
        if not re.fullmatch(r"[A-Z0-9_-]+", code):
            raise ValidationError("Tier code may contain uppercase letters, numbers, underscores, and hyphens.", {"code": "invalid"})
        if db.session.scalar(select(PricingTier.id).where(PricingTier.code == code)):
            raise ConflictError("A pricing tier with this code already exists.", {"code": "duplicate"})
        item = PricingTier(
            code=code,
            name=_text(data, "name", required=True, maximum=100),
            description=_text(data, "description", maximum=5000),
            base_price=_money(data.get("basePrice"), "basePrice"),
            currency=_pricing_currency(data.get("currency", default_currency())),
            is_active=active,
        )
    elif kind == "pagePricing":
        tier_id = _text(data, "tierId", required=True, maximum=36)
        tier = db.session.get(PricingTier, tier_id)
        if tier is None or not tier.is_active:
            raise ValidationError("Choose an active pricing tier.", {"tierId": "not_found"})
        minimum = _positive_int(data.get("minimumPages"), "minimumPages")
        maximum = _positive_int(data.get("maximumPages"), "maximumPages")
        if maximum < minimum:
            raise ValidationError("Maximum pages must be greater than or equal to minimum pages.", {"pages": "invalid_range"})
        _validate_page_pricing_range(tier.id, minimum, maximum)
        item = PagePricing(
            tier_id=tier.id,
            minimum_pages=minimum,
            maximum_pages=maximum,
            price_per_page=_money(data.get("pricePerPage"), "pricePerPage"),
        )
    elif kind == "shipping":
        country = _text(data, "countryCode", required=True, maximum=2).upper()
        if not re.fullmatch(r"[A-Z]{2}", country):
            raise ValidationError("Country code must contain two letters.", {"countryCode": "invalid"})
        region = _text(data, "regionCode", maximum=20)
        service_code = _text(data, "serviceCode", required=True, maximum=40)
        if db.session.scalar(select(ShippingRate.id).where(
            ShippingRate.country_code == country,
            ShippingRate.region_code == region if region is not None else ShippingRate.region_code.is_(None),
            ShippingRate.service_code == service_code,
        )):
            raise ConflictError("A shipping service already exists for this destination.", {"serviceCode": "duplicate"})
        minimum_days = _positive_int(data.get("estimatedDaysMin"), "estimatedDaysMin", optional=True)
        maximum_days = _positive_int(data.get("estimatedDaysMax"), "estimatedDaysMax", optional=True)
        if minimum_days and maximum_days and maximum_days < minimum_days:
            raise ValidationError("Maximum delivery days must be at least the minimum.", {"estimatedDaysMax": "invalid_range"})
        item = ShippingRate(
            country_code=country,
            region_code=region,
            service_code=service_code,
            service_name=_text(data, "serviceName", required=True, maximum=100),
            price=_money(data.get("price"), "price"),
            currency=_pricing_currency(data.get("currency", default_currency())),
            estimated_days_min=minimum_days,
            estimated_days_max=maximum_days,
            is_active=active,
        )
    elif kind == "size":
        code = _text(data, "code", required=True, maximum=40)
        if db.session.scalar(select(BookSize.id).where(BookSize.code == code)):
            raise ConflictError("A book size with this code already exists.", {"code": "duplicate"})
        width = _money(data.get("widthMm"), "widthMm")
        height = _money(data.get("heightMm"), "heightMm")
        if width <= 0 or height <= 0:
            raise ValidationError("Book dimensions must be greater than zero.", {"dimensions": "invalid"})
        item = BookSize(
            code=code,
            name=_text(data, "name", required=True, maximum=100),
            width_mm=width,
            height_mm=height,
            is_active=active,
        )
    elif kind == "cover":
        name = _text(data, "name", required=True, maximum=100)
        if db.session.scalar(select(CoverType.id).where(CoverType.name == name)):
            raise ConflictError("A cover type with this name already exists.", {"name": "duplicate"})
        item = CoverType(
            name=name,
            description=_text(data, "description", maximum=500),
            is_active=active,
        )
    elif kind == "paper":
        name = _text(data, "name", required=True, maximum=100)
        if db.session.scalar(select(PaperType.id).where(PaperType.name == name)):
            raise ConflictError("A paper type with this name already exists.", {"name": "duplicate"})
        item = PaperType(
            name=name,
            description=_text(data, "description", maximum=500),
            weight_gsm=_positive_int(data.get("weightGsm"), "weightGsm", optional=True),
            is_active=active,
        )
    else:
        raise ValidationError("Pricing resource type is not supported.", {"type": "invalid"})

    db.session.add(item)
    db.session.flush()
    _commit("pricing.created", kind, item.id)
    return {"id": item.id, "kind": kind, "active": getattr(item, "is_active", True)}


def update_pricing(kind: str, item_id: str, data: dict) -> dict:
    models = {
        "tier": PricingTier,
        "shipping": ShippingRate,
        "size": BookSize,
        "cover": CoverType,
        "paper": PaperType,
        "pagePricing": PagePricing,
        "rule": PricingRule,
        "discount": DiscountCode,
        "variant": BookVariant,
    }
    model = models.get(kind)
    if model is None:
        raise ValidationError("Pricing resource type is not supported.", {"type": "invalid"})
    item = db.session.get(model, item_id)
    if item is None:
        raise NotFound("Pricing record was not found.")
    if kind == "tier":
        if "code" in data:
            code = _text(data, "code", required=True, maximum=40).upper()
            if not re.fullmatch(r"[A-Z0-9_-]+", code):
                raise ValidationError("Tier code may contain uppercase letters, numbers, underscores, and hyphens.", {"code": "invalid"})
            if db.session.scalar(select(PricingTier.id).where(PricingTier.code == code, PricingTier.id != item.id)):
                raise ConflictError("A pricing tier with this code already exists.", {"code": "duplicate"})
            item.code = code
        if "basePrice" in data:
            item.base_price = _money(data["basePrice"], "basePrice")
        if "name" in data:
            item.name = _text(data, "name", required=True, maximum=100)
        if "description" in data:
            item.description = _text(data, "description", maximum=5000)
        if "currency" in data:
            item.currency = _pricing_currency(data["currency"])
    elif kind == "shipping":
        if "price" in data:
            item.price = _money(data["price"], "price")
        if "serviceName" in data:
            item.service_name = _text(data, "serviceName", required=True, maximum=100)
        if "countryCode" in data:
            country = _text(data, "countryCode", required=True, maximum=2).upper()
            if not re.fullmatch(r"[A-Z]{2}", country):
                raise ValidationError("Country code must contain two letters.", {"countryCode": "invalid"})
            item.country_code = country
        if "regionCode" in data:
            item.region_code = _text(data, "regionCode", maximum=20)
        if "serviceCode" in data:
            item.service_code = _text(data, "serviceCode", required=True, maximum=40)
        if "currency" in data:
            item.currency = _pricing_currency(data["currency"])
        if "estimatedDaysMin" in data:
            item.estimated_days_min = _positive_int(data["estimatedDaysMin"], "estimatedDaysMin", optional=True)
        if "estimatedDaysMax" in data:
            item.estimated_days_max = _positive_int(data["estimatedDaysMax"], "estimatedDaysMax", optional=True)
        if item.estimated_days_min and item.estimated_days_max and item.estimated_days_max < item.estimated_days_min:
            raise ValidationError("Maximum delivery days must be at least the minimum.", {"estimatedDaysMax": "invalid_range"})
        region_condition = (
            ShippingRate.region_code == item.region_code
            if item.region_code is not None
            else ShippingRate.region_code.is_(None)
        )
        duplicate_query = select(ShippingRate.id).where(
            ShippingRate.country_code == item.country_code,
            region_condition,
            ShippingRate.service_code == item.service_code,
            ShippingRate.id != item.id,
        )
        if db.session.scalar(duplicate_query) is not None:
            raise ConflictError(
                "A shipping service already exists for this destination.",
                {"serviceCode": "duplicate"},
            )
    elif kind == "size":
        if "code" in data:
            code = _text(data, "code", required=True, maximum=40)
            if db.session.scalar(select(BookSize.id).where(BookSize.code == code, BookSize.id != item.id)):
                raise ConflictError("A book size with this code already exists.", {"code": "duplicate"})
            item.code = code
        if "name" in data:
            item.name = _text(data, "name", required=True, maximum=100)
        for field, attr in (("widthMm", "width_mm"), ("heightMm", "height_mm")):
            if field in data:
                value = _money(data[field], field)
                if value == 0:
                    raise ValidationError(f"{field} must be greater than zero.", {field: "invalid"})
                setattr(item, attr, value)
    elif kind == "pagePricing":
        if "tierId" in data:
            tier_id = _text(data, "tierId", required=True, maximum=36)
            tier = db.session.get(PricingTier, tier_id)
            if tier is None or not tier.is_active:
                raise ValidationError("Choose an active pricing tier.", {"tierId": "not_found"})
            item.tier_id = tier.id
        for field, attr in (("minimumPages", "minimum_pages"), ("maximumPages", "maximum_pages")):
            if field in data:
                setattr(item, attr, _positive_int(data[field], field))
        if "pricePerPage" in data:
            item.price_per_page = _money(data["pricePerPage"], "pricePerPage")
        if item.maximum_pages < item.minimum_pages:
            raise ValidationError("Maximum pages must be greater than or equal to minimum pages.", {"pages": "invalid_range"})
        _validate_page_pricing_range(
            item.tier_id,
            item.minimum_pages,
            item.maximum_pages,
            item_id=item.id,
        )
    elif kind == "rule":
        if "name" in data:
            item.name = _text(data, "name", required=True, maximum=160)
        if "amount" in data:
            item.amount = _money(data["amount"], "amount")
        if "adjustmentType" in data:
            adjustment_type = _text(data, "adjustmentType", required=True, maximum=20)
            if adjustment_type not in {"fixed", "percent"}:
                raise ValidationError("Adjustment type must be fixed or percent.", {"adjustmentType": "invalid"})
            item.adjustment_type = adjustment_type
    elif kind == "discount":
        if "value" in data:
            value = _money(data["value"], "value")
            if value == 0 or (item.discount_type == "percent" and value > 100):
                raise ValidationError("Discount value is outside its allowed range.", {"value": "invalid"})
            item.value = value
        if "type" in data:
            discount_type = _text(data, "type", required=True, maximum=20)
            if discount_type not in {"fixed", "percent"}:
                raise ValidationError("Discount type must be fixed or percent.", {"type": "invalid"})
            item.discount_type = discount_type
        if "maximumUses" in data:
            item.maximum_uses = _positive_int(data["maximumUses"], "maximumUses", optional=True)
        if "currency" in data:
            item.currency = _pricing_currency(data["currency"])
    elif kind == "variant":
        if "basePrice" in data:
            item.base_price = _money(data["basePrice"], "basePrice")
        if "currency" in data:
            currency = _pricing_currency(data["currency"])
            product = db.session.get(BookProduct, item.product_id)
            if product is None or currency != product.currency.upper():
                raise ValidationError("Variant currency must match its book product.", {"currency": "mismatch"})
            item.currency = currency
    elif kind == "cover":
        if "name" in data:
            name = _text(data, "name", required=True, maximum=100)
            if db.session.scalar(select(CoverType.id).where(CoverType.name == name, CoverType.id != item.id)):
                raise ConflictError("A cover type with this name already exists.", {"name": "duplicate"})
            item.name = name
    elif kind == "paper":
        if "name" in data:
            name = _text(data, "name", required=True, maximum=100)
            if db.session.scalar(select(PaperType.id).where(PaperType.name == name, PaperType.id != item.id)):
                raise ConflictError("A paper type with this name already exists.", {"name": "duplicate"})
            item.name = name
        if "weightGsm" in data:
            item.weight_gsm = _positive_int(data["weightGsm"], "weightGsm", optional=True)
    if kind in {"cover", "paper"} and "description" in data:
        item.description = _text(data, "description", maximum=500)
    elif "description" in data and hasattr(item, "description"):
        item.description = _text(data, "description", maximum=500)
    if "active" in data:
        if not isinstance(data["active"], bool):
            raise ValidationError("active must be a boolean.", {"active": "invalid"})
        item.is_active = data["active"]
    _commit("pricing.updated", kind, item.id, {"fields": sorted(data)})
    return {"id": item.id, "active": item.is_active}


def delete_pricing(kind: str, item_id: str) -> None:
    if kind != "pagePricing":
        raise ValidationError("Only page-pricing bands can be deleted; deactivate other pricing records instead.", {"type": "unsupported"})
    item = db.session.get(PagePricing, item_id)
    if item is None:
        raise NotFound("Pricing record was not found.")
    db.session.delete(item)
    _commit("pricing.deleted", kind, item.id)


def create_variant(data: dict) -> dict:
    product_id = _text(data, "productId", required=True, maximum=36)
    size_id = _text(data, "sizeId", required=True, maximum=36)
    cover_id = _text(data, "coverTypeId", required=True, maximum=36)
    paper_id = _text(data, "paperTypeId", required=True, maximum=36)
    sku = _text(data, "sku", required=True, maximum=80)
    product = db.session.get(BookProduct, product_id)
    size = db.session.get(BookSize, size_id)
    cover = db.session.get(CoverType, cover_id)
    paper = db.session.get(PaperType, paper_id)
    if (
        product is None or product.deleted_at is not None
        or size is None or not size.is_active
        or cover is None or not cover.is_active
        or paper is None or not paper.is_active
    ):
        raise ValidationError("Product, size, cover, and paper options must exist.", {"variant": "invalid_reference"})
    metadata = product.admin_metadata or {}
    for field, identifier in (
        ("sizeOptions", size.id),
        ("coverOptions", cover.id),
        ("paperOptions", paper.id),
    ):
        configured = metadata.get(field)
        if isinstance(configured, list) and configured and identifier not in configured:
            raise ValidationError(
                "The selected option is not enabled for this book product.",
                {field: "incompatible"},
            )
    currency = _pricing_currency(data.get("currency", product.currency))
    if currency != product.currency.upper():
        raise ValidationError("Variant currency must match its book product.", {"currency": "mismatch"})
    sku = _text(data, "sku", required=True, maximum=80)
    if db.session.scalar(select(BookVariant.id).where(BookVariant.sku == sku)):
        raise ConflictError("A variant with this SKU already exists.", {"sku": "duplicate"})
    duplicate = db.session.scalar(select(BookVariant.id).where(
        BookVariant.product_id == product.id,
        BookVariant.size_id == size.id,
        BookVariant.cover_type_id == cover.id,
        BookVariant.paper_type_id == paper.id,
    ))
    if duplicate:
        raise ConflictError("This product, size, cover, and paper combination already exists.", {"variant": "duplicate"})
    variant = BookVariant(
        product_id=product.id,
        size_id=size.id,
        cover_type_id=cover.id,
        paper_type_id=paper.id,
        sku=sku,
        base_price=_money(data.get("basePrice"), "basePrice"),
        currency=currency,
    )
    db.session.add(variant)
    db.session.flush()
    _commit("pricing.variant_created", "book_variant", variant.id)
    return {
        "id": variant.id,
        "productId": product.id,
        "basePrice": str(variant.base_price),
        "currency": variant.currency,
        "active": variant.is_active,
    }


def list_support(args) -> dict:
    page, per_page = _page_params(args)
    query = select(SupportTicket).order_by(SupportTicket.updated_at.desc())
    if args.get("status"):
        query = query.where(SupportTicket.status == args["status"][:30])
    result = _paginate(query, page, per_page)
    rows = []
    for ticket in result["items"]:
        user = db.session.get(User, ticket.user_id) if ticket.user_id else None
        messages = db.session.scalars(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id).order_by(SupportMessage.created_at)).all()
        rows.append({
            "id": ticket.id, "ticketNumber": ticket.ticket_number, "subject": ticket.subject,
            "category": ticket.category, "priority": ticket.priority, "status": ticket.status,
            "userEmail": user.email if user else None,
            "messages": [{"id": msg.id, "body": msg.body, "internal": msg.is_internal, "createdAt": msg.created_at.isoformat()} for msg in messages],
        })
    result["items"] = rows
    return result


def update_support(ticket_id: str, data: dict, actor_id: str) -> dict:
    ticket = db.session.get(SupportTicket, ticket_id)
    if ticket is None:
        raise NotFound("Support ticket was not found.")
    if "status" in data:
        status = _text(data, "status", required=True, maximum=30)
        if status not in {"open", "in_progress", "waiting_for_customer", "resolved", "closed"}:
            raise ValidationError("Support ticket status is invalid.", {"status": "invalid"})
        ticket.status = status
        ticket.closed_at = datetime.now(UTC) if status in {"resolved", "closed"} else None
    if "priority" in data:
        priority = _text(data, "priority", required=True, maximum=20)
        if priority not in {"low", "normal", "high", "urgent"}:
            raise ValidationError("Support priority is invalid.", {"priority": "invalid"})
        ticket.priority = priority
    if "reply" in data:
        reply = _text(data, "reply", required=True, maximum=10000)
        db.session.add(SupportMessage(ticket_id=ticket.id, sender_user_id=actor_id, body=reply, is_internal=False))
    if "internalNote" in data:
        note = _text(data, "internalNote", required=True, maximum=10000)
        db.session.add(SupportMessage(ticket_id=ticket.id, sender_user_id=actor_id, body=note, is_internal=True))
    _commit("support_ticket.updated", "support_ticket", ticket.id, {"fields": sorted(data)})
    return {"id": ticket.id, "status": ticket.status, "priority": ticket.priority}


def list_settings() -> list[dict]:
    items = db.session.scalars(select(PlatformSetting).order_by(PlatformSetting.setting_key)).all()
    return [{"id": item.id, "key": item.setting_key, "value": item.setting_value, "public": item.is_public} for item in items]


def save_setting(data: dict, setting_id: str | None = None) -> dict:
    if setting_id:
        item = db.session.get(PlatformSetting, setting_id)
        if item is None:
            raise NotFound("Setting was not found.")
    else:
        key = _text(data, "key", required=True, maximum=120)
        item = db.session.scalar(select(PlatformSetting).where(PlatformSetting.setting_key == key))
        item = item or PlatformSetting(setting_key=key, setting_value={})
    item.setting_value = _body_dict(data.get("value"), "value")
    if item.setting_key == "paypal_pkr_to_usd_rate":
        try:
            rate = Decimal(str(item.setting_value.get("rate")))
        except (InvalidOperation, ValueError, TypeError) as failure:
            raise ValidationError(
                "PayPal conversion rate must contain a positive USD-per-PKR rate.",
                {"value.rate": "invalid"},
            ) from failure
        if not rate.is_finite() or rate <= 0 or rate > 1 or rate.as_tuple().exponent < -8:
            raise ValidationError(
                "PayPal conversion rate must be greater than zero, at most 1, and have no more than 8 decimals.",
                {"value.rate": "invalid"},
            )
        item.setting_value = {"rate": format(rate, "f")}
    if "public" in data:
        if not isinstance(data["public"], bool):
            raise ValidationError("public must be a boolean.", {"public": "invalid"})
        item.is_public = data["public"]
    from memorybook.permissions import get_authenticated_user
    item.updated_by_user_id = get_authenticated_user().id
    db.session.add(item)
    db.session.flush()
    _commit("setting.saved", "platform_setting", item.id, {"key": item.setting_key})
    return {"id": item.id, "key": item.setting_key, "value": item.setting_value, "public": item.is_public}


def list_activity(args) -> dict:
    page, per_page = _page_params(args)
    query = select(AdminActivityLog).order_by(AdminActivityLog.created_at.desc())
    result = _paginate(query, page, per_page)
    result["items"] = [{
        "id": row.id, "actorId": row.actor_user_id, "action": row.action, "targetType": row.target_type,
        "targetId": row.target_id, "details": row.details, "ipAddress": row.ip_address,
        "createdAt": row.created_at.isoformat(),
    } for row in result["items"]]
    return result


def list_notifications(args, *, admin_user_id: str) -> dict:
    from memorybook.models import Notification

    page, per_page = _page_params(args)
    query = select(Notification).where(Notification.user_id == admin_user_id).order_by(Notification.created_at.desc())
    result = _paginate(query, page, per_page)
    result["items"] = [{
        "id": row.id, "category": row.category, "title": row.title, "message": row.message,
        "targetUrl": row.target_url, "data": row.data, "read": row.read_at is not None,
        "createdAt": row.created_at.isoformat(),
    } for row in result["items"]]
    return result


def notify_admins(event: str, title: str, message: str, data: dict | None = None) -> None:
    """Persist an operational event notification for every active admin."""
    from memorybook.models import Notification, Role, UserRole

    admin_ids = db.session.scalars(
        select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.name == "admin")
    ).all()
    for user_id in admin_ids:
        db.session.add(Notification(
            user_id=user_id,
            category=event,
            title=title,
            message=message,
            data=data or {},
        ))


def send_transactional_email(data: dict) -> dict:
    recipient = _text(data, "recipient", required=True, maximum=320)
    subject = _text(data, "subject", required=True, maximum=200)
    body = _text(data, "body", required=True, maximum=20000)
    user = db.session.scalar(select(User).where(User.email == recipient))
    log = EmailLog(
        user_id=user.id if user else None,
        recipient_email=recipient,
        template_key="admin_transactional",
        status="sending",
    )
    db.session.add(log)
    db.session.flush()
    try:
        send_email(recipient, subject, body)
    except ServiceUnavailableError as failure:
        log.status = "failed"
        log.error_message = str(failure)[:1000]
        db.session.commit()
        raise
    log.status = "sent"
    log.sent_at = datetime.now(UTC)
    _commit("transactional_email.sent", "email_log", log.id, {"recipient": recipient})
    return {"id": log.id, "status": log.status}


def reports_summary() -> dict:
    metrics = dashboard_metrics()
    metrics["userGrowth"] = db.session.execute(
        select(func.date(User.created_at), func.count()).where(User.deleted_at.is_(None))
        .group_by(func.date(User.created_at)).order_by(func.date(User.created_at).desc()).limit(30)
    ).all()
    metrics["activity"] = db.session.scalars(select(AdminActivityLog).order_by(AdminActivityLog.created_at.desc()).limit(20)).all()
    metrics["userGrowth"] = [{"date": str(day), "count": count} for day, count in metrics["userGrowth"]]
    metrics["activity"] = [{"action": item.action, "type": item.target_type, "createdAt": item.created_at.isoformat()} for item in metrics["activity"]]
    return metrics


def list_discount_codes() -> list[dict]:
    return [{
        "id": item.id, "code": item.code, "type": item.discount_type, "value": str(item.value),
        "currency": item.currency, "active": item.is_active, "maximumUses": item.maximum_uses,
        "usesCount": item.uses_count,
    } for item in db.session.scalars(select(DiscountCode).order_by(DiscountCode.code)).all()]


def create_discount_code(data: dict) -> dict:
    code = _text(data, "code", required=True, maximum=80).upper()
    discount_type = _text(data, "type", required=True, maximum=20)
    if discount_type not in {"fixed", "percent"}:
        raise ValidationError("Discount type must be fixed or percent.", {"type": "invalid"})
    value = _money(data.get("value"), "value")
    if value == 0 or (discount_type == "percent" and value > 100):
        raise ValidationError("Discount value is outside its allowed range.", {"value": "invalid"})
    item = DiscountCode(
        code=code,
        discount_type=discount_type,
        value=value,
        currency=_pricing_currency(data.get("currency", default_currency())),
    )
    db.session.add(item)
    db.session.flush()
    _commit("discount.created", "discount_code", item.id)
    return {"id": item.id, "code": item.code, "type": item.discount_type, "value": str(item.value)}
