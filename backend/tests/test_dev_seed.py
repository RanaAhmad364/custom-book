from sqlalchemy import select

from memorybook.extensions import db
from memorybook.models import BookCategory, BookCollection, BookProduct, BookTemplate


def test_development_catalog_seed_is_guarded_idempotent_and_non_destructive(app, client):
    runner = app.test_cli_runner()

    denied = runner.invoke(args=["seed-demo-catalog"])
    assert denied.exit_code != 0
    assert "only be added in development" in denied.output

    app.config["ENVIRONMENT"] = "development"
    first = runner.invoke(args=["seed-demo-catalog"])
    assert first.exit_code == 0

    with app.app_context():
        product = db.session.scalar(
            select(BookProduct).where(BookProduct.slug == "development-travel-book")
        )
        assert product is not None
        product.title = "Locally customized sample"
        db.session.commit()

    second = runner.invoke(args=["seed-demo-catalog"])
    assert second.exit_code == 0

    with app.app_context():
        assert db.session.scalar(select(db.func.count()).select_from(BookCategory)) == 1
        assert db.session.scalar(select(db.func.count()).select_from(BookCollection)) == 1
        assert db.session.scalar(select(db.func.count()).select_from(BookProduct)) == 1
        assert db.session.scalar(select(db.func.count()).select_from(BookTemplate)) == 1
        seeded_product = db.session.scalar(
            select(BookProduct).where(BookProduct.slug == "development-travel-book")
        )
        assert seeded_product.title == "Locally customized sample"
        assert seeded_product.currency == "PKR"

    response = client.get("/api/v1/books")
    assert response.status_code == 200
    assert [item["slug"] for item in response.json["items"]] == ["development-travel-book"]
