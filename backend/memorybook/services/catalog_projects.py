from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import delete, func, select

from memorybook.errors import ConflictError, ServiceUnavailableError, ValidationError
from memorybook.extensions import db
from memorybook.integrations.asset_storage import get_asset_storage
from memorybook.integrations.image_validation import validate_and_sanitize_image
from memorybook.models import (
    BookCategory,
    BookCollection,
    BookProduct,
    BookTemplate,
    BookTemplateVersion,
    BookVariant,
    CoverType,
    ProjectAsset,
    ProjectElement,
    ProjectPage,
    ProjectRevision,
    ProjectSnapshot,
    TemplateElement,
    TemplatePage,
    User,
    UserProject,
)
from memorybook.repositories.catalog_projects import CatalogRepository


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _catalog_asset_url(value: str | None) -> str | None:
    if not value:
        return None
    if urlparse(value).scheme in {"http", "https"}:
        return value
    storage = get_asset_storage()
    if value.startswith("catalog/"):
        return storage.public_download_url(value)
    if value.startswith("admin-design/"):
        return storage.private_download_url(value)
    return storage.download_url(value)


def serialize_category(category: BookCategory) -> dict:
    first_book = db.session.scalar(
        select(BookProduct).where(BookProduct.category_id == category.id, BookProduct.is_active.is_(True))
        .order_by(BookProduct.is_featured.desc(), BookProduct.title)
    )
    image_key = category.hero_asset_key
    if image_key and not (
        image_key.startswith(("catalog/", "http://", "https://"))
    ):
        image_key = None
    if image_key is None and first_book:
        image_key = first_book.cover_asset_key
    if image_key and not image_key.startswith(("catalog/", "http://", "https://")):
        image_key = None
    image = _catalog_asset_url(image_key)
    return {
        "id": category.id,
        "name": category.name,
        "title": category.name,
        "slug": category.slug,
        "description": category.description or "",
        "style": category.style or "Thoughtful",
        "heroImage": image,
        "image": image,
        "imageAlt": f"{category.name} photo books",
        "sortOrder": category.sort_order,
    }


def serialize_collection(collection: BookCollection) -> dict:
    category = db.session.get(BookCategory, collection.category_id) if collection.category_id else None
    return {
        "id": collection.id,
        "name": collection.name,
        "title": collection.name,
        "slug": collection.slug,
        "description": collection.description or "",
        "image": _catalog_asset_url(collection.hero_asset_key),
        "imageAlt": f"{collection.name} collection",
        "eyebrow": collection.eyebrow or "A thoughtful collection",
        "recommendedLayouts": collection.recommended_layouts or [],
        "relatedCategories": collection.related_categories or [],
        "categoryId": collection.category_id,
        "categoryName": category.name if category else None,
        "categorySlug": category.slug if category else None,
        "sortOrder": collection.sort_order,
    }


def serialize_book(book: BookProduct, *, include_gallery: bool = False) -> dict:
    category = db.session.get(BookCategory, book.category_id)
    collection = db.session.get(BookCollection, book.collection_id) if book.collection_id else None
    if collection is not None and (collection.deleted_at is not None or not collection.is_active):
        collection = None
    variant_cover_ids = db.session.scalars(
        select(BookVariant.cover_type_id).where(BookVariant.product_id == book.id, BookVariant.is_active.is_(True))
    ).all()
    cover_names = db.session.scalars(
        select(CoverType.name).where(CoverType.id.in_(set(variant_cover_ids)), CoverType.is_active.is_(True))
    ).all() if variant_cover_ids else []
    result = {
        "id": book.id,
        "slug": book.slug,
        "title": book.title,
        "category": category.name if category else "",
        "categoryId": book.category_id,
        "categorySlug": category.slug if category else "",
        "collection": collection.name if collection else "",
        "collectionId": book.collection_id,
        "collectionSlug": collection.slug if collection else "",
        "description": book.description,
        "image": _catalog_asset_url(book.cover_asset_key),
        "imageAlt": book.title,
        "style": book.style,
        "occasion": book.occasion,
        "bookType": book.book_type,
        "pageCountMin": book.page_count_min,
        "pageCountMax": book.page_count_max,
        "pageCount": book.page_count_min,
        "pages": (
            f"{book.page_count_min} pages"
            if book.page_count_min == book.page_count_max or book.page_count_max is None
            else f"{book.page_count_min}–{book.page_count_max} pages"
        ),
        "startingPrice": float(book.starting_price),
        "currency": book.currency,
        "featured": book.is_featured,
        "format": ", ".join(sorted(set(cover_names))) or "Customizable",
    }
    if include_gallery:
        gallery = []
        if result["image"]:
            gallery.append({
                "image": result["image"],
                "imageAlt": book.title,
                "label": "Cover",
            })
        metadata = book.admin_metadata if isinstance(book.admin_metadata, dict) else {}
        preview_keys = metadata.get("previewImageKeys", [])
        if isinstance(preview_keys, list):
            gallery.extend(
                {
                    "image": _catalog_asset_url(key),
                    "imageAlt": f"{book.title} preview {index}",
                    "label": f"Preview {index}",
                }
                for index, key in enumerate(preview_keys, start=1)
                if isinstance(key, str) and key.startswith("catalog/")
            )
        result["gallery"] = gallery
        result["designTemplateId"] = db.session.scalar(
            select(BookTemplate.id)
            .where(
                BookTemplate.product_id == book.id,
                BookTemplate.is_active.is_(True),
                BookTemplate.deleted_at.is_(None),
                BookTemplate.published_design_document.is_not(None),
            )
            .order_by(BookTemplate.updated_at.desc())
            .limit(1)
        )
    return result


def serialize_template(
    template: BookTemplate,
    *,
    include_pages: bool = False,
    include_design: bool = False,
) -> dict:
    category = db.session.get(BookCategory, template.category_id) if template.category_id else None
    result = {
        "id": template.id,
        "slug": template.slug,
        "name": template.name,
        "title": template.name,
        "description": template.description or "",
        "previewImage": _catalog_asset_url(template.preview_asset_key),
        "version": template.version,
        "publishedVersion": template.published_version,
        "published": template.is_active,
        "productId": template.product_id,
        "categoryId": template.category_id,
        "category": category.name if category else "Custom",
    }
    if include_pages:
        pages = db.session.scalars(
            select(TemplatePage).where(TemplatePage.template_id == template.id).order_by(TemplatePage.page_number)
        ).all()
        result["pages"] = [
            {
                "pageNumber": page.page_number,
                "type": page.page_type,
                "layout": page.layout_key,
                "background": page.background,
                "elements": [
                    {
                        "type": element.element_type,
                        "sortOrder": element.sort_order,
                        "x": float(element.x),
                        "y": float(element.y),
                        "width": float(element.width),
                        "height": float(element.height),
                        "content": element.content,
                    }
                    for element in db.session.scalars(
                        select(TemplateElement)
                        .where(TemplateElement.template_page_id == page.id)
                        .order_by(TemplateElement.sort_order)
                    ).all()
                ],
            }
            for page in pages
        ]
    if include_design and template.design_document:
        design = copy.deepcopy(template.design_document)
        asset_urls = {}
        serialized_assets = []
        for asset in design.get("assets", []):
            asset_key = asset.get("assetKey")
            if not isinstance(asset_key, str) or not asset_key.startswith(("catalog/", "admin-design/")):
                continue
            asset_url = _catalog_asset_url(asset_key)
            asset_urls[asset.get("id")] = asset_url
            serialized_assets.append({**asset, "src": asset_url})
        design["assets"] = serialized_assets
        for page in design.get("pages", []):
            for element in page.get("elements", []):
                if element.get("type") == "image" and element.get("assetId") in asset_urls:
                    element["src"] = asset_urls[element["assetId"]]
        result["designDocument"] = design
    return result


def list_books(filters: dict) -> tuple[list[dict], int]:
    query = CatalogRepository.books_query(filters)
    total = db.session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    products = db.session.scalars(
        query.offset((filters["page"] - 1) * filters["per_page"]).limit(filters["per_page"])
    ).all()
    return [serialize_book(book) for book in products], total


def list_categories() -> list[dict]:
    return [serialize_category(item) for item in db.session.scalars(CatalogRepository.categories_query()).all()]


def list_collections() -> list[dict]:
    return [serialize_collection(item) for item in db.session.scalars(CatalogRepository.collections_query()).all()]


def list_templates(page: int, per_page: int, search: str, category: str) -> tuple[list[dict], int]:
    query = CatalogRepository.templates_query()
    if search:
        query = query.where(BookTemplate.name.ilike(f"%{search}%"))
    if category:
        query = query.join(BookCategory, BookTemplate.category_id == BookCategory.id).where(
            (BookCategory.slug == category) | BookCategory.name.ilike(category)
        )
    total = db.session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    templates = db.session.scalars(query.offset((page - 1) * per_page).limit(per_page)).all()
    return [serialize_template(template) for template in templates], total


def get_template(template_id: str) -> dict | None:
    template = db.session.scalar(CatalogRepository.templates_query().where(
        (BookTemplate.id == template_id) | (BookTemplate.slug == template_id),
    ))
    return serialize_template(template, include_pages=True) if template else None


def _asset_src(asset: ProjectAsset) -> str:
    return get_asset_storage().private_download_url(asset.storage_key)


def _stored_document(document: dict, project_id: str) -> dict:
    stored = copy.deepcopy(document)
    for asset in stored.get("assets", []):
        asset.pop("src", None)
    for page in stored.get("pages", []):
        for element in page.get("elements", []):
            if element.get("type") == "image":
                element.pop("src", None)
    stored["metadata"]["id"] = project_id
    stored["metadata"]["updatedAt"] = datetime.now(UTC).isoformat()
    return stored


def serialize_project(project: UserProject, owner: User) -> dict:
    document = copy.deepcopy(project.document) if project.document else None
    product = db.session.get(BookProduct, project.product_id) if project.product_id else None
    category = db.session.get(BookCategory, product.category_id) if product else None
    first_asset = db.session.scalar(
        select(ProjectAsset).where(ProjectAsset.project_id == project.id).order_by(ProjectAsset.created_at)
    )
    image = _asset_src(first_asset) if first_asset else (
        _catalog_asset_url(product.cover_asset_key) if product else None
    )
    if document:
        assets = db.session.scalars(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id)
        ).all()
        by_id = {asset.id: asset for asset in assets}
        document["metadata"]["id"] = project.id
        document["metadata"]["owner"] = owner.email
        document["metadata"]["title"] = project.title
        document["metadata"]["updatedAt"] = _iso(project.updated_at)
        serialized_assets = []
        for item in document.get("assets", []):
            asset = by_id.get(item.get("id"))
            if asset is None:
                continue
            serialized = {
                **item,
                "id": asset.id,
                "name": asset.original_filename or item.get("name", "Photo"),
                "mimeType": asset.mime_type,
                "size": asset.byte_size,
                "width": asset.width_px,
                "height": asset.height_px,
                "src": _asset_src(asset),
            }
            serialized_assets.append(serialized)
        document["assets"] = serialized_assets
        asset_urls = {item["id"]: item["src"] for item in serialized_assets}
        for page in document.get("pages", []):
            for element in page.get("elements", []):
                if element.get("type") == "image" and element.get("assetId") in asset_urls:
                    element["src"] = asset_urls[element["assetId"]]
    return {
        "id": project.id,
        "title": project.title,
        "status": project.status,
        "pageCount": project.page_count,
        "productId": project.product_id,
        "templateId": project.template_id,
        "templateVersion": project.template_version,
        "image": image,
        "category": category.name if category else "Custom",
        "version": project.version,
        "createdAt": _iso(project.created_at),
        "updatedAt": _iso(project.updated_at),
        "document": document,
    }


def _sync_pages(project: UserProject, document: dict) -> None:
    db.session.execute(delete(ProjectElement).where(ProjectElement.page_id.in_(
        select(ProjectPage.id).where(ProjectPage.project_id == project.id)
    )))
    db.session.execute(delete(ProjectPage).where(ProjectPage.project_id == project.id))
    pages_by_id = {}
    for index, page_data in enumerate(document["pages"]):
        page = ProjectPage(
            id=page_data["id"],
            project_id=project.id,
            page_number=document["pageOrder"].index(page_data["id"]) + 1 if page_data["id"] in document["pageOrder"] else index + 1,
            page_type=page_data.get("type", "page"),
            label=page_data.get("label"),
            layout_key=page_data.get("layout"),
            background=page_data.get("background"),
            elements=page_data.get("elements", []),
        )
        db.session.add(page)
        pages_by_id[page.id] = page
    db.session.flush()
    for page_data in document["pages"]:
        page_id = page_data["id"]
        for sort_order, element in enumerate(page_data.get("elements", [])):
            asset_id = element.get("assetId") if element.get("type") == "image" else None
            db.session.add(ProjectElement(
                page_id=page_id,
                asset_id=asset_id,
                element_type=element.get("type", "shape"),
                sort_order=sort_order,
                x=element.get("x", 0),
                y=element.get("y", 0),
                width=element.get("width", 0.01),
                height=element.get("height", 0.01),
                rotation=element.get("rotation", 0),
                content={key: value for key, value in element.items() if key not in {
                    "id", "type", "assetId", "x", "y", "width", "height", "rotation", "src",
                }},
            ))


def _check_document_assets(project_id: str, document: dict) -> None:
    asset_ids = {asset.get("id") for asset in document.get("assets", []) if isinstance(asset, dict)}
    if len(asset_ids) != len(document.get("assets", [])):
        raise ValidationError("Every project asset must have a unique ID.", {"assets": "invalid"})
    available_ids = set(db.session.scalars(
        select(ProjectAsset.id).where(ProjectAsset.project_id == project_id, ProjectAsset.id.in_(asset_ids))
    ).all()) if asset_ids else set()
    if available_ids != asset_ids:
        raise ValidationError("Project document contains an asset not uploaded to this project.", {"assets": "invalid"})
    for page in document.get("pages", []):
        for element in page.get("elements", []):
            if element.get("type") == "image" and element.get("assetId") not in available_ids:
                raise ValidationError("Every photo element must reference an uploaded project asset.", {"assetId": "invalid"})
    cover_design = (document.get("cover") or {}).get("design") or {}
    front_asset_id = (cover_design.get("front") or {}).get("photoAssetId")
    if front_asset_id is not None and front_asset_id not in available_ids:
        raise ValidationError("The cover photo must reference an uploaded project asset.", {"photoAssetId": "invalid"})


def _sync_document(project: UserProject, document: dict) -> None:
    _check_document_assets(project.id, document)
    stored = _stored_document(document, project.id)
    project.title = stored["metadata"]["title"].strip()
    project.document = stored
    project.page_count = int((stored.get("book") or {}).get("pageCount") or max(0, len(stored["pages"]) - 1))
    _sync_pages(project, stored)


def _assert_version(project: UserProject, expected_version: int | None) -> None:
    if expected_version is not None and expected_version != project.version:
        raise ConflictError(
            "This project changed on another session. Reload the latest project before saving.",
            {"expectedVersion": expected_version, "currentVersion": project.version},
        )


def _next_version(project: UserProject, expected_version: int | None) -> None:
    _assert_version(project, expected_version)
    project.version += 1
    project.updated_at = datetime.now(UTC)


def _copy_published_design(template: BookTemplate, project: UserProject, owner: User) -> dict:
    document = copy.deepcopy(template.published_design_document)
    if not document:
        return document
    page_id_map = {
        page["id"]: str(uuid4())
        for page in document.get("pages", [])
        if isinstance(page, dict) and isinstance(page.get("id"), str)
    }
    element_id_map = {
        element["id"]: str(uuid4())
        for page in document.get("pages", [])
        if isinstance(page, dict)
        for element in page.get("elements", [])
        if isinstance(element, dict) and isinstance(element.get("id"), str)
    }
    for page in document.get("pages", []):
        if page.get("id") in page_id_map:
            page["id"] = page_id_map[page["id"]]
        for element in page.get("elements", []):
            if element.get("id") in element_id_map:
                element["id"] = element_id_map[element["id"]]
    document["pageOrder"] = [
        page_id_map.get(page_id, page_id)
        for page_id in document.get("pageOrder", [])
    ]
    cover_page_id = (document.get("cover") or {}).get("pageId")
    if cover_page_id in page_id_map:
        document["cover"]["pageId"] = page_id_map[cover_page_id]
    storage = get_asset_storage() if document.get("assets") else None
    copied_keys = []
    asset_id_map = {}
    asset_records = []
    try:
        for source in document.get("assets", []):
            asset_id = str(uuid4())
            source_key = source["assetKey"]
            target_key = f"projects/{owner.id}/{project.id}/{asset_id}"
            storage.copy(source_key, target_key)
            copied_keys.append(target_key)
            asset_id_map[source["id"]] = asset_id
            db.session.add(ProjectAsset(
                id=asset_id,
                project_id=project.id,
                storage_key=target_key,
                mime_type=source["mimeType"],
                byte_size=source["size"],
                checksum_sha256=source["checksum"],
                original_filename=source["name"],
                width_px=source.get("width"),
                height_px=source.get("height"),
            ))
            asset_records.append({
                key: value
                for key, value in source.items()
                if key not in {"assetKey", "checksum", "src"}
            } | {"id": asset_id})
    except ServiceUnavailableError:
        for key in copied_keys:
            try:
                storage.delete(key)
            except ServiceUnavailableError:
                from flask import current_app

                current_app.logger.exception("Copied template asset cleanup failed.")
        db.session.rollback()
        raise
    for page in document.get("pages", []):
        for element in page.get("elements", []):
            if element.get("type") == "image":
                element["assetId"] = asset_id_map[element["assetId"]]
                element.pop("src", None)
    front_design = (document.get("cover", {}).get("design") or {}).get("front")
    if front_design and front_design.get("photoAssetId") is not None:
        front_design["photoAssetId"] = asset_id_map[front_design["photoAssetId"]]
    document["assets"] = asset_records
    document["metadata"]["id"] = project.id
    document["metadata"]["owner"] = owner.email
    document["metadata"]["title"] = project.title
    document["metadata"]["createdAt"] = datetime.now(UTC).isoformat()
    document["metadata"]["updatedAt"] = datetime.now(UTC).isoformat()
    document["book"]["template"] = {
        "id": template.id,
        "title": template.name,
        "category": serialize_template(template)["category"],
        "image": _catalog_asset_url(template.preview_asset_key),
    }
    project.page_count = int(document.get("book", {}).get("pageCount") or max(0, len(document.get("pages", [])) - 1))
    return document


def create_project(owner: User, data: dict) -> UserProject:
    template = db.session.get(BookTemplate, data["template_id"]) if data["template_id"] else None
    product_id = data["product_id"]
    if product_id and not data["template_id"]:
        raise ValidationError(
            "The selected book does not have an eligible published design.",
            {"templateId": "required"},
        )
    if product_id and not db.session.scalar(
        select(BookProduct.id)
        .join(BookCategory, BookProduct.category_id == BookCategory.id)
        .where(
            BookProduct.id == product_id,
            BookProduct.is_active.is_(True),
            BookProduct.deleted_at.is_(None),
            BookCategory.is_active.is_(True),
            BookCategory.deleted_at.is_(None),
        )
    ):
        raise ValidationError("The selected book product is unavailable.", {"productId": "not_found"})
    if data["template_id"] and (
        template is None
        or template.deleted_at is not None
        or not template.is_active
        or template.product_id is not None and template.published_design_document is None
    ):
        raise ValidationError("The selected template is unavailable.", {"templateId": "not_found"})
    if template and template.product_id:
        template_product = db.session.get(BookProduct, template.product_id)
        if (
            template_product is None
            or template_product.deleted_at is not None
            or not template_product.is_active
            or not db.session.scalar(
                select(BookCategory.id).where(
                    BookCategory.id == template_product.category_id,
                    BookCategory.is_active.is_(True),
                    BookCategory.deleted_at.is_(None),
                )
            )
        ):
            raise ValidationError("The selected template is unavailable.", {"templateId": "not_found"})
        if product_id and product_id != template_product.id:
            raise ValidationError("The selected template does not belong to the selected product.", {"templateId": "product_mismatch"})
        product_id = template_product.id
    elif product_id:
        raise ValidationError(
            "Choose the published design associated with this book.",
            {"templateId": "product_mismatch"},
        )
    if product_id and (template is None or template.published_design_document is None):
        raise ValidationError(
            "The selected book does not have an eligible published design.",
            {"templateId": "unavailable"},
        )
    project = UserProject(
        user_id=owner.id,
        product_id=product_id,
        template_id=data["template_id"],
        template_version=(
            (template.published_version or template.version) if template else None
        ),
        title=data["title"],
        page_count=data["page_count"],
        status="draft",
        version=1,
    )
    db.session.add(project)
    db.session.flush()
    document = data["document"]
    if document is None and template and template.published_design_document:
        document = _copy_published_design(template, project, owner)
    if document:
        document["metadata"]["id"] = project.id
        _sync_document(project, document)
    db.session.commit()
    return project


def update_project(project: UserProject, data: dict, expected_version: int | None) -> UserProject:
    _next_version(project, expected_version)
    document = data.pop("document", None)
    for key, value in data.items():
        setattr(project, key, value)
    if document is not None:
        if document["metadata"].get("id") not in (None, project.id):
            raise ValidationError("Project document belongs to another project.", {"document": "project_mismatch"})
        _sync_document(project, document)
    db.session.commit()
    return project


def delete_project(project: UserProject, expected_version: int | None) -> None:
    _next_version(project, expected_version)
    project.status = "deleted"
    db.session.commit()


def duplicate_project(source: UserProject, owner: User) -> UserProject:
    duplicate = UserProject(
        user_id=owner.id,
        product_id=source.product_id,
        template_id=source.template_id,
        template_version=source.template_version,
        title=f"{source.title} (copy)"[:200],
        status="draft",
        page_count=source.page_count,
        version=1,
    )
    db.session.add(duplicate)
    db.session.flush()
    document = copy.deepcopy(source.document)
    if not document:
        db.session.commit()
        return duplicate

    page_id_map = {page["id"]: str(uuid4()) for page in document.get("pages", [])}
    asset_id_map = {}
    source_assets = db.session.scalars(
        select(ProjectAsset).where(ProjectAsset.project_id == source.id)
    ).all()
    storage = get_asset_storage() if source_assets else None
    copied_keys = []
    try:
        for asset in source_assets:
            new_asset_id = str(uuid4())
            asset_id_map[asset.id] = new_asset_id
            target_key = f"projects/{owner.id}/{duplicate.id}/{new_asset_id}"
            storage.copy(asset.storage_key, target_key)
            copied_keys.append(target_key)
            db.session.add(ProjectAsset(
                id=new_asset_id,
                project_id=duplicate.id,
                storage_key=target_key,
                mime_type=asset.mime_type,
                byte_size=asset.byte_size,
                checksum_sha256=asset.checksum_sha256,
                original_filename=asset.original_filename,
                width_px=asset.width_px,
                height_px=asset.height_px,
            ))
    except ServiceUnavailableError:
        for key in copied_keys:
            try:
                storage.delete(key)
            except ServiceUnavailableError:
                from flask import current_app

                current_app.logger.exception("Duplicated project asset cleanup failed.")
        db.session.rollback()
        raise
    for page in document.get("pages", []):
        page["id"] = page_id_map[page["id"]]
        for element in page.get("elements", []):
            element["id"] = str(uuid4())
            if element.get("assetId") in asset_id_map:
                element["assetId"] = asset_id_map[element["assetId"]]
    document["pageOrder"] = [page_id_map[page_id] for page_id in document["pageOrder"]]
    document["metadata"]["id"] = duplicate.id
    document["metadata"]["title"] = duplicate.title
    document["metadata"]["createdAt"] = datetime.now(UTC).isoformat()
    document["assets"] = [
        {**asset, "id": asset_id_map[asset["id"]]}
        for asset in document.get("assets", [])
        if asset.get("id") in asset_id_map
    ]
    if document.get("cover", {}).get("pageId") in page_id_map:
        document["cover"]["pageId"] = page_id_map[document["cover"]["pageId"]]
    front_design = (document.get("cover", {}).get("design") or {}).get("front")
    if front_design and front_design.get("photoAssetId") in asset_id_map:
        front_design["photoAssetId"] = asset_id_map[front_design["photoAssetId"]]
    _sync_document(duplicate, document)
    db.session.commit()
    return duplicate


def save_page(project: UserProject, page: dict, expected_version: int | None) -> UserProject:
    document = copy.deepcopy(project.document or {
        "schemaVersion": 1,
        "metadata": {"id": project.id, "title": project.title, "updatedAt": _iso(project.updated_at)},
        "book": {"pageCount": 0},
        "pageOrder": [],
        "pages": [],
        "assets": [],
        "styles": {},
        "cover": {},
    })
    existing = next((item for item in document["pages"] if item["id"] == page["id"]), None)
    if existing is None and page["page_type"] == "cover":
        raise ConflictError("A project can contain only one cover page.")
    if existing is not None and (existing.get("type") == "cover") != (page["page_type"] == "cover"):
        raise ConflictError("The cover page type cannot be changed.")
    if existing is None:
        document["pages"].append(_page_payload(page))
        if page["page_type"] != "cover":
            document["book"]["pageCount"] = int(document.get("book", {}).get("pageCount", 0)) + 1
    else:
        document["pages"] = [_page_payload(page) if item["id"] == page["id"] else item for item in document["pages"]]
        document["pageOrder"].remove(page["id"])
    document["pageOrder"].insert(min(page["page_number"] - 1, len(document["pageOrder"])), page["id"])
    document["metadata"]["title"] = project.title
    return update_project(project, {"document": document}, expected_version)


def _page_payload(page: dict) -> dict:
    return {
        "id": page["id"],
        "type": page["page_type"],
        "label": page["label"],
        "layout": page["layout"],
        "background": page["background"],
        "elements": page["elements"],
    }


def delete_page(project: UserProject, page_id: str, expected_version: int | None) -> UserProject:
    document = copy.deepcopy(project.document)
    if not document:
        raise ValidationError("Project has no saved document.", {"pageId": "not_found"})
    if not any(page["id"] == page_id for page in document["pages"]):
        raise ValidationError("Page does not exist in this project.", {"pageId": "not_found"})
    page = next(page for page in document["pages"] if page["id"] == page_id)
    if page.get("type") == "cover" or document.get("cover", {}).get("pageId") == page_id:
        raise ConflictError("The cover page cannot be deleted.")
    document["pages"] = [page for page in document["pages"] if page["id"] != page_id]
    document["pageOrder"] = [item for item in document["pageOrder"] if item != page_id]
    document["book"]["pageCount"] = sum(page.get("type") != "cover" for page in document["pages"])
    return update_project(project, {"document": document}, expected_version)


def upload_asset(
    project: UserProject,
    owner: User,
    file,
    metadata: dict,
    asset_id: str | None,
    expected_version: int | None,
) -> ProjectAsset:
    storage = get_asset_storage()
    asset_id = asset_id or __import__("uuid").uuid4().hex
    if len(asset_id) > 36 or db.session.get(ProjectAsset, asset_id) is not None:
        raise ValidationError("Asset ID is invalid or already in use.", {"id": "invalid"})
    storage_key = f"projects/{owner.id}/{project.id}/{asset_id}"
    image, width, height = validate_and_sanitize_image(file.stream, metadata["mime_type"])
    checksum = hashlib.sha256(image.getbuffer()).hexdigest()
    _next_version(project, expected_version)
    storage.upload(storage_key, image, metadata["mime_type"])
    asset = ProjectAsset(
        id=asset_id,
        project_id=project.id,
        storage_key=storage_key,
        mime_type=metadata["mime_type"],
        byte_size=image.getbuffer().nbytes,
        checksum_sha256=checksum,
        original_filename=metadata["filename"],
        width_px=width,
        height_px=height,
    )
    db.session.add(asset)
    db.session.commit()
    return asset


def serialize_asset(asset: ProjectAsset) -> dict:
    return {
        "id": asset.id,
        "name": asset.original_filename,
        "mimeType": asset.mime_type,
        "size": asset.byte_size,
        "checksum": asset.checksum_sha256,
        "width": asset.width_px,
        "height": asset.height_px,
        "src": _asset_src(asset),
        "createdAt": _iso(asset.created_at),
    }


def delete_asset(project: UserProject, asset: ProjectAsset, expected_version: int | None) -> None:
    references = db.session.scalars(
        select(ProjectElement.id).where(ProjectElement.asset_id == asset.id).limit(1)
    ).first()
    if references:
        raise ConflictError("Remove this photo from its page before deleting the project asset.")
    revisions = db.session.scalars(
        select(ProjectRevision.document).where(ProjectRevision.project_id == project.id)
    ).all()
    snapshots = db.session.scalars(
        select(ProjectSnapshot.document).where(ProjectSnapshot.project_id == project.id)
    ).all()
    if any(
        item.get("id") == asset.id
        for document in [*revisions, *snapshots]
        for item in (document.get("assets") or [])
    ):
        raise ConflictError("This photo is retained by a saved project revision.")
    _next_version(project, expected_version)
    get_asset_storage().delete(asset.storage_key)
    db.session.delete(asset)
    db.session.commit()


def create_revision(project: UserProject, expected_version: int | None) -> ProjectRevision:
    if not project.document:
        raise ValidationError("Save the project document before creating a revision.")
    if expected_version is not None and expected_version != project.version:
        raise ConflictError("Project changed before the revision was created.", {
            "expectedVersion": expected_version,
            "currentVersion": project.version,
        })
    latest = db.session.scalar(
        select(func.max(ProjectRevision.revision_number)).where(ProjectRevision.project_id == project.id)
    ) or 0
    encoded = json.dumps(project.document, sort_keys=True, separators=(",", ":")).encode()
    revision = ProjectRevision(
        project_id=project.id,
        revision_number=latest + 1,
        document_version=project.version,
        document=copy.deepcopy(project.document),
        checksum_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    db.session.add(revision)
    db.session.commit()
    return revision


def serialize_revision(revision: ProjectRevision) -> dict:
    return {
        "id": revision.id,
        "revisionNumber": revision.revision_number,
        "documentVersion": revision.document_version,
        "checksum": revision.checksum_sha256,
        "createdAt": _iso(revision.immutable_at),
        "document": copy.deepcopy(revision.document),
    }


def restore_revision(project: UserProject, revision: ProjectRevision, expected_version: int | None) -> UserProject:
    if revision.project_id != project.id:
        raise ValidationError("Revision does not belong to this project.", {"revisionId": "not_found"})
    document = copy.deepcopy(revision.document)
    return update_project(project, {"document": document}, expected_version)
