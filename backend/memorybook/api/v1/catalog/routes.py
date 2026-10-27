from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import select

from memorybook.errors import ValidationError
from memorybook.extensions import db
from memorybook.models import BookCategory, BookCollection, BookProduct, Favorite
from memorybook.schemas.catalog_projects import CatalogQuerySchema
from memorybook.services.catalog_projects import (
    get_template,
    list_books,
    list_categories,
    list_collections,
    list_templates,
    serialize_book,
    serialize_category,
    serialize_collection,
)
from memorybook.services.pricing import public_plan_catalog

catalog_blueprint = Blueprint("catalog", __name__)


def _page_response(items: list[dict], total: int, page: int, per_page: int):
    return {
        "items": items,
        "pagination": {
            "page": page,
            "perPage": per_page,
            "totalItems": total,
            "totalPages": (total + per_page - 1) // per_page,
        },
    }


@catalog_blueprint.get("/books")
@jwt_required(optional=True)
def books():
    filters = CatalogQuerySchema.load(request.args)
    items, total = list_books(filters, get_jwt_identity())
    return jsonify(_page_response(items, total, filters["page"], filters["per_page"]))


@catalog_blueprint.get("/pricing/tiers")
def pricing_tiers():
    products = db.session.scalars(
        select(BookProduct).where(
            BookProduct.is_active.is_(True),
            BookProduct.deleted_at.is_(None),
        )
    ).all()
    return jsonify({"items": public_plan_catalog(products)})


@catalog_blueprint.get("/books/<string:book_id>")
@jwt_required(optional=True)
def book_details(book_id: str):
    book = db.session.scalar(
        select(BookProduct).join(BookCategory, BookProduct.category_id == BookCategory.id).where(
            (BookProduct.id == book_id) | (BookProduct.slug == book_id),
            BookProduct.is_active.is_(True),
            BookProduct.deleted_at.is_(None),
            BookCategory.is_active.is_(True),
            BookCategory.deleted_at.is_(None),
        )
    )
    if book is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Book was not found."}}), 404
    user_id = get_jwt_identity()
    favorite_ids = set()
    if user_id and db.session.scalar(
        select(Favorite.id).where(Favorite.user_id == user_id, Favorite.book_id == book.id)
    ):
        favorite_ids.add(book.id)
    return jsonify({"book": serialize_book(book, include_gallery=True, favorite_ids=favorite_ids)})


@catalog_blueprint.get("/categories")
def categories():
    return jsonify({"items": list_categories()})


@catalog_blueprint.get("/categories/<string:category_id>")
def category_details(category_id: str):
    category = db.session.scalar(
        select(BookCategory).where(
            (BookCategory.id == category_id) | (BookCategory.slug == category_id),
            BookCategory.is_active.is_(True),
            BookCategory.deleted_at.is_(None),
        )
    )
    if category is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Category was not found."}}), 404
    return jsonify({"category": serialize_category(category)})


@catalog_blueprint.get("/collections")
def collections():
    return jsonify({"items": list_collections()})


@catalog_blueprint.get("/collections/<string:collection_id>")
def collection_details(collection_id: str):
    collection = db.session.scalar(
        select(BookCollection).where(
            (BookCollection.id == collection_id) | (BookCollection.slug == collection_id),
            BookCollection.is_active.is_(True),
            BookCollection.deleted_at.is_(None),
        )
    )
    if collection is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Collection was not found."}}), 404
    return jsonify({"collection": serialize_collection(collection)})


@catalog_blueprint.get("/templates")
def templates():
    page, per_page = CatalogQuerySchema.page_args(request.args)
    search = request.args.get("search", "").strip()[:120]
    category = request.args.get("category", "").strip()
    if len(category) > 140:
        raise ValidationError("Category filter is too long.", {"category": "too_long"})
    items, total = list_templates(page, per_page, search, category)
    return jsonify(_page_response(items, total, page, per_page))


@catalog_blueprint.get("/templates/<string:template_id>")
def template_details(template_id: str):
    template = get_template(template_id)
    if template is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Template was not found."}}), 404
    return jsonify({"template": template})
