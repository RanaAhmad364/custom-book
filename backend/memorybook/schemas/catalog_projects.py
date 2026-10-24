from __future__ import annotations

from decimal import Decimal, InvalidOperation
from math import isfinite

from memorybook.errors import ValidationError

MAX_PROJECT_DOCUMENT_BYTES = 1_500_000


def _validate_elements(elements: object) -> None:
    if not isinstance(elements, list) or len(elements) > 200:
        raise ValidationError("Page elements must be a list of at most 200 items.", {"elements": "invalid"})
    for element in elements:
        if not isinstance(element, dict):
            raise ValidationError("Page elements must be JSON objects.", {"elements": "invalid"})
        if not isinstance(element.get("id"), str) or not element["id"] or len(element["id"]) > 36:
            raise ValidationError("Each page element needs a valid ID.", {"elements": "invalid"})
        if element.get("type") not in {"text", "image", "shape"}:
            raise ValidationError("Page element type is invalid.", {"elements": "invalid"})
        for field in ("x", "y", "width", "height"):
            value = element.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValidationError(f"Element {field} must be a finite normalized number.", {field: "invalid"})
        if not -1 <= element["x"] <= 2 or not -1 <= element["y"] <= 2:
            raise ValidationError("Element position is outside the supported page coordinate range.", {"position": "out_of_range"})
        if not 0 < element["width"] <= 2 or not 0 < element["height"] <= 2:
            raise ValidationError("Element dimensions are outside the supported normalized range.", {"dimensions": "out_of_range"})
        source = element.get("src")
        if isinstance(source, str) and source.startswith("data:"):
            raise ValidationError("Image data must be uploaded as a project asset.", {"assets": "upload_required"})


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationError(f"{field} must be a positive integer.", {field: "invalid"})
    return value


class ProjectCreateSchema:
    @staticmethod
    def load(data: object) -> dict:
        if not isinstance(data, dict):
            raise ValidationError("A JSON object is required.")
        title = data.get("title")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
            raise ValidationError("Title must contain 1 to 200 characters.", {"title": "invalid"})
        page_count = data.get("pageCount", 0)
        if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 0 or page_count > 500:
            raise ValidationError("Page count must be between 0 and 500.", {"pageCount": "invalid"})
        document = data.get("document")
        if document is not None:
            document = ProjectDocumentSchema.load(document)
        return {
            "title": title.strip(),
            "product_id": _optional_id(data.get("productId"), "productId"),
            "template_id": _optional_id(data.get("templateId"), "templateId"),
            "page_count": page_count,
            "document": document,
        }


def _optional_id(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 36:
        raise ValidationError(f"{field} is invalid.", {field: "invalid"})
    return value.strip()


class ProjectDocumentSchema:
    @staticmethod
    def load(value: object) -> dict:
        if not isinstance(value, dict):
            raise ValidationError("Project document must be a JSON object.", {"document": "invalid"})
        import json

        try:
            encoded = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
        except (TypeError, ValueError) as failure:
            raise ValidationError("Project document must contain valid JSON values.", {"document": "invalid"}) from failure
        if len(encoded) > MAX_PROJECT_DOCUMENT_BYTES:
            raise ValidationError("Project document is too large.", {"document": "too_large"})
        if value.get("schemaVersion") != 1:
            raise ValidationError("Unsupported project document version.", {"schemaVersion": "unsupported"})
        metadata = value.get("metadata")
        book = value.get("book")
        pages = value.get("pages")
        page_order = value.get("pageOrder")
        assets = value.get("assets", [])
        if not isinstance(metadata, dict) or not isinstance(metadata.get("title"), str) or not metadata["title"].strip():
            raise ValidationError("Project document metadata needs a title.", {"metadata": "invalid"})
        if len(metadata["title"].strip()) > 200:
            raise ValidationError("Project title must be 200 characters or fewer.", {"title": "too_long"})
        if metadata.get("id") is not None and (
            not isinstance(metadata["id"], str) or not metadata["id"] or len(metadata["id"]) > 36
        ):
            raise ValidationError("Project document ID is invalid.", {"metadata": "invalid"})
        if not isinstance(book, dict):
            raise ValidationError("Project document book details are invalid.", {"book": "invalid"})
        page_count = book.get("pageCount", 0)
        if isinstance(page_count, bool) or not isinstance(page_count, int) or not 0 <= page_count <= 500:
            raise ValidationError("Book page count must be between 0 and 500.", {"pageCount": "invalid"})
        if not isinstance(pages, list) or len(pages) > 500:
            raise ValidationError("Project pages must be a list of at most 500 pages.", {"pages": "invalid"})
        if (
            not isinstance(page_order, list)
            or any(not isinstance(page_id, str) or not page_id for page_id in page_order)
            or len(page_order) != len(pages)
            or len(set(page_order)) != len(page_order)
        ):
            raise ValidationError("Page order must contain each page ID exactly once.", {"pageOrder": "invalid"})
        page_ids = set()
        for page in pages:
            if not isinstance(page, dict) or not isinstance(page.get("id"), str) or not page["id"] or len(page["id"]) > 36:
                raise ValidationError("Each project page needs a valid ID.", {"pages": "invalid"})
            page_type = page.get("type", "page")
            label = page.get("label", "")
            layout = page.get("layout")
            background = page.get("background")
            if not isinstance(page_type, str) or len(page_type) > 30:
                raise ValidationError("Project page type is invalid.", {"pages": "invalid"})
            if not isinstance(label, str) or len(label) > 120:
                raise ValidationError("Project page label is invalid.", {"pages": "invalid"})
            if layout is not None and (not isinstance(layout, str) or len(layout) > 100):
                raise ValidationError("Project page layout is invalid.", {"pages": "invalid"})
            if background is not None and not isinstance(background, dict):
                raise ValidationError("Project page background must be a JSON object.", {"pages": "invalid"})
            page_ids.add(page["id"])
            _validate_elements(page.get("elements", []))
        if set(page_order) != page_ids:
            raise ValidationError("Page order does not match the project pages.", {"pageOrder": "invalid"})
        if not isinstance(assets, list) or len(assets) > 500:
            raise ValidationError("Project assets must be a list of at most 500 items.", {"assets": "invalid"})
        asset_ids = []
        for asset in assets:
            if not isinstance(asset, dict) or not isinstance(asset.get("id"), str) or not asset["id"] or len(asset["id"]) > 36:
                raise ValidationError("Each project asset needs a valid ID.", {"assets": "invalid"})
            asset_ids.append(asset["id"])
        if len(set(asset_ids)) != len(asset_ids):
            raise ValidationError("Project asset IDs must be unique.", {"assets": "invalid"})
        cover = value.get("cover", {})
        if not isinstance(cover, dict) or (cover.get("design") is not None and not isinstance(cover.get("design"), dict)):
            raise ValidationError("Project cover settings are invalid.", {"cover": "invalid"})
        return value


class ProjectUpdateSchema:
    @staticmethod
    def load(data: object) -> dict:
        if not isinstance(data, dict):
            raise ValidationError("A JSON object is required.")
        result = {}
        if "title" in data:
            title = data["title"]
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
                raise ValidationError("Title must contain 1 to 200 characters.", {"title": "invalid"})
            result["title"] = title.strip()
        if "status" in data:
            status = data["status"]
            if status not in {"draft", "in_progress", "completed"}:
                raise ValidationError("Project status is invalid.", {"status": "invalid"})
            result["status"] = status
        if "pageCount" in data:
            result["page_count"] = _positive_integer(data["pageCount"], "pageCount")
            if result["page_count"] > 500:
                raise ValidationError("Page count must be 500 or less.", {"pageCount": "out_of_range"})
        if "document" in data:
            result["document"] = ProjectDocumentSchema.load(data["document"])
        if not result:
            raise ValidationError("Provide at least one project field to update.")
        return result


class ProjectPageSchema:
    @staticmethod
    def load(data: object) -> dict:
        if not isinstance(data, dict):
            raise ValidationError("A page JSON object is required.")
        page_id = _optional_id(data.get("id"), "id")
        if not page_id:
            raise ValidationError("Page ID is required.", {"id": "required"})
        page_number = _positive_integer(data.get("pageNumber"), "pageNumber")
        label = data.get("label", f"Page {page_number}")
        page_type = data.get("type", "page")
        layout = data.get("layout")
        background = data.get("background")
        elements = data.get("elements", [])
        if not isinstance(label, str) or len(label) > 120:
            raise ValidationError("Page label must be 120 characters or fewer.", {"label": "invalid"})
        if not isinstance(page_type, str) or len(page_type) > 30:
            raise ValidationError("Page type is invalid.", {"type": "invalid"})
        if page_type not in {"cover", "page", "interior"}:
            raise ValidationError("Page type is unsupported.", {"type": "invalid"})
        if page_number > 500:
            raise ValidationError("Page number must be 500 or less.", {"pageNumber": "out_of_range"})
        if layout is not None and (not isinstance(layout, str) or len(layout) > 100):
            raise ValidationError("Page layout is invalid.", {"layout": "invalid"})
        if background is not None and not isinstance(background, dict):
            raise ValidationError("Page background must be a JSON object.", {"background": "invalid"})
        _validate_elements(elements)
        return {
            "id": page_id,
            "page_number": page_number,
            "page_type": page_type,
            "label": label.strip(),
            "layout": layout,
            "background": background,
            "elements": elements,
        }


class AssetMetadataSchema:
    ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
    MAX_BYTES = 15 * 1024 * 1024

    @classmethod
    def load(cls, filename: object, mime_type: object, byte_size: object) -> dict:
        if not isinstance(filename, str) or not filename.strip() or len(filename) > 255:
            raise ValidationError("Asset filename is required and must be 255 characters or fewer.", {"filename": "invalid"})
        if mime_type not in cls.ALLOWED_TYPES:
            raise ValidationError("Unsupported image type.", {"mimeType": "unsupported"})
        if isinstance(byte_size, bool) or not isinstance(byte_size, int) or not 0 < byte_size <= cls.MAX_BYTES:
            raise ValidationError("Image size must be between 1 byte and 15 MB.", {"size": "invalid"})
        return {"filename": filename.strip(), "mime_type": mime_type, "byte_size": byte_size}


class CatalogQuerySchema:
    ALLOWED_SORTS = {"featured", "title", "price-low", "price-high", "newest", "pages"}

    @staticmethod
    def page_args(args) -> tuple[int, int]:
        try:
            page = int(args.get("page", "1"))
            per_page = int(args.get("perPage", "24"))
        except (TypeError, ValueError) as failure:
            raise ValidationError("Pagination values must be integers.", {"pagination": "invalid"}) from failure
        if page < 1 or per_page < 1 or per_page > 100:
            raise ValidationError("Page must be positive and perPage must be between 1 and 100.", {"pagination": "out_of_range"})
        return page, per_page

    @classmethod
    def load(cls, args) -> dict:
        page, per_page = cls.page_args(args)
        sort = args.get("sort", "featured")
        if sort not in cls.ALLOWED_SORTS:
            raise ValidationError("Unsupported sort option.", {"sort": "invalid"})
        result = {
            "page": page,
            "per_page": per_page,
            "search": args.get("search", "").strip()[:120],
            "category": args.get("category", "").strip(),
            "collection": args.get("collection", "").strip(),
            "occasion": args.get("occasion", "").strip(),
            "style": args.get("style", "").strip(),
            "book_type": args.get("bookType", "").strip(),
            "sort": sort,
        }
        for query_name, key in (("minPrice", "min_price"), ("maxPrice", "max_price")):
            raw = args.get(query_name)
            if raw is not None and raw != "":
                try:
                    number = Decimal(raw)
                except InvalidOperation as failure:
                    raise ValidationError(f"{query_name} must be a number.", {query_name: "invalid"}) from failure
                if not number.is_finite() or number < 0:
                    raise ValidationError(f"{query_name} cannot be negative.", {query_name: "invalid"})
                result[key] = number
            else:
                result[key] = None
        result["featured"] = None
        if args.get("featured") is not None:
            if args["featured"].lower() not in {"true", "false"}:
                raise ValidationError("featured must be true or false.", {"featured": "invalid"})
            result["featured"] = args["featured"].lower() == "true"
        result["page_count"] = args.get("pageCount", "").strip()
        if result["page_count"]:
            if result["page_count"] == "49+":
                result["page_count_min"] = 49
                result["page_count_max"] = None
            else:
                try:
                    minimum, maximum = (int(part) for part in result["page_count"].split("-", 1))
                except (ValueError, TypeError) as failure:
                    raise ValidationError("pageCount must use a minimum-maximum range.", {"pageCount": "invalid"}) from failure
                if minimum < 1 or maximum < minimum:
                    raise ValidationError("pageCount range is invalid.", {"pageCount": "invalid"})
                result["page_count_min"] = minimum
                result["page_count_max"] = maximum
        else:
            result["page_count_min"] = None
            result["page_count_max"] = None
        return result
