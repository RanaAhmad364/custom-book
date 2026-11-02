from decimal import Decimal
from types import SimpleNamespace

import pytest

from memorybook.errors import ConflictError
from memorybook.services.pricing import (
    calculate_book_price,
    calculate_discount,
    default_currency,
    validate_order_page_count,
)


def test_base_page_count_does_not_add_extra_page_charges(app):
    with app.app_context():
        quote = calculate_book_price(Decimal("500.00"), 30, 30, Decimal("4.00"))

    assert quote == {
        "basePrice": Decimal("500.00"),
        "additionalPages": Decimal("0.00"),
        "extraPageCount": 0,
        "shipping": Decimal("0.00"),
        "discount": Decimal("0.00"),
        "total": Decimal("500.00"),
    }


def test_extra_pages_are_charged_at_the_configured_rate(app):
    with app.app_context():
        quote = calculate_book_price(Decimal("500.00"), 35, 30, Decimal("4.00"))

    assert quote["extraPageCount"] == 5
    assert quote["additionalPages"] == Decimal("20.00")
    assert quote["total"] == Decimal("520.00")


def test_fifty_pages_on_a_thirty_page_template_apply_ten_extra_pages(app):
    with app.app_context():
        quote = calculate_book_price(Decimal("500.00"), 50, 30, Decimal("4.00"))

    assert quote["extraPageCount"] == 20
    assert quote["additionalPages"] == Decimal("80.00")
    assert quote["total"] == Decimal("580.00")


@pytest.mark.parametrize(
    ("tier", "base_price", "extra_page_price"),
    [
        ("LIGHT", "24.00", "0.10"),
        ("BASIC", "40.00", "0.25"),
        ("PREMIUM", "60.00", "0.50"),
    ],
)
def test_fifty_page_print_quote_costs_more_than_twenty_four_pages_in_every_tier(
    app,
    tier,
    base_price,
    extra_page_price,
):
    with app.app_context():
        base = Decimal(base_price)
        per_page = Decimal(extra_page_price)
        quote_24 = calculate_book_price(base, 24, 24, per_page)
        quote_50 = calculate_book_price(base, 50, 24, per_page)

    assert quote_24["total"] == base
    assert quote_50["total"] == base + 26 * per_page
    assert quote_50["total"] > quote_24["total"], tier


def test_discounts_and_shipping_are_accounted_for_by_the_price_calculator(app):
    with app.app_context():
        percentage = calculate_discount(Decimal("600.00"), "percent", Decimal("10.00"))
        fixed = calculate_discount(Decimal("600.00"), "fixed", Decimal("25.00"))
        quote = calculate_book_price(
            Decimal("500.00"),
            50,
            30,
            Decimal("4.00"),
            shipping=Decimal("15.00"),
            discount=fixed,
        )

    assert percentage == Decimal("60.00")
    assert fixed == Decimal("25.00")
    assert quote["shipping"] == Decimal("15.00")
    assert quote["discount"] == Decimal("25.00")
    assert quote["total"] == Decimal("570.00")


def test_shipping_is_charged_once_per_order_unless_rate_is_per_copy(app):
    with app.app_context():
        per_order = calculate_book_price(
            Decimal("40.00"), 24, 24, Decimal("0.00"),
            quantity=2, shipping=Decimal("45.99"),
        )
        per_copy = calculate_book_price(
            Decimal("40.00"), 24, 24, Decimal("0.00"),
            quantity=2, shipping=Decimal("45.99"), shipping_per_copy=True,
        )

    assert per_order["shipping"] == Decimal("45.99")
    assert per_order["total"] == Decimal("125.99")
    assert per_copy["shipping"] == Decimal("91.98")
    assert per_copy["total"] == Decimal("171.98")


def test_configured_currency_and_plan_page_rules_are_enforced(app):
    product = SimpleNamespace(
        currency="USD",
        book_type="BASIC",
        page_count_min=24,
        page_count_max=80,
        admin_metadata={"basePageCount": 30, "evenPageCountRequired": True},
    )

    with app.app_context():
        assert default_currency() == "USD"
        assert validate_order_page_count(product, 50)["plan"] == "BASIC"
        with pytest.raises(ConflictError, match="even page count"):
            validate_order_page_count(product, 51, print_order=True)
        with pytest.raises(ConflictError, match="cannot exceed"):
            validate_order_page_count(product, 81)


def test_catalog_currency_mismatch_error_identifies_the_configuration_to_change(app):
    product = SimpleNamespace(
        currency="PKR",
        book_type="BASIC",
        page_count_min=24,
        page_count_max=80,
        admin_metadata={"basePageCount": 24},
    )
    with app.app_context(), pytest.raises(ConflictError) as failure:
        validate_order_page_count(product, 24)
    assert "PAYMENT_DEFAULT_CURRENCY is USD but the data is PKR" in str(failure.value)
    assert "set PAYMENT_DEFAULT_CURRENCY=PKR in backend/.env" in str(failure.value)
