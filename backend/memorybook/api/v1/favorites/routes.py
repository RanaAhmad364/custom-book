from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from memorybook.extensions import db
from memorybook.models import BookCategory, BookProduct, Favorite
from memorybook.permissions import active_user_required, get_authenticated_user
from memorybook.services.catalog_projects import serialize_book

favorites_blueprint = Blueprint("favorites", __name__)


def _public_book_query():
    return (
        select(BookProduct)
        .join(BookCategory, BookProduct.category_id == BookCategory.id)
        .where(
            BookProduct.is_active.is_(True),
            BookProduct.deleted_at.is_(None),
            BookCategory.is_active.is_(True),
            BookCategory.deleted_at.is_(None),
        )
    )


@favorites_blueprint.get("")
@active_user_required
def list_favorites():
    user_id = get_authenticated_user().id
    products = db.session.scalars(
        _public_book_query()
        .join(Favorite, Favorite.book_id == BookProduct.id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.created_at.desc())
    ).all()
    favorite_ids = {book.id for book in products}
    return jsonify({
        "items": [serialize_book(book, favorite_ids=favorite_ids) for book in products],
    })


@favorites_blueprint.post("/<string:book_id>")
@active_user_required
def add_favorite(book_id: str):
    user_id = get_authenticated_user().id
    book = db.session.scalar(_public_book_query().where(
        (BookProduct.id == book_id) | (BookProduct.slug == book_id)
    ))
    if book is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "Book was not found."}}), 404

    favorite = db.session.scalar(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.book_id == book.id)
    )
    if favorite is None:
        db.session.add(Favorite(user_id=user_id, book_id=book.id))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            favorite = db.session.scalar(
                select(Favorite).where(Favorite.user_id == user_id, Favorite.book_id == book.id)
            )
            if favorite is None:
                raise
    return jsonify({"bookId": book.id, "is_favorite": True}), 200


@favorites_blueprint.delete("/<string:book_id>")
@active_user_required
def remove_favorite(book_id: str):
    user_id = get_authenticated_user().id
    favorite = db.session.scalar(
        select(Favorite)
        .join(BookProduct, Favorite.book_id == BookProduct.id)
        .where(
            Favorite.user_id == user_id,
            (BookProduct.id == book_id) | (BookProduct.slug == book_id),
        )
    )
    if favorite is not None:
        db.session.delete(favorite)
        db.session.commit()
    return "", 204
