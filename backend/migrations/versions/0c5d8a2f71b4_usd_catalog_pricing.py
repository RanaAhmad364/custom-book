"""Convert active catalog and pricing to USD without changing order history.

Revision ID: 0c5d8a2f71b4
Revises: 91d4a7c2e6b0
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "0c5d8a2f71b4"
down_revision = "91d4a7c2e6b0"
branch_labels = None
depends_on = None


def _plan_price(book_type: str | None, prices: dict[str, str], fallback: str) -> str:
    return prices.get((book_type or "BASIC").upper(), fallback)


def upgrade():
    connection = op.get_bind()
    connection.execute(sa.text(
        "UPDATE pricing_tiers SET base_price = CASE upper(code) "
        "WHEN 'LIGHT' THEN 24.00 WHEN 'BASIC' THEN 40.00 WHEN 'PREMIUM' THEN 60.00 "
        "ELSE round(base_price / 100.0, 2) END, currency = 'USD' "
        "WHERE upper(currency) = 'PKR'"
    ))
    connection.execute(sa.text(
        "UPDATE page_pricing SET price_per_page = CASE "
        "WHEN tier_id IN (SELECT id FROM pricing_tiers WHERE upper(code) = 'LIGHT') THEN 0.10 "
        "WHEN tier_id IN (SELECT id FROM pricing_tiers WHERE upper(code) = 'BASIC') THEN 0.25 "
        "WHEN tier_id IN (SELECT id FROM pricing_tiers WHERE upper(code) = 'PREMIUM') THEN 0.50 "
        "ELSE round(price_per_page / 100.0, 2) END "
        "WHERE tier_id IN (SELECT id FROM pricing_tiers WHERE upper(currency) = 'USD')"
    ))
    connection.execute(sa.text(
        "UPDATE shipping_rates SET price = CASE "
        "WHEN country_code = 'PK' THEN 5.99 ELSE 9.99 END, currency = 'USD' "
        "WHERE upper(currency) = 'PKR'"
    ))
    connection.execute(sa.text(
        "UPDATE discount_codes SET value = round(value / 100.0, 2), currency = 'USD' "
        "WHERE upper(currency) = 'PKR' AND lower(discount_type) = 'fixed'"
    ))
    connection.execute(sa.text(
        "UPDATE discount_codes SET currency = NULL "
        "WHERE upper(currency) = 'PKR' AND lower(discount_type) = 'percent'"
    ))
    connection.execute(sa.text(
        "UPDATE book_products SET "
        "starting_price = CASE upper(coalesce(book_type, 'BASIC')) "
        "WHEN 'LIGHT' THEN 18.00 WHEN 'BASIC' THEN 30.00 WHEN 'MEDIUM' THEN 40.00 "
        "WHEN 'PREMIUM' THEN 45.00 ELSE round(starting_price / 100.0, 2) END, "
        "currency = 'USD' WHERE upper(currency) = 'PKR'"
    ))
    connection.execute(sa.text(
        "UPDATE book_variants SET "
        "base_price = CASE upper(coalesce((SELECT book_type FROM book_products "
        "WHERE book_products.id = book_variants.product_id), 'BASIC')) "
        "WHEN 'LIGHT' THEN CASE WHEN (SELECT code FROM paper_types WHERE id = paper_type_id) = 'standard' "
        "THEN 6.00 ELSE 8.00 END "
        "WHEN 'PREMIUM' THEN CASE WHEN (SELECT code FROM paper_types WHERE id = paper_type_id) = 'standard' "
        "THEN 15.00 ELSE 17.00 END "
        "ELSE CASE WHEN (SELECT code FROM paper_types WHERE id = paper_type_id) = 'standard' "
        "THEN 10.00 ELSE 12.00 END END, currency = 'USD' "
        "WHERE upper(currency) = 'PKR'"
    ))

    products = connection.execute(sa.text(
        "SELECT id, book_type, admin_metadata FROM book_products"
    )).mappings()
    for product in products:
        metadata_value = product["admin_metadata"]
        if not metadata_value:
            metadata = {}
        elif isinstance(metadata_value, str):
            metadata = json.loads(metadata_value)
        else:
            metadata = dict(metadata_value)
        book_type = (product["book_type"] or "BASIC").upper()
        metadata["pdfPrice"] = _plan_price(
            book_type,
            {"LIGHT": "3.99", "BASIC": "5.99", "MEDIUM": "7.99", "PREMIUM": "9.99"},
            "5.99",
        )
        metadata["printingPrice"] = _plan_price(
            book_type,
            {"LIGHT": "6.00", "BASIC": "10.00", "MEDIUM": "12.00", "PREMIUM": "15.00"},
            "10.00",
        )
        metadata["basePageCount"] = int(metadata.get("basePageCount") or 24)
        metadata["extraPagePrice"] = _plan_price(
            book_type,
            {"LIGHT": "0.10", "BASIC": "0.25", "MEDIUM": "0.35", "PREMIUM": "0.50"},
            "0.25",
        )
        connection.execute(
            sa.text("UPDATE book_products SET admin_metadata = :metadata WHERE id = :id"),
            {"metadata": json.dumps(metadata), "id": product["id"]},
        )

    for table in ("pricing_tiers", "shipping_rates"):
        with op.batch_alter_table(table) as batch:
            batch.alter_column("currency", server_default="USD")
    with op.batch_alter_table("book_products") as batch:
        batch.alter_column("currency", server_default="USD")
    with op.batch_alter_table("book_variants") as batch:
        batch.alter_column("currency", server_default="USD")


def downgrade():
    raise RuntimeError("USD catalog prices cannot be safely converted back to PKR.")
