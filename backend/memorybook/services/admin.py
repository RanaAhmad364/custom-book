from __future__ import annotations

import hashlib
import copy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from flask import request
from sqlalchemy import func, or_, select
from werkzeug.exceptions import NotFound

from memorybook.errors import ConflictError, ServiceUnavailableError, ValidationError
from memorybook.extensions import db
from memorybook.integrations.asset_storage import get_asset_storage
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
    EmailLog,
    OrderStatusHistory,
    PagePricing,
    PaperType,
    Payment,
    PdfOrder,
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
from memorybook.services.catalog_projects import _valid_image_signature
from memorybook.services.catalog_projects import serialize_book, serialize_category, serialize_collection, serialize_template
from memorybook.services.notifications import queue_order_event

ADMIN_PRINT_STATES = {
    "order_placed",
    "payment_confirmed",
    "design_verified",
    "in_production",
    "quality_check",
    "packed",
    "shipped",
    "out_for_delivery",
    "delivered",
    "cancelled",
    "cancellation_requested",
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
        if not isinstance(key, str) or not key.startswith("catalog/") or len(key) > 1024:
            raise ValidationError("Design images must reference persisted catalog asset keys.", {"assets": "invalid_key"})
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
    if not book.title.strip() or not book.description.strip() or not book.category_id:
        raise ValidationError("Complete the book product details before publishing.", {"product": "incomplete"})
    template.published_design_document = copy.deepcopy(document)
    template.published_version = template.version
    template.is_active = True
    book.is_active = True
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
    templates = db.session.scalars(
        select(BookTemplate).where(BookTemplate.product_id == book.id, BookTemplate.deleted_at.is_(None))
    ).all()
    book.is_active = False
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


def upload_catalog_asset(file, owner: User) -> dict:
    file.stream.seek(0, 2)
    byte_size = file.stream.tell()
    file.stream.seek(0)
    metadata = AssetMetadataSchema.load(file.filename, file.mimetype, byte_size)
    signature = file.stream.read(16)
    file.stream.seek(0)
    if not _valid_image_signature(metadata["mime_type"], signature):
        raise ValidationError("The image contents do not match the selected file type.", {"file": "invalid_content"})
    digest = hashlib.sha256()
    for block in iter(lambda: file.stream.read(1024 * 1024), b""):
        digest.update(block)
    file.stream.seek(0)
    key = f"catalog/{owner.id}/{uuid4().hex}"
    storage = get_asset_storage()
    storage.upload(key, file.stream, metadata["mime_type"])
    _commit("catalog_asset.uploaded", "catalog_asset", owner.id, {
        "assetKey": key,
        "filename": metadata["filename"],
        "mimeType": metadata["mime_type"],
        "size": metadata["byte_size"],
        "checksum": digest.hexdigest(),
    })
    return {
        "assetKey": key,
        "url": storage.download_url(key),
        "filename": metadata["filename"],
        "mimeType": metadata["mime_type"],
        "size": metadata["byte_size"],
        "checksum": digest.hexdigest(),
    }


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


def dashboard_metrics() -> dict:
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
    return {
        "totalUsers": db.session.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))) or 0,
        "activeProjects": db.session.scalar(select(func.count()).select_from(UserProject).where(UserProject.status != "deleted")) or 0,
        "pdfPurchases": pdf_count,
        "printOrders": print_count,
        "revenue": str(Decimal(revenue_pdf or 0) + Decimal(revenue_print or 0)),
        "pendingOrders": pending,
        "booksInProduction": production,
        "recentOrders": recent[:8],
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
    return {
        **serialize_book(book),
        "isPublished": book.is_active,
        "coverAssetKey": book.cover_asset_key,
        "adminMetadata": book.admin_metadata or {},
    }


def _validate_product_metadata(value: dict) -> dict:
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
    if "printingTiers" in metadata:
        tiers = metadata["printingTiers"]
        if not isinstance(tiers, list) or any(item not in {"LIGHT", "BASIC", "PREMIUM"} for item in tiers):
            raise ValidationError("printingTiers contains an unsupported tier.", {"printingTiers": "invalid"})
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
    for field in ("pdfPrice", "printingPrice"):
        if field in metadata:
            metadata[field] = str(_money(metadata[field], field))
    if "productionDays" in metadata:
        metadata["productionDays"] = _positive_int(metadata["productionDays"], "productionDays")
    return metadata


def list_products(args) -> dict:
    page, per_page = _page_params(args)
    query = select(BookProduct).where(BookProduct.deleted_at.is_(None)).order_by(BookProduct.updated_at.desc())
    if args.get("published") in {"true", "false"}:
        query = query.where(BookProduct.is_active.is_(args.get("published") == "true"))
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
    collection = _collection_by_id(data.get("collectionId", item.collection_id))
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
    for source, target, maximum in (
        ("description", "description", 10000), ("style", "style", 60), ("occasion", "occasion", 60),
        ("bookType", "book_type", 40), ("currency", "currency", 3), ("coverAssetKey", "cover_asset_key", 1024),
    ):
        if source in data:
            value = _text(data, source, required=source == "description", maximum=maximum)
            if source == "currency" and value and (len(value) != 3 or not value.isalpha()):
                raise ValidationError("currency must be a three-letter code.", {"currency": "invalid"})
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
        item.admin_metadata = _validate_product_metadata(_body_dict(data["adminMetadata"], "adminMetadata"))
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
        return publish_book_design(product_id)["product"]
    templates = db.session.scalars(
        select(BookTemplate).where(BookTemplate.product_id == item.id, BookTemplate.deleted_at.is_(None))
    ).all()
    for template in templates:
        template.is_active = False
    item.is_active = published
    _commit("book.published" if published else "book.unpublished", "book_product", item.id)
    return _product_dict(item)


def delete_product(product_id: str) -> None:
    item = db.session.get(BookProduct, product_id)
    if item is None or item.deleted_at is not None:
        raise NotFound("Book product was not found.")
    item.deleted_at = datetime.now(UTC)
    item.is_active = False
    _commit("book.deleted", "book_product", item.id)


def _save_simple_catalog(model, data: dict, object_id: str | None, kind: str) -> dict:
    item = db.session.get(model, object_id) if object_id else model()
    if object_id and (item is None or item.deleted_at is not None):
        raise NotFound(f"{kind.title()} was not found.")
    name = _text(data, "name", required=not object_id, maximum=160)
    slug = _text(data, "slug", required=not object_id, maximum=180)
    if name is not None:
        item.name = name
    if slug is not None:
        item.slug = slug
    for field, attr, max_length in (
        ("description", "description", 5000), ("style", "style", 60), ("heroAssetKey", "hero_asset_key", 1024),
        ("eyebrow", "eyebrow", 120),
    ):
        if field in data and hasattr(item, attr):
            setattr(item, attr, _text(data, field, maximum=max_length))
    if "sortOrder" in data and hasattr(item, "sort_order"):
        try:
            item.sort_order = int(data["sortOrder"])
        except (ValueError, TypeError) as failure:
            raise ValidationError("sortOrder must be an integer.", {"sortOrder": "invalid"}) from failure
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
        item.is_active = data["isPublished"]
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
    return result


def save_simple_catalog(model, kind: str, data: dict, object_id: str | None = None) -> dict:
    return _save_simple_catalog(model, data, object_id, kind)


def delete_simple_catalog(model, kind: str, object_id: str) -> None:
    item = db.session.get(model, object_id)
    if item is None or item.deleted_at is not None:
        raise NotFound(f"{kind.title()} was not found.")
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


def _order_dict(order, kind: str) -> dict:
    user = db.session.get(User, order.user_id)
    project = db.session.get(UserProject, order.project_id)
    payload = {
        "id": order.id,
        "orderNumber": order.order_number,
        "type": kind,
        "userId": order.user_id,
        "userEmail": user.email if user else None,
        "projectId": order.project_id,
        "projectTitle": project.title if project else None,
        "revisionId": order.project_revision_id,
        "status": order.status,
        "currency": order.currency,
        "amount": str(order.total_amount),
        "paidAt": order.paid_at.isoformat() if order.paid_at else None,
        "createdAt": order.created_at.isoformat(),
    }
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
        items = db.session.scalars(select(PrintOrderItem).where(PrintOrderItem.print_order_id == order.id)).all()
        payload["items"] = [{
            "quantity": item.quantity, "pageCount": item.page_count, "specification": item.specification_snapshot,
        } for item in items]
        shipment = db.session.scalar(select(Shipment).where(Shipment.print_order_id == order.id).order_by(Shipment.created_at.desc()))
        payload["shipment"] = ({
            "id": shipment.id, "carrier": shipment.carrier, "trackingNumber": shipment.tracking_number,
            "status": shipment.status, "estimatedDeliveryAt": shipment.estimated_delivery_at.isoformat() if shipment.estimated_delivery_at else None,
        } if shipment else None)
    else:
        payload["pageCount"] = order.page_count
    return payload


def list_orders(args) -> dict:
    page, per_page = _page_params(args)
    kind = args.get("type", "all")
    if kind not in {"all", "pdf", "print"}:
        raise ValidationError("Order type must be all, pdf, or print.", {"type": "invalid"})
    result = []
    limit = page * per_page
    total = 0
    search = args.get("search", "").strip()[:120]
    if kind in {"all", "pdf"}:
        query = select(PdfOrder).order_by(PdfOrder.created_at.desc())
        count_query = select(func.count()).select_from(PdfOrder)
        if args.get("status"):
            query = query.where(PdfOrder.status == args["status"][:30])
            count_query = count_query.where(PdfOrder.status == args["status"][:30])
        if search:
            query = query.join(User, User.id == PdfOrder.user_id).where(
                or_(PdfOrder.order_number.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"))
            )
            count_query = count_query.join(User, User.id == PdfOrder.user_id).where(
                or_(PdfOrder.order_number.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"))
            )
        total += db.session.scalar(count_query) or 0
        result.extend(_order_dict(item, "pdf") for item in db.session.scalars(query.limit(limit)).all())
    if kind in {"all", "print"}:
        query = select(PrintOrder).order_by(PrintOrder.created_at.desc())
        count_query = select(func.count()).select_from(PrintOrder)
        if args.get("status"):
            query = query.where(PrintOrder.status == args["status"][:30])
            count_query = count_query.where(PrintOrder.status == args["status"][:30])
        if search:
            query = query.join(User, User.id == PrintOrder.user_id).where(
                or_(PrintOrder.order_number.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"))
            )
            count_query = count_query.join(User, User.id == PrintOrder.user_id).where(
                or_(PrintOrder.order_number.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"))
            )
        total += db.session.scalar(count_query) or 0
        result.extend(_order_dict(item, "print") for item in db.session.scalars(query.limit(limit)).all())
    result.sort(key=lambda item: item["createdAt"], reverse=True)
    return {"items": result[(page - 1) * per_page:page * per_page], "pagination": {
        "page": page, "perPage": per_page, "totalItems": total, "totalPages": (total + per_page - 1) // per_page,
    }}


def update_order(order_id: str, kind: str, data: dict, actor_id: str) -> dict:
    if kind not in {"pdf", "print"}:
        raise ValidationError("Order type must be pdf or print.", {"type": "invalid"})
    model = PdfOrder if kind == "pdf" else PrintOrder
    order = db.session.get(model, order_id)
    if order is None:
        raise NotFound("Order was not found.")
    shipment = None
    if "status" in data:
        state = _text(data, "status", required=True, maximum=40)
        allowed = {"cancellation_requested", "cancelled"} if kind == "pdf" else ADMIN_PRINT_STATES
        if state not in allowed:
            raise ValidationError("The requested order status is not allowed.", {"status": "invalid"})
        if state != order.status:
            if state == "cancelled" and order.paid_at is not None:
                raise ConflictError("Paid orders must be refunded through the payment provider before cancellation.")
            old_status = order.status
            order.status = state
            db.session.add(OrderStatusHistory(
                pdf_order_id=order.id if kind == "pdf" else None,
                print_order_id=order.id if kind == "print" else None,
                status=state,
                note=f"Admin status update from {old_status}",
                changed_by_user_id=actor_id,
            ))
            queue_order_event(
                order.user_id,
                f"order_status:{kind}:{order.id}:{state}",
                "order",
                "Order status updated",
                f"Order {order.order_number} is now {state.replace('_', ' ')}.",
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
        result["items"] = [{
            "id": item.id, "userId": item.user_id, "provider": item.provider,
            "purpose": item.purpose, "paymentMethod": item.payment_method,
            "providerPaymentId": item.provider_payment_id, "status": item.status,
            "amount": str(item.amount), "currency": item.currency,
            "orderId": item.pdf_order_id or item.print_order_id, "createdAt": item.created_at.isoformat(),
        } for item in result["items"]]
    return result


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
        "tiers": [{"id": x.id, "code": x.code, "name": x.name, "description": x.description, "basePrice": str(x.base_price), "currency": x.currency, "active": x.is_active} for x in tiers],
        "pagePricing": [{"id": x.id, "tierId": x.tier_id, "minimumPages": x.minimum_pages, "maximumPages": x.maximum_pages, "pricePerPage": str(x.price_per_page)} for x in page_pricing],
        "rules": [{"id": x.id, "code": x.code, "name": x.name, "type": x.adjustment_type, "amount": str(x.amount), "active": x.is_active} for x in rules],
        "shipping": [{"id": x.id, "countryCode": x.country_code, "regionCode": x.region_code, "serviceCode": x.service_code, "serviceName": x.service_name, "price": str(x.price), "currency": x.currency, "active": x.is_active} for x in shipping],
        "sizes": [{"id": x.id, "code": x.code, "name": x.name, "widthMm": str(x.width_mm), "heightMm": str(x.height_mm), "active": x.is_active} for x in sizes],
        "covers": [{"id": x.id, "name": x.name, "description": x.description, "active": x.is_active} for x in covers],
        "papers": [{"id": x.id, "name": x.name, "description": x.description, "weightGsm": x.weight_gsm, "active": x.is_active} for x in papers],
        "discounts": [{"id": x.id, "code": x.code, "type": x.discount_type, "value": str(x.value), "currency": x.currency, "active": x.is_active, "maximumUses": x.maximum_uses, "usesCount": x.uses_count} for x in discounts],
        "variants": [{"id": row[0].id, "productId": row[0].product_id, "book": row[1], "size": row[2], "cover": row[3], "paper": row[4], "basePrice": str(row[0].base_price), "active": row[0].is_active, "kind": "variant"} for row in variants],
    }


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
        if "basePrice" in data:
            item.base_price = _money(data["basePrice"], "basePrice")
        if "name" in data:
            item.name = _text(data, "name", required=True, maximum=100)
    elif kind == "shipping":
        if "price" in data:
            item.price = _money(data["price"], "price")
        if "serviceName" in data:
            item.service_name = _text(data, "serviceName", required=True, maximum=100)
    elif kind == "size":
        for field, attr in (("widthMm", "width_mm"), ("heightMm", "height_mm")):
            if field in data:
                value = _money(data[field], field)
                if value == 0:
                    raise ValidationError(f"{field} must be greater than zero.", {field: "invalid"})
                setattr(item, attr, value)
    elif kind == "pagePricing":
        for field, attr in (("minimumPages", "minimum_pages"), ("maximumPages", "maximum_pages")):
            if field in data:
                setattr(item, attr, _positive_int(data[field], field))
        if "pricePerPage" in data:
            item.price_per_page = _money(data["pricePerPage"], "pricePerPage")
        if item.maximum_pages < item.minimum_pages:
            raise ValidationError("Maximum pages must be greater than or equal to minimum pages.", {"pages": "invalid_range"})
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
    elif kind == "variant":
        if "basePrice" in data:
            item.base_price = _money(data["basePrice"], "basePrice")
    elif "description" in data and hasattr(item, "description"):
        item.description = _text(data, "description", maximum=500)
    if "active" in data:
        if not isinstance(data["active"], bool):
            raise ValidationError("active must be a boolean.", {"active": "invalid"})
        item.is_active = data["active"]
    _commit("pricing.updated", kind, item.id, {"fields": sorted(data)})
    return {"id": item.id, "active": item.is_active}


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
    if product is None or product.deleted_at is not None or size is None or cover is None or paper is None:
        raise ValidationError("Product, size, cover, and paper options must exist.", {"variant": "invalid_reference"})
    variant = BookVariant(
        product_id=product.id,
        size_id=size.id,
        cover_type_id=cover.id,
        paper_type_id=paper.id,
        sku=sku,
        base_price=_money(data.get("basePrice"), "basePrice"),
    )
    db.session.add(variant)
    db.session.flush()
    _commit("pricing.variant_created", "book_variant", variant.id)
    return {"id": variant.id, "productId": product.id, "basePrice": str(variant.base_price), "active": variant.is_active}


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
    item = DiscountCode(code=code, discount_type=discount_type, value=value, currency=data.get("currency"))
    db.session.add(item)
    db.session.flush()
    _commit("discount.created", "discount_code", item.id)
    return {"id": item.id, "code": item.code, "type": item.discount_type, "value": str(item.value)}
