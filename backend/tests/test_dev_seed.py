import re
from pathlib import Path
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO

from PIL import Image
from sqlalchemy import event, select

from memorybook import create_app
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
    DownloadEntitlement,
    GeneratedFile,
    PagePricing,
    Payment,
    PaperType,
    PdfJob,
    PdfOrder,
    PrintOrder,
    PrintQuote,
    PricingTier,
    ProjectRevision,
    ShippingRate,
    User,
    UserProject,
)
from memorybook.services.catalog_projects import create_revision
from memorybook.services.orders import create_print_quote
from memorybook.services.pdf_generation import generate_pdf_job


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
        assert len(categories) == 6
        assert len(collections) == 4
        assert len(products) == 12
        assert len(templates) == 12
        assert len(variants) == 108
        assert len(projects) == 3
        assert all(product.is_active and product.currency == "PKR" for product in products)
        assert all(product.collection_id for product in products)
        assert all(template.is_active and template.published_design_document for template in templates)
        assert all(project.product_id and project.template_id and project.status == "draft" for project in projects)
        assert db.session.scalar(select(db.func.count()).select_from(BookSize)) == 2
        assert db.session.scalar(select(db.func.count()).select_from(CoverType)) == 3
        assert db.session.scalar(select(db.func.count()).select_from(PaperType)) == 3
        assert db.session.scalar(select(db.func.count()).select_from(PricingTier)) == 3
        assert db.session.scalar(select(db.func.count()).select_from(PagePricing)) == 3
        assert db.session.scalar(select(db.func.count()).select_from(ShippingRate)) == 1
        assert db.session.scalar(select(db.func.count()).select_from(User)) == 3
        assert {item.code for item in db.session.scalars(select(CoverType)).all()} == {"hardcover", "softcover", "linen"}
        assert {item.code for item in db.session.scalars(select(PaperType)).all()} == {"standard", "premium", "archival"}
        assert {item.code for item in db.session.scalars(select(PricingTier)).all()} == {"LIGHT", "BASIC", "PREMIUM"}

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
            {"cover": "hardcover", "paper": "standard", "tier": "basic", "quantity": 1},
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
        for item, legacy_name in (
            (db.session.scalar(select(CoverType).where(CoverType.code == "hardcover")), "Demo Hardcover"),
            (db.session.scalar(select(CoverType).where(CoverType.code == "softcover")), "Demo Softcover"),
            (db.session.scalar(select(PaperType).where(PaperType.code == "standard")), "Demo Matte"),
            (db.session.scalar(select(PaperType).where(PaperType.code == "premium")), "Demo Satin"),
        ):
            item.name = legacy_name
            item.code = f"legacy-{item.id.replace('-', '')[:32]}"
        for item in db.session.scalars(select(CoverType).where(CoverType.code == "linen")).all():
            db.session.execute(
                db.delete(BookVariant).where(BookVariant.cover_type_id == item.id)
            )
            db.session.delete(item)
        for item in db.session.scalars(select(PaperType).where(PaperType.code == "archival")).all():
            db.session.execute(
                db.delete(BookVariant).where(BookVariant.paper_type_id == item.id)
            )
            db.session.delete(item)
        for tier in db.session.scalars(select(PricingTier)).all():
            tier.code = f"DEMO-{tier.code}"
            tier.name = f"Demo {tier.name}"
        for product in products:
            metadata = dict(product.admin_metadata)
            metadata["printingTiers"] = ["DEMO-LIGHT", "DEMO-BASIC", "DEMO-PREMIUM"]
            product.admin_metadata = metadata
        db.session.commit()

    public_books = client.get("/api/v1/books")
    assert public_books.status_code == 200
    public_slugs = {item["slug"] for item in public_books.json["items"]}
    assert len({slug for slug in public_slugs if slug.startswith("demo-")}) == 12

    second = runner.invoke(args=["seed-demo-catalog", "--apply"])
    assert second.exit_code == 0, second.output
    with app.app_context():
        assert db.session.scalar(
            select(db.func.count()).select_from(BookCategory).where(BookCategory.slug.like("demo-%"))
        ) == 6
        assert db.session.scalar(
            select(db.func.count()).select_from(BookCollection).where(BookCollection.slug.like("demo-%"))
        ) == 4
        assert db.session.scalar(
            select(db.func.count()).select_from(BookProduct).where(BookProduct.slug.like("demo-%"))
        ) == 12
        assert db.session.scalar(
            select(db.func.count()).select_from(BookTemplate).where(BookTemplate.slug.like("demo-%-master-design"))
        ) == 12
        preserved = db.session.scalar(
            select(BookProduct).where(BookProduct.slug == "demo-our-family-story")
        )
        assert preserved.title == "Locally customized demo"
        assert db.session.scalar(select(db.func.count()).select_from(BookVariant)) == 108
        assert {item.code for item in db.session.scalars(select(CoverType)).all()} == {"hardcover", "softcover", "linen"}
        assert {item.code for item in db.session.scalars(select(PaperType)).all()} == {"standard", "premium", "archival"}
        assert {item.code for item in db.session.scalars(select(PricingTier)).all()} == {"LIGHT", "BASIC", "PREMIUM"}


def test_migrated_seeded_books_quote_every_available_print_combination(tmp_path):
    database_path = tmp_path / "print-options.sqlite"
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret-key-that-is-not-used-outside-testing",
        "JWT_SECRET_KEY": "test-only-jwt-secret-that-is-not-used-outside-testing",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "RATELIMIT_ENABLED": False,
        "RATE_LIMIT_STORAGE_URI": "memory://",
        "ENVIRONMENT": "testing",
        "MIGRATIONS_DIRECTORY": str(migrations),
        "CORS_ORIGINS": [],
        "PAYMENT_DEFAULT_CURRENCY": "PKR",
        "LOG_LEVEL": "CRITICAL",
        "ASSET_STORAGE_BACKEND": "filesystem",
        "ASSET_LOCAL_DIRECTORY": str(tmp_path / "assets"),
        "CELERY": {"broker_url": "memory://", "result_backend": "cache+memory://"},
        "REDIS_URL": "redis://localhost:6379/0",
    })
    upgraded = app.test_cli_runner().invoke(args=["db", "upgrade"])
    assert upgraded.exit_code == 0, upgraded.output
    with app.app_context():
        engine = app.extensions["sqlalchemy"].engine
        event.listen(
            engine,
            "connect",
            lambda connection, _record: connection.create_function(
                "now", 0, lambda: datetime.now(UTC).isoformat(sep=" "),
            ),
        )
        engine.dispose()
    with app.app_context(), app.test_request_context("/seed-demo-catalog"):
        from memorybook.demo_catalog import seed_demo_catalog

        assert seed_demo_catalog()["published_books"] == 12

    with app.app_context():
        product = db.session.scalar(
            select(BookProduct).where(BookProduct.slug == "demo-our-family-story")
        )
        original_cover_key = product.cover_asset_key
        original_gallery_key = product.admin_metadata["previewImageKeys"][1]
        storage = get_asset_storage()
        for key in (original_cover_key, original_gallery_key):
            small_art = BytesIO()
            Image.new("RGB", (900, 1100), color="#cdbb9c").save(small_art, format="PNG")
            small_art.seek(0)
            storage.upload(key, small_art, "image/png")

    with app.app_context(), app.test_request_context("/seed-demo-catalog"):
        from memorybook.demo_catalog import seed_demo_catalog

        assert seed_demo_catalog()["published_books"] == 12

    with app.app_context():
        product = db.session.scalar(
            select(BookProduct).where(BookProduct.slug == "demo-our-family-story")
        )
        template = db.session.scalar(
            select(BookTemplate).where(BookTemplate.product_id == product.id)
        )
        assert product.cover_asset_key != original_cover_key
        assert product.admin_metadata["previewImageKeys"][1] != original_gallery_key
        assert {
            asset["assetKey"] for asset in template.published_design_document["assets"]
        } == set(product.admin_metadata["previewImageKeys"][:2])
        for asset in template.published_design_document["assets"]:
            with Image.open(BytesIO(get_asset_storage().download(asset["assetKey"]))) as image:
                assert image.width >= 3600
                assert image.height >= 4400

    outbox = []
    app.extensions["auth_email_outbox"] = outbox
    app.extensions["auth_email_sender"] = lambda recipient, subject, body: outbox.append((recipient, subject, body))
    client = app.test_client()
    email = "print-options-customer@example.test"
    assert client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery"},
    ).status_code == 201
    verification_email = outbox[-1][2]
    code = re.search(r"\b(\d{6})\b", verification_email).group(1)
    assert client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "code": code},
    ).status_code == 200
    assert client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-battery"},
    ).status_code == 200
    csrf = {"X-CSRF-TOKEN": client.get_cookie("csrf_access_token").value}

    with app.app_context():
        products = db.session.scalars(select(BookProduct).where(BookProduct.slug.like("demo-%")).order_by(BookProduct.slug)).all()
        templates = {
            template.product_id: template
            for template in db.session.scalars(
                select(BookTemplate).where(BookTemplate.is_active.is_(True))
            ).all()
        }

    address = {
        "fullName": "Print Options Customer",
        "line1": "1 Sample Street",
        "city": "Lahore",
        "region": "Punjab",
        "postalCode": "54000",
        "country": "PK",
        "phone": "+920000000000",
    }
    project_ids = []
    for product in products:
        template = templates[product.id]
        project_response = client.post(
            "/api/v1/projects",
            json={
                "title": f"Test {product.title}",
                "pageCount": 24,
                "productId": product.id,
                "templateId": template.id,
            },
            headers=csrf,
        )
        assert project_response.status_code == 201, project_response.json
        project = project_response.json["project"]
        project_ids.append(project["id"])
        available = client.get(f"/api/v1/projects/{project['id']}/print-options")
        assert available.status_code == 200, available.json
        combinations = available.json["combinations"]
        assert len(combinations) == 27
        assert {item["cover"] for item in combinations} == {"hardcover", "softcover", "linen"}
        assert {item["paper"] for item in combinations} == {"standard", "premium", "archival"}
        assert {item["tier"] for item in combinations} == {"light", "basic", "premium"}
        for combination in combinations:
            quote = client.post(
                "/api/v1/print/quotes",
                json={
                    "projectId": project["id"],
                    "configuration": {**combination, "quantity": 1},
                    "shippingAddress": address,
                },
                headers=csrf,
            )
            assert quote.status_code == 200, quote.json
            assert quote.json["total"]

    first_project_id = project_ids[0]
    first_options = client.get(f"/api/v1/projects/{first_project_id}/print-options").json["combinations"]
    unavailable = first_options[0]
    with app.app_context():
        project = db.session.get(UserProject, first_project_id)
        variant = db.session.scalar(
            select(BookVariant)
            .join(CoverType, CoverType.id == BookVariant.cover_type_id)
            .join(PaperType, PaperType.id == BookVariant.paper_type_id)
            .where(
                BookVariant.product_id == project.product_id,
                CoverType.code == unavailable["cover"],
                PaperType.code == unavailable["paper"],
                BookVariant.is_active.is_(True),
            )
        )
        variant.is_active = False
        db.session.commit()
    rejected = client.post(
        "/api/v1/print/quotes",
        json={
            "projectId": first_project_id,
            "configuration": {**unavailable, "quantity": 1},
            "shippingAddress": address,
        },
        headers=csrf,
    )
    assert rejected.status_code == 409
    assert "not available for this book size" in rejected.json["error"]["message"]

    with app.app_context():
        project = db.session.get(UserProject, first_project_id)
        revision = create_revision(project, project.version)
        order = PdfOrder(
            order_number="PDF-SEEDED-BOOK-1",
            user_id=project.user_id,
            project_id=project.id,
            project_revision_id=revision.id,
            status="paid",
            currency="PKR",
            service_price=Decimal("850.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("850.00"),
            price_snapshot={"printPdfIncluded": True},
            page_count=project.page_count,
            paid_at=datetime.now(UTC),
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(Payment(
            user_id=project.user_id,
            pdf_order_id=order.id,
            provider="manual",
            status="successful",
            amount=order.total_amount,
            currency=order.currency,
        ))
        jobs = {
            profile: PdfJob(order_id=order.id, generation_profile=profile, status="queued")
            for profile in ("digital", "print")
        }
        db.session.add_all(jobs.values())
        db.session.commit()
        assert app.config.get("PDF_MIN_PRINT_DPI", 300) == 300

        for profile, job in jobs.items():
            result = generate_pdf_job(job.id)
            assert result["status"] == "ready"
            generated_file = db.session.scalar(
                select(GeneratedFile).where(
                    GeneratedFile.pdf_order_id == order.id,
                    GeneratedFile.generation_profile == profile,
                )
            )
            assert generated_file is not None
            assert generated_file.byte_size > 0
            assert generated_file.storage_key.endswith(f"/{profile}/{job.id}.pdf")
            assert db.session.scalar(
                select(DownloadEntitlement).where(
                    DownloadEntitlement.generated_file_id == generated_file.id,
                )
            ) is not None


def test_demo_catalog_seed_requires_explicit_apply_confirmation(app):
    runner = app.test_cli_runner()
    app.config["TESTING"] = False
    app.config["ENVIRONMENT"] = "production"

    denied = runner.invoke(args=["seed-demo-catalog", "--apply", "--confirm-local-database"])
    assert denied.exit_code != 0
    assert "only in development" in denied.output
