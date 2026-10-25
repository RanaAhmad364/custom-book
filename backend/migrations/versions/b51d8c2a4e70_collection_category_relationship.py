"""Add a safe category relationship to collections.

Revision ID: b51d8c2a4e70
Revises: 4bc81f02d9a7

The new foreign key is nullable so ambiguous, stale, and unreferenced legacy
collections remain intact and can be resolved explicitly by an administrator.
Downgrading removes category_id assignments made after this migration but
preserves the original related_categories JSON and all other collection data.
"""
from __future__ import annotations

import json
import logging

from alembic import op
import sqlalchemy as sa


revision = "b51d8c2a4e70"
down_revision = "4bc81f02d9a7"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)


def _reference_candidates(reference, categories_by_id, categories_by_slug, categories_by_name):
    if not isinstance(reference, str) or not reference.strip():
        return set()
    value = reference.strip()
    candidates = set()
    if value in categories_by_id:
        candidates.add(categories_by_id[value])
    if value in categories_by_slug:
        candidates.update(categories_by_slug[value])
    candidates.update(categories_by_name.get(value.casefold(), set()))
    return candidates


def upgrade():
    with op.batch_alter_table("book_collections") as batch:
        batch.add_column(sa.Column("category_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_book_collections_category_id_book_categories",
            "book_categories",
            ["category_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_book_collections_category_id", ["category_id"], unique=False)

    connection = op.get_bind()
    categories = connection.execute(
        sa.text("SELECT id, name, slug FROM book_categories")
    ).mappings().all()
    categories_by_id = {row["id"]: row["id"] for row in categories}
    categories_by_slug = {}
    categories_by_name = {}
    for row in categories:
        categories_by_slug.setdefault(row["slug"], set()).add(row["id"])
        categories_by_name.setdefault(row["name"].strip().casefold(), set()).add(row["id"])

    mapped_count = 0
    unresolved_count = 0
    collections = connection.execute(
        sa.text("SELECT id, slug, related_categories FROM book_collections ORDER BY id")
    ).mappings().all()
    for collection in collections:
        references = collection["related_categories"]
        if isinstance(references, str):
            try:
                references = json.loads(references)
            except (TypeError, ValueError):
                references = None

        candidates = set()
        reason = None
        if not isinstance(references, list) or len(references) != 1:
            reason = "expected exactly one legacy category reference"
        else:
            candidates = _reference_candidates(
                references[0],
                categories_by_id,
                categories_by_slug,
                categories_by_name,
            )
            if len(candidates) != 1:
                reason = "legacy category reference is stale or ambiguous"

        if reason:
            unresolved_count += 1
            logger.warning(
                "Collection category backfill left collection %s (%s) unresolved: %s.",
                collection["slug"],
                collection["id"],
                reason,
            )
            continue

        connection.execute(
            sa.text("UPDATE book_collections SET category_id = :category_id WHERE id = :collection_id"),
            {"category_id": next(iter(candidates)), "collection_id": collection["id"]},
        )
        mapped_count += 1

    logger.info(
        "Collection category backfill complete: %s mapped, %s unresolved.",
        mapped_count,
        unresolved_count,
    )


def downgrade():
    with op.batch_alter_table("book_collections") as batch:
        batch.drop_index("ix_book_collections_category_id")
        batch.drop_constraint("fk_book_collections_category_id_book_categories", type_="foreignkey")
        batch.drop_column("category_id")
