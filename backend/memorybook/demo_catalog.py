from __future__ import annotations

import hashlib
import secrets
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from urllib.parse import quote, urlsplit
from uuid import uuid4

from flask import current_app
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from memorybook.extensions import db
from memorybook.integrations.asset_storage import get_asset_storage
from memorybook.models import (
    BookCategory,
    BookCollection,
    BookProduct,
    BookSize,
    BookTemplate,
    BookVariant,
    CoverType,
    PagePricing,
    PaperType,
    ProjectAsset,
    PricingTier,
    Role,
    ShippingRate,
    User,
    UserProject,
    UserRole,
)
from memorybook.services import admin
from memorybook.services.catalog_projects import create_project

DATASET_VERSION = "module-8a-v1"
CURRENCY = "PKR"
ASSET_OWNER_ID = "demo-catalog-seed"
DEMO_CUSTOMERS = (
    "demo.customer.1@memorybook.local",
    "demo.customer.2@memorybook.local",
    "demo.customer.3@memorybook.local",
)

CATEGORIES = (
    {
        "name": "Family & Memories",
        "slug": "demo-family-memories",
        "description": "A thoughtful home for family histories, traditions, and the everyday moments worth keeping.",
        "style": "Editorial",
        "color": ("#dfe8df", "#355849", "#c18d65"),
    },
    {
        "name": "Travel & Adventures",
        "slug": "demo-travel-adventures",
        "description": "Travel journals for the places, people, and small discoveries that stay with you.",
        "style": "Modern",
        "color": ("#e6e8d5", "#3a655d", "#cf9b69"),
    },
    {
        "name": "Weddings & Celebrations",
        "slug": "demo-weddings-celebrations",
        "description": "Elegant keepsakes for the celebrations and milestones shared with the people you love.",
        "style": "Romantic",
        "color": ("#efe1df", "#684c50", "#bf967e"),
    },
    {
        "name": "Baby & Childhood",
        "slug": "demo-baby-childhood",
        "description": "Gentle, personal books for first years, growing families, and childhood adventures.",
        "style": "Classic",
        "color": ("#e5e8df", "#52706a", "#d0a47c"),
    },
)

COLLECTIONS = (
    ("Family Heritage", "demo-family-heritage", 0, "Stories, recipes, and family traditions passed from one generation to the next."),
    ("Everyday Moments", "demo-everyday-moments", 0, "A home for ordinary days that became favorite memories."),
    ("Travel Diaries", "demo-travel-diaries", 1, "A collected journal of faraway places and the journey between them."),
    ("Wedding Memories", "demo-wedding-memories", 2, "A refined collection for the ceremony, celebration, and all the details in between."),
    ("Baby's First Year", "demo-babys-first-year", 3, "A gentle record of first smiles, first steps, and the people who were there."),
    ("Birthday Celebrations", "demo-birthday-celebrations", 2, "A joyful keepsake for milestone birthdays and the people gathered around."),
)

BOOKS = (
    ("Our Family Story", "our-family-story", 0, 0, "BASIC", "Editorial", "Family", 24, 80, "A living portrait of family traditions, familiar places, and the people who make a house a home."),
    ("The Travel Journal", "the-travel-journal", 1, 2, "PREMIUM", "Modern", "Travel", 24, 80, "A considered travel journal for maps, quiet mornings, local color, and the road home."),
    ("Wedding Memories", "wedding-memories", 2, 3, "PREMIUM", "Romantic", "Wedding", 24, 80, "A graceful keepsake of the vows, the gathering, and every thoughtful detail of the day."),
    ("Baby's First Year", "babys-first-year", 3, 4, "BASIC", "Classic", "Baby", 24, 80, "A soft, timeless record of new beginnings and a first year that moved too quickly."),
    ("Birthday Celebration Book", "birthday-celebration-book", 2, 5, "LIGHT", "Playful", "Birthday", 24, 80, "A bright collection of candles, familiar faces, shared laughter, and birthday wishes."),
    ("Our Love Story", "our-love-story", 2, 3, "PREMIUM", "Romantic", "Anniversary", 24, 80, "A personal anniversary book for the places, rituals, and little moments that became yours."),
    ("Adventure Begins", "adventure-begins", 1, 2, "LIGHT", "Editorial", "Travel", 24, 80, "A light, portable album for spontaneous weekends and the first chapter of a new adventure."),
    ("Everyday Moments", "everyday-moments-book", 0, 1, "LIGHT", "Minimal", "Family", 24, 80, "A simple, modern album that gives ordinary days the space they deserve."),
    ("Family Recipe Memories", "family-recipe-memories", 0, 0, "BASIC", "Classic", "Family", 24, 80, "A family recipe book pairing treasured dishes with the stories and people behind them."),
    ("Graduation Memories", "graduation-memories", 2, 5, "BASIC", "Modern", "Birthday", 24, 80, "A polished keepsake for the hard work, proud faces, and new beginnings of graduation."),
)

TIERS = (
    ("DEMO-LIGHT", "Demo Light", Decimal("1200.00"), Decimal("0.00")),
    ("DEMO-BASIC", "Demo Basic", Decimal("2400.00"), Decimal("65.00")),
    ("DEMO-PREMIUM", "Demo Premium", Decimal("4200.00"), Decimal("120.00")),
)


@dataclass(frozen=True)
class DemoAssetOwner:
    id: str = ASSET_OWNER_ID


def _artwork(title: str, palette: tuple[str, str, str], label: str) -> BytesIO:
    base, dark, accent = palette
    image = Image.new("RGB", (900, 1100), base)
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("arial.ttf", 57)
        small_font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        title_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    draw.ellipse((120, 130, 780, 790), fill=accent)
    draw.ellipse((235, 235, 665, 665), fill=dark)
    draw.arc((175, 205, 720, 750), 195, 345, fill=base, width=18)
    draw.line((0, 830, 900, 830), fill=dark, width=3)
    draw.text((72, 65), "MEMORYBOOK  /  DEMO", fill=dark, font=small_font)
    lines = textwrap.wrap(title, width=22)
    y = 875
    for line in lines[:3]:
        draw.text((72, y), line, fill=dark, font=title_font)
        y += 66
    draw.text((74, 1050), label.upper(), fill=dark, font=small_font)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def _upload_artwork(title: str, slug: str, palette: tuple[str, str, str], label: str) -> dict:
    artwork = _artwork(title, palette, label)
    file = FileStorage(
        stream=artwork,
        filename=f"{slug}.png",
        content_type="image/png",
    )
    return admin.upload_catalog_asset(file, DemoAssetOwner())


def _find_category(data: dict) -> BookCategory | None:
    found = db.session.scalar(
        select(BookCategory).where(
            BookCategory.slug == data["slug"],
            BookCategory.deleted_at.is_(None),
        )
    )
    if found is not None:
        return found
    equivalents = {
        "demo-family-memories": ("family & memories", "family", "memories"),
        "demo-travel-adventures": ("travel & adventures", "travel"),
        "demo-weddings-celebrations": ("weddings & celebrations", "wedding"),
        "demo-baby-childhood": ("baby & childhood", "baby", "childhood"),
    }[data["slug"]]
    return db.session.scalar(
        select(BookCategory).where(
            db.func.lower(BookCategory.name).in_(equivalents),
            BookCategory.deleted_at.is_(None),
        ).order_by(BookCategory.sort_order, BookCategory.id)
    )


def _ensure_categories(summary: dict) -> list[BookCategory]:
    categories = []
    for data in CATEGORIES:
        category = _find_category(data)
        if category is None:
            category = BookCategory(
                name=data["name"],
                slug=data["slug"],
                description=data["description"],
                style=data["style"],
                is_active=True,
            )
            db.session.add(category)
            db.session.flush()
            summary["categories"]["created"] += 1
        else:
            summary["categories"]["reused"] += 1
        if not category.is_active:
            raise ValueError(f"Category '{category.name}' is inactive; it was not changed.")
        if not category.hero_asset_key:
            asset = _upload_artwork(data["name"], data["slug"], data["color"], "Category")
            category.hero_asset_key = asset["assetKey"]
            db.session.flush()
        categories.append(category)
    db.session.commit()
    return categories


def _ensure_collections(categories: list[BookCategory], summary: dict) -> list[BookCollection]:
    collections = []
    for name, slug, category_index, description in COLLECTIONS:
        category = categories[category_index]
        collection = db.session.scalar(
            select(BookCollection).where(
                BookCollection.slug == slug,
                BookCollection.deleted_at.is_(None),
            )
        )
        if collection is None:
            collection = db.session.scalar(
                select(BookCollection).where(
                    BookCollection.name == name,
                    BookCollection.category_id == category.id,
                    BookCollection.deleted_at.is_(None),
                )
            )
        if collection is None:
            asset = _upload_artwork(
                name,
                slug,
                CATEGORIES[category_index]["color"],
                "Collection",
            )
            collection = BookCollection(
                name=name,
                slug=slug,
                description=description,
                category_id=category.id,
                hero_asset_key=asset["assetKey"],
                eyebrow="DEMO COLLECTION",
                recommended_layouts=["editorial", "photo-text"],
                related_categories=[category.slug],
                is_active=True,
            )
            db.session.add(collection)
            db.session.flush()
            summary["collections"]["created"] += 1
        else:
            if collection.category_id != category.id:
                raise ValueError(
                    f"Collection '{collection.name}' belongs to a different category; it was not changed."
                )
            if not collection.is_active:
                raise ValueError(f"Collection '{collection.name}' is inactive; it was not changed.")
            if not collection.hero_asset_key:
                asset = _upload_artwork(
                    name,
                    slug,
                    CATEGORIES[category_index]["color"],
                    "Collection",
                )
                collection.hero_asset_key = asset["assetKey"]
            summary["collections"]["reused"] += 1
        collections.append(collection)
    db.session.commit()
    return collections


def _ensure_pricing(summary: dict) -> dict:
    sizes = {}
    for code, name, width, height in (
        ("DEMO_8_SQUARE", "Demo 8 × 8 in", Decimal("203.20"), Decimal("203.20")),
        ("DEMO_10_SQUARE", "Demo 10 × 10 in", Decimal("254.00"), Decimal("254.00")),
    ):
        size = db.session.scalar(select(BookSize).where(BookSize.code == code))
        if size is None:
            result = admin.create_pricing("size", {
                "code": code, "name": name, "widthMm": str(width), "heightMm": str(height),
                "active": True,
            })
            size = db.session.get(BookSize, result["id"])
            summary["pricing"]["created"] += 1
        else:
            summary["pricing"]["reused"] += 1
        if not size.is_active or size.width_mm != width or size.height_mm != height:
            raise ValueError(f"Pricing size '{code}' is incompatible and was not changed.")
        sizes["LIGHT" if code == "DEMO_8_SQUARE" else "STANDARD"] = size

    covers = {}
    for name, description in (
        ("Demo Hardcover", "Sample case-bound cover for the development catalog."),
        ("Demo Softcover", "Sample flexible cover for the development catalog."),
    ):
        cover = db.session.scalar(select(CoverType).where(CoverType.name == name))
        if cover is None:
            result = admin.create_pricing("cover", {
                "name": name, "description": description, "active": True,
            })
            cover = db.session.get(CoverType, result["id"])
            summary["pricing"]["created"] += 1
        else:
            summary["pricing"]["reused"] += 1
        if not cover.is_active:
            raise ValueError(f"Cover type '{name}' is inactive and was not changed.")
        covers[name] = cover

    papers = {}
    for name, gsm, description in (
        ("Demo Matte", 170, "Uncoated matte paper sample used by the demo books."),
        ("Demo Satin", 200, "Smooth satin paper sample used by the demo books."),
    ):
        paper = db.session.scalar(select(PaperType).where(PaperType.name == name))
        if paper is None:
            result = admin.create_pricing("paper", {
                "name": name, "weightGsm": gsm, "description": description, "active": True,
            })
            paper = db.session.get(PaperType, result["id"])
            summary["pricing"]["created"] += 1
        else:
            summary["pricing"]["reused"] += 1
        if not paper.is_active:
            raise ValueError(f"Paper type '{name}' is inactive and was not changed.")
        papers[name] = paper

    tiers = {}
    for code, name, base_price, page_rate in TIERS:
        tier = db.session.scalar(select(PricingTier).where(PricingTier.code == code))
        if tier is None:
            result = admin.create_pricing("tier", {
                "code": code,
                "name": name,
                "description": f"Development sample {name.lower()} print tier; values are illustrative.",
                "basePrice": str(base_price),
                "currency": CURRENCY,
                "active": True,
            })
            tier = db.session.get(PricingTier, result["id"])
            summary["pricing"]["created"] += 1
        else:
            summary["pricing"]["reused"] += 1
        if not tier.is_active or tier.currency.upper() != CURRENCY or tier.base_price != base_price:
            raise ValueError(f"Pricing tier '{code}' is incompatible and was not changed.")
        band = db.session.scalar(
            select(PagePricing).where(
                PagePricing.tier_id == tier.id,
                PagePricing.minimum_pages == 24,
                PagePricing.maximum_pages == 80,
            )
        )
        if band is None:
            result = admin.create_pricing("pagePricing", {
                "tierId": tier.id,
                "minimumPages": 24,
                "maximumPages": 80,
                "pricePerPage": str(page_rate),
                "active": True,
            })
            band = db.session.get(PagePricing, result["id"])
            summary["pricing"]["created"] += 1
        else:
            summary["pricing"]["reused"] += 1
        if band.price_per_page != page_rate:
            raise ValueError(f"Page pricing for '{code}' differs from the demo values; it was not changed.")
        tiers[code] = tier

    shipping = db.session.scalar(
        select(ShippingRate).where(
            ShippingRate.country_code == "PK",
            ShippingRate.region_code.is_(None),
            ShippingRate.service_code == "DEMO-HOME",
        )
    )
    if shipping is None:
        result = admin.create_pricing("shipping", {
            "countryCode": "PK",
            "serviceCode": "DEMO-HOME",
            "serviceName": "Demo home delivery",
            "price": "350.00",
            "currency": CURRENCY,
            "estimatedDaysMin": 3,
            "estimatedDaysMax": 7,
            "active": True,
        })
        shipping = db.session.get(ShippingRate, result["id"])
        summary["pricing"]["created"] += 1
    else:
        summary["pricing"]["reused"] += 1
    if (
        not shipping.is_active
        or shipping.currency.upper() != CURRENCY
        or shipping.price != Decimal("350.00")
        or shipping.estimated_days_max != 7
    ):
        raise ValueError("Demo home delivery configuration is incompatible and was not changed.")
    return {"sizes": sizes, "covers": covers, "papers": papers, "tiers": tiers, "shipping": shipping}


def _product_metadata(product_type: str, size: BookSize, covers: dict, papers: dict, tiers: dict, artwork_keys: list[str]) -> dict:
    return {
        "datasetKey": DATASET_VERSION,
        "pageCountOptions": [24, 32, 40, 56, 80],
        "sizeOptions": [size.id],
        "coverOptions": [cover.id for cover in covers.values()],
        "paperOptions": [paper.id for paper in papers.values()],
        "printingTiers": list(tiers),
        "productionDays": 7 if product_type == "LIGHT" else 10,
        "pdfPrice": "850.00",
        "previewImageKeys": artwork_keys,
        "dimensions": {
            "widthMm": str(size.width_mm),
            "heightMm": str(size.height_mm),
        },
    }


def _design_document(product: BookProduct, template: BookTemplate, cover_asset: dict, gallery_asset: dict) -> dict:
    document = admin._new_book_design_document(product, template, 24)
    cover_id = document["pageOrder"][0]
    first_story_id = document["pageOrder"][1]
    second_story_id = document["pageOrder"][2]
    cover_asset_id = str(uuid4())
    gallery_asset_id = str(uuid4())
    document["assets"] = [
        {
            "id": cover_asset_id,
            "assetKey": cover_asset["assetKey"],
            "name": cover_asset["filename"],
            "mimeType": cover_asset["mimeType"],
            "size": cover_asset["size"],
            "checksum": cover_asset["checksum"],
            "width": cover_asset["width"],
            "height": cover_asset["height"],
        },
        {
            "id": gallery_asset_id,
            "assetKey": gallery_asset["assetKey"],
            "name": gallery_asset["filename"],
            "mimeType": gallery_asset["mimeType"],
            "size": gallery_asset["size"],
            "checksum": gallery_asset["checksum"],
            "width": gallery_asset["width"],
            "height": gallery_asset["height"],
        },
    ]
    pages_by_id = {page["id"]: page for page in document["pages"]}
    pages_by_id[cover_id]["layout"] = "cover"
    pages_by_id[cover_id]["elements"] = [
        {
            "id": str(uuid4()), "type": "image", "assetId": cover_asset_id, "name": cover_asset["filename"],
            "fit": "cover", "cropX": 0.5, "cropY": 0.5, "x": 0.08, "y": 0.08, "width": 0.84, "height": 0.84,
        },
        {
            "id": str(uuid4()), "type": "text", "kind": "heading", "text": product.title,
            "fontFamily": "Georgia", "fontSize": 0.055, "fontWeight": "600", "color": "#ffffff",
            "alignment": "center", "x": 0.1, "y": 0.73, "width": 0.8, "height": 0.12,
        },
    ]
    pages_by_id[cover_id]["background"] = {"color": "#355849"}
    pages_by_id[first_story_id]["layout"] = "editorial"
    pages_by_id[first_story_id]["elements"] = [
        {
            "id": str(uuid4()), "type": "image", "assetId": gallery_asset_id, "name": gallery_asset["filename"],
            "fit": "cover", "cropX": 0.5, "cropY": 0.5, "x": 0.08, "y": 0.08, "width": 0.84, "height": 0.58,
        },
        {
            "id": str(uuid4()), "type": "text", "kind": "heading", "text": "The moments between",
            "fontFamily": "Georgia", "fontSize": 0.034, "fontWeight": "600", "color": "#253d34",
            "alignment": "left", "x": 0.08, "y": 0.72, "width": 0.84, "height": 0.08,
        },
        {
            "id": str(uuid4()), "type": "text", "kind": "paragraph",
            "text": "Some of our favorite stories are found in the unplanned details, the familiar voices, and the places we return to.",
            "fontFamily": "DM Sans", "fontSize": 0.021, "fontWeight": "400", "color": "#394a42",
            "alignment": "left", "lineHeight": 1.25, "x": 0.08, "y": 0.82, "width": 0.84, "height": 0.12,
        },
    ]
    pages_by_id[second_story_id]["layout"] = "photo-text"
    pages_by_id[second_story_id]["elements"] = [
        {
            "id": str(uuid4()), "type": "image", "assetId": cover_asset_id, "name": cover_asset["filename"],
            "fit": "cover", "cropX": 0.5, "cropY": 0.5, "x": 0.06, "y": 0.08, "width": 0.52, "height": 0.82,
        },
        {
            "id": str(uuid4()), "type": "text", "kind": "subheading", "text": "A note to remember",
            "fontFamily": "Georgia", "fontSize": 0.028, "fontWeight": "500", "color": "#253d34",
            "alignment": "left", "x": 0.64, "y": 0.28, "width": 0.3, "height": 0.12,
        },
        {
            "id": str(uuid4()), "type": "text", "kind": "paragraph",
            "text": "Keep a few words beside the photograph: where you were, what made you laugh, and why this day still matters.",
            "fontFamily": "DM Sans", "fontSize": 0.02, "fontWeight": "400", "color": "#394a42",
            "alignment": "left", "lineHeight": 1.25, "x": 0.64, "y": 0.44, "width": 0.3, "height": 0.3,
        },
    ]
    document["cover"]["design"]["front"].update({
        "title": product.title,
        "subtitle": "A MEMORYBOOK KEEPSAKE",
        "photoAssetId": cover_asset_id,
    })
    document["cover"]["design"]["back"]["description"] = product.description[:140]
    return document


def _ensure_variants(product: BookProduct, pricing: dict, summary: dict) -> None:
    size_key = "LIGHT" if product.book_type == "LIGHT" else "STANDARD"
    size = pricing["sizes"][size_key]
    for cover in pricing["covers"].values():
        for paper in pricing["papers"].values():
            sku = f"DEMO-{product.slug.removeprefix('demo-')}-{size.code}-{cover.name}-{paper.name}"[:80]
            existing = db.session.scalar(
                select(BookVariant).where(
                    BookVariant.product_id == product.id,
                    BookVariant.size_id == size.id,
                    BookVariant.cover_type_id == cover.id,
                    BookVariant.paper_type_id == paper.id,
                )
            )
            if existing is not None:
                if not existing.is_active or existing.currency.upper() != CURRENCY:
                    raise ValueError(f"Variant for '{product.title}' is inactive or uses a different currency.")
                summary["variants"]["reused"] += 1
                continue
            price = {
                "LIGHT": Decimal("1450.00"),
                "BASIC": Decimal("2650.00"),
                "PREMIUM": Decimal("4350.00"),
            }[product.book_type or "BASIC"]
            if paper.name == "Demo Satin":
                price += Decimal("350.00")
            if cover.name == "Demo Softcover":
                price -= Decimal("450.00")
            admin.create_variant({
                "productId": product.id,
                "sizeId": size.id,
                "coverTypeId": cover.id,
                "paperTypeId": paper.id,
                "sku": sku,
                "basePrice": str(price),
                "currency": CURRENCY,
            })
            summary["variants"]["created"] += 1


def _ensure_template(
    product: BookProduct,
    category: BookCategory,
    cover_asset: dict,
    gallery_asset: dict,
    summary: dict,
) -> BookTemplate | None:
    slug = f"{product.slug}-master-design"
    template = db.session.scalar(
        select(BookTemplate).where(BookTemplate.slug == slug, BookTemplate.deleted_at.is_(None))
    )
    if template is None:
        template = BookTemplate(
            product_id=product.id,
            category_id=category.id,
            name=f"{product.title} — Demo Master Design",
            slug=slug,
            description=f"Original development-only master design for {product.title}.",
            version=1,
            is_active=False,
        )
        db.session.add(template)
        db.session.flush()
        summary["designs"]["created"] += 1
    elif template.product_id != product.id or template.category_id != category.id:
        raise ValueError(f"Master design slug for '{product.title}' is already used by another record.")
    else:
        summary["designs"]["reused"] += 1
    if template.design_document is None:
        admin.save_book_design(
            product.id,
            _design_document(product, template, cover_asset, gallery_asset),
            template.version,
        )
        template = db.session.get(BookTemplate, template.id)
    if template.published_design_document is None:
        admin.publish_book_design(product.id, template.version)
        template = db.session.get(BookTemplate, template.id)
    if template.published_design_document is None or not template.is_active:
        raise ValueError(f"Master design for '{product.title}' did not pass publication validation.")
    return template


def _create_or_reuse_product(
    book_data: tuple,
    category: BookCategory,
    collection: BookCollection,
    pricing: dict,
    summary: dict,
) -> tuple[BookProduct | None, dict | None, dict | None]:
    title, slug_suffix, category_index, collection_index, book_type, style, occasion, min_pages, max_pages, description = book_data
    slug = f"demo-{slug_suffix}"
    product = db.session.scalar(select(BookProduct).where(BookProduct.slug == slug))
    if product is not None:
        if (product.admin_metadata or {}).get("datasetKey") != DATASET_VERSION:
            summary["products"]["skipped"] += 1
            return None, None, None
        summary["products"]["reused"] += 1
        assets = (product.admin_metadata or {}).get("previewImageKeys", [])
        cover_key = product.cover_asset_key
        gallery_key = assets[1] if len(assets) > 1 else (assets[0] if assets else None)
        if not cover_key or not gallery_key:
            summary["products"]["skipped"] += 1
            return None, None, None
        storage = get_asset_storage()
        cover_asset = {
            "assetKey": cover_key,
            "filename": cover_key.rsplit("/", 1)[-1],
            "mimeType": storage.content_type(cover_key),
            "size": 0,
            "checksum": "",
            "width": 900,
            "height": 1100,
        }
        cover_bytes = storage.download(cover_key)
        cover_asset["size"] = len(cover_bytes)
        cover_asset["checksum"] = hashlib.sha256(cover_bytes).hexdigest()
        gallery_bytes = storage.download(gallery_key)
        gallery_asset = {
            "assetKey": gallery_key,
            "filename": gallery_key.rsplit("/", 1)[-1],
            "mimeType": storage.content_type(gallery_key),
            "size": len(gallery_bytes),
            "checksum": hashlib.sha256(gallery_bytes).hexdigest(),
            "width": 900,
            "height": 1100,
        }
        return product, cover_asset, gallery_asset

    palette = CATEGORIES[category_index]["color"]
    cover_asset = _upload_artwork(title, f"{slug}-cover", palette, "Book cover")
    gallery_asset = _upload_artwork(title, f"{slug}-gallery", palette, "Interior image")
    size = pricing["sizes"]["LIGHT" if book_type == "LIGHT" else "STANDARD"]
    metadata = _product_metadata(
        book_type,
        size,
        pricing["covers"],
        pricing["papers"],
        pricing["tiers"],
        [cover_asset["assetKey"], gallery_asset["assetKey"]],
    )
    start_price = {
        "LIGHT": Decimal("4200.00"),
        "BASIC": Decimal("5900.00"),
        "PREMIUM": Decimal("7900.00"),
    }[book_type]
    product_response = admin.save_product({
        "title": title,
        "slug": slug,
        "description": description,
        "categoryId": category.id,
        "collectionId": collection.id,
        "style": style,
        "occasion": occasion,
        "bookType": book_type,
        "pageCountMin": min_pages,
        "pageCountMax": max_pages,
        "startingPrice": str(start_price),
        "currency": CURRENCY,
        "coverAssetKey": cover_asset["assetKey"],
        "featured": True,
        "adminMetadata": metadata,
    })
    product = db.session.get(BookProduct, product_response["id"])
    summary["products"]["created"] += 1
    return product, cover_asset, gallery_asset


def _ensure_customer(email: str, index: int) -> User:
    user = db.session.scalar(select(User).where(User.email == email))
    if user is not None:
        if user.deleted_at is not None:
            raise ValueError(f"Reserved demo account {email} is soft-deleted; it was not modified.")
        return user
    role = db.session.scalar(select(Role).where(Role.name == "customer"))
    if role is None:
        role = Role(name="customer", description="MemoryBook customer", is_system=True)
        db.session.add(role)
        db.session.flush()
    user = User(
        email=email,
        full_name=f"MemoryBook Demo Customer {index}",
        password_hash=generate_password_hash(secrets.token_urlsafe(48)),
        is_active=True,
        email_verified_at=datetime.now(UTC),
    )
    db.session.add(user)
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.commit()
    return user


def _ensure_customer_projects(products: list[BookProduct], templates: dict[str, BookTemplate], summary: dict) -> None:
    selected = ("demo-our-family-story", "demo-the-travel-journal", "demo-wedding-memories")
    for index, slug in enumerate(selected, start=1):
        email = DEMO_CUSTOMERS[index - 1]
        owner = _ensure_customer(email, index)
        product = next((item for item in products if item.slug == slug), None)
        template = templates.get(slug)
        if product is None or template is None or not product.is_active or not template.is_active:
            summary["projects"]["skipped"] += 1
            continue
        title = f"Demo draft: {product.title}"
        project = db.session.scalar(
            select(UserProject).where(
                UserProject.user_id == owner.id,
                UserProject.product_id == product.id,
                UserProject.title == title,
                UserProject.status != "deleted",
            )
        )
        if project is not None:
            if project.template_id != template.id:
                raise ValueError(f"Demo draft for {email} references a different design.")
            summary["projects"]["reused"] += 1
        else:
            project = create_project(owner, {
                "title": title,
                "product_id": product.id,
                "template_id": template.id,
                "page_count": product.page_count_min or 24,
                "document": None,
            })
            summary["projects"]["created"] += 1
        if (
            project.user_id != owner.id
            or project.product_id != product.id
            or project.template_id != template.id
            or not project.document
            or project.document == template.published_design_document
        ):
            raise ValueError(f"Demo draft for {email} is not an independent copy of its published design.")
        project_assets = db.session.scalars(
            select(ProjectAsset).where(ProjectAsset.project_id == project.id)
        ).all()
        if not project_assets or any(not asset.storage_key.startswith(f"projects/{owner.id}/{project.id}/") for asset in project_assets):
            raise ValueError(f"Demo draft assets for {email} are not owned by that customer project.")


def _verify_seed(
    categories: list[BookCategory],
    collections: list[BookCollection],
    products: list[BookProduct],
    templates: dict[str, BookTemplate],
    summary: dict,
) -> None:
    storage = get_asset_storage()
    asset_keys = [
        item.hero_asset_key
        for item in [*categories, *collections]
        if item.hero_asset_key and item.hero_asset_key.startswith("catalog/")
    ]
    for product in products:
        if not product.is_active:
            raise ValueError(f"Product '{product.slug}' is not published.")
        if not product.cover_asset_key or not storage.download(product.cover_asset_key):
            raise ValueError(f"Product cover for '{product.slug}' could not be read from configured storage.")
        asset_keys.append(product.cover_asset_key)
        asset_keys.extend((product.admin_metadata or {}).get("previewImageKeys", []))
        variants = db.session.scalars(
            select(BookVariant).where(BookVariant.product_id == product.id, BookVariant.is_active.is_(True))
        ).all()
        if len(variants) < 4 or any(variant.currency.upper() != CURRENCY for variant in variants):
            raise ValueError(f"Product '{product.slug}' has incomplete or inconsistent variants.")
        template = templates.get(product.slug)
        if template is None or not template.is_active or not template.published_design_document:
            raise ValueError(f"Product '{product.slug}' has no published master design.")
        design = template.published_design_document
        if len(design.get("pages", [])) < 4:
            raise ValueError(f"Master design for '{product.slug}' has fewer than four pages.")
        for asset in design.get("assets", []):
            if not storage.download(asset["assetKey"]):
                raise ValueError(f"Master design asset for '{product.slug}' could not be read.")
            asset_keys.append(asset["assetKey"])
    client = current_app.test_client()
    for key in set(asset_keys):
        response = client.get(f"/api/v1/assets/public/{quote(key, safe='/')}")
        if response.status_code != 200 or not response.data:
            raise ValueError("A catalog image URL failed its local asset retrieval check.")
    summary["published_books"] = len(products)


def seed_demo_catalog() -> dict:
    summary = {
        "categories": {"created": 0, "reused": 0},
        "collections": {"created": 0, "reused": 0},
        "pricing": {"created": 0, "reused": 0},
        "products": {"created": 0, "reused": 0, "skipped": 0},
        "variants": {"created": 0, "reused": 0},
        "designs": {"created": 0, "reused": 0},
        "projects": {"created": 0, "reused": 0, "skipped": 0},
        "published_books": 0,
    }
    categories = _ensure_categories(summary)
    collections = _ensure_collections(categories, summary)
    pricing = _ensure_pricing(summary)
    products = []
    templates = {}
    for book_data in BOOKS:
        _, _, category_index, collection_index = book_data[:4]
        category = categories[category_index]
        collection = collections[collection_index]
        product, cover_asset, gallery_asset = _create_or_reuse_product(
            book_data,
            category,
            collection,
            pricing,
            summary,
        )
        if product is None:
            continue
        if product.category_id != category.id or product.collection_id != collection.id:
            raise ValueError(f"Product '{product.slug}' has mismatched category or collection relationships.")
        _ensure_variants(product, pricing, summary)
        template = _ensure_template(product, category, cover_asset, gallery_asset, summary)
        templates[product.slug] = template
        if not product.is_active:
            admin.set_product_published(product.id, True)
            product = db.session.get(BookProduct, product.id)
        products.append(product)
    if len(products) != len(BOOKS):
        raise ValueError(
            f"Only {len(products)} of {len(BOOKS)} demo products were safe to seed; conflicting records were skipped."
        )
    _ensure_customer_projects(products, templates, summary)
    _verify_seed(categories, collections, products, templates, summary)
    db.session.commit()
    return summary


def _local_postgres_database(database_uri: str | None) -> bool:
    if not database_uri:
        return False
    parts = urlsplit(database_uri)
    return (
        parts.scheme in {"postgresql", "postgresql+psycopg"}
        and (parts.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}
    )


def preview_demo_catalog() -> dict:
    product_slugs = [f"demo-{book[1]}" for book in BOOKS]
    existing_products = db.session.scalar(
        select(db.func.count(BookProduct.id)).where(BookProduct.slug.in_(product_slugs))
    ) or 0
    categories = [_find_category(item) for item in CATEGORIES]
    existing_categories = sum(category is not None for category in categories)
    existing_collections = 0
    for name, slug, category_index, _description in COLLECTIONS:
        category = categories[category_index]
        if category is None:
            continue
        existing = db.session.scalar(
            select(BookCollection.id).where(
                BookCollection.deleted_at.is_(None),
                (BookCollection.slug == slug)
                | (
                    (BookCollection.name == name)
                    & (BookCollection.category_id == category.id)
                ),
            )
        )
        existing_collections += existing is not None
    return {
        "categories": len(CATEGORIES),
        "existing_categories": existing_categories,
        "collections": len(COLLECTIONS),
        "existing_collections": existing_collections,
        "books": len(BOOKS),
        "existing_books": existing_products,
    }


def seed_environment_error(
    app,
    confirm_local_database: bool,
    *,
    require_confirmation: bool = True,
) -> str | None:
    if app.config.get("TESTING"):
        return None
    if app.config.get("ENVIRONMENT") != "development":
        return "Demo catalog seeding is allowed only in development."
    if not _local_postgres_database(app.config.get("SQLALCHEMY_DATABASE_URI")):
        return "Demo catalog seeding requires a loopback PostgreSQL DATABASE_URL."
    if require_confirmation and not confirm_local_database:
        return "Pass --confirm-local-database only after verifying this is a dedicated, non-production database."
    if app.config.get("ASSET_STORAGE_BACKEND") != "filesystem":
        return "Demo artwork seeding requires the local filesystem asset storage backend."
    return None


def seed_schema_error(app) -> str | None:
    if app.config.get("TESTING"):
        return None

    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    migration_config = Config()
    migration_config.set_main_option("script_location", app.config["MIGRATIONS_DIRECTORY"])
    expected_heads = set(ScriptDirectory.from_config(migration_config).get_heads())
    with db.engine.connect() as connection:
        current_heads = set(MigrationContext.configure(connection).get_current_heads())
    if current_heads != expected_heads:
        return (
            "The configured database is not at the repository migration head. "
            "Review and apply the pending development migration manually before seeding."
        )
    return None
