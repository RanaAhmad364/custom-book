from sqlalchemy import select

from memorybook.extensions import db
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
    PrintOrder,
    PrintQuote,
    PricingTier,
    ShippingRate,
    User,
    UserProject,
)
from memorybook.services.orders import create_print_quote


def test_demo_catalog_seed_is_previewed_idempotent_and_complete(app, client, tmp_path):
    runner = app.test_cli_runner()
    app.config["ENVIRONMENT"] = "development"
    app.config["ASSET_STORAGE_BACKEND"] = "filesystem"
    app.config["ASSET_LOCAL_DIRECTORY"] = str(tmp_path)

    preview = runner.invoke(args=["seed-demo-catalog"])
    assert preview.exit_code == 0, preview.output
    assert "Dry run only" in preview.output
    with app.app_context():
        assert db.session.scalar(select(db.func.count()).select_from(BookProduct)) == 0

    first = runner.invoke(args=["seed-demo-catalog", "--apply"])
    assert first.exit_code == 0, first.output
    assert "Demo catalog seed completed and verified." in first.output

    with app.app_context():
        categories = db.session.scalars(select(BookCategory).where(BookCategory.slug.like("demo-%"))).all()
        collections = db.session.scalars(select(BookCollection).where(BookCollection.slug.like("demo-%"))).all()
        products = db.session.scalars(select(BookProduct).where(BookProduct.slug.like("demo-%"))).all()
        templates = db.session.scalars(
            select(BookTemplate).where(BookTemplate.slug.like("demo-%-master-design"))
        ).all()
        variants = db.session.scalars(select(BookVariant)).all()
        projects = db.session.scalars(select(UserProject)).all()
        assert len(categories) == 4
        assert len(collections) == 6
        assert len(products) == 10
        assert len(templates) == 10
        assert len(variants) == 40
        assert len(projects) == 3
        assert all(product.is_active and product.currency == "PKR" for product in products)
        assert all(product.collection_id for product in products)
        assert all(template.is_active and template.published_design_document for template in templates)
        assert all(project.product_id and project.template_id and project.status == "draft" for project in projects)
        assert db.session.scalar(select(db.func.count()).select_from(BookSize)) == 2
        assert db.session.scalar(select(db.func.count()).select_from(CoverType)) == 2
        assert db.session.scalar(select(db.func.count()).select_from(PaperType)) == 2
        assert db.session.scalar(select(db.func.count()).select_from(PricingTier)) == 3
        assert db.session.scalar(select(db.func.count()).select_from(PagePricing)) == 3
        assert db.session.scalar(select(db.func.count()).select_from(ShippingRate)) == 1
        assert db.session.scalar(select(db.func.count()).select_from(User)) == 3

        customer = db.session.scalar(
            select(User).where(User.email == "demo.customer.1@memorybook.local")
        )
        product = db.session.scalar(
            select(BookProduct).where(BookProduct.slug == "demo-our-family-story")
        )
        project = db.session.scalar(
            select(UserProject).where(
                UserProject.user_id == customer.id,
                UserProject.product_id == product.id,
            )
        )
        quote = create_print_quote(
            project.id,
            customer.id,
            {"cover": "Demo Hardcover", "paper": "Demo Matte", "tier": "DEMO-BASIC", "quantity": 1},
            {
                "fullName": "Demo Customer",
                "line1": "1 Sample Street",
                "city": "Lahore",
                "region": "Punjab",
                "postalCode": "54000",
                "country": "PK",
                "phone": "+920000000000",
            },
        )
        assert quote["currency"] == "PKR"
        assert quote["bookPrice"] == "5900.00"
        assert quote["printingCharge"] == "2650.00"
        assert quote["additionalPages"] == "0.00"
        assert quote["shipping"] == "350.00"
        assert quote["total"] == "8900.00"
        assert db.session.scalar(select(db.func.count()).select_from(PrintOrder)) == 0
        assert db.session.scalar(select(db.func.count()).select_from(PrintQuote)) == 1

        customized = db.session.scalar(
            select(BookProduct).where(BookProduct.slug == "demo-our-family-story")
        )
        customized.title = "Locally customized demo"
        db.session.commit()

    public_books = client.get("/api/v1/books")
    assert public_books.status_code == 200
    public_slugs = {item["slug"] for item in public_books.json["items"]}
    assert len({slug for slug in public_slugs if slug.startswith("demo-")}) == 10

    second = runner.invoke(args=["seed-demo-catalog", "--apply"])
    assert second.exit_code == 0, second.output
    with app.app_context():
        assert db.session.scalar(
            select(db.func.count()).select_from(BookCategory).where(BookCategory.slug.like("demo-%"))
        ) == 4
        assert db.session.scalar(
            select(db.func.count()).select_from(BookCollection).where(BookCollection.slug.like("demo-%"))
        ) == 6
        assert db.session.scalar(
            select(db.func.count()).select_from(BookProduct).where(BookProduct.slug.like("demo-%"))
        ) == 10
        assert db.session.scalar(
            select(db.func.count()).select_from(BookTemplate).where(BookTemplate.slug.like("demo-%-master-design"))
        ) == 10
        preserved = db.session.scalar(
            select(BookProduct).where(BookProduct.slug == "demo-our-family-story")
        )
        assert preserved.title == "Locally customized demo"


def test_demo_catalog_seed_requires_explicit_apply_confirmation(app):
    runner = app.test_cli_runner()
    app.config["TESTING"] = False
    app.config["ENVIRONMENT"] = "production"

    denied = runner.invoke(args=["seed-demo-catalog", "--apply", "--confirm-local-database"])
    assert denied.exit_code != 0
    assert "only in development" in denied.output
