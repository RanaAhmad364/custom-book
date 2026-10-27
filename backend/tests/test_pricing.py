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


def test_configured_currency_and_plan_page_rules_are_enforced(app):
    product = SimpleNamespace(
        currency="PKR",
        book_type="BASIC",
        page_count_min=24,
        page_count_max=80,
        admin_metadata={"basePageCount": 30, "evenPageCountRequired": True},
    )

    with app.app_context():
        assert default_currency() == "PKR"
        assert validate_order_page_count(product, 50)["plan"] == "BASIC"
        with pytest.raises(ConflictError, match="even page count"):
            validate_order_page_count(product, 51, print_order=True)
        with pytest.raises(ConflictError, match="cannot exceed"):
            validate_order_page_count(product, 81)
