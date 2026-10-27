import hashlib
import re
from datetime import UTC, datetime, timedelta
import time
from decimal import Decimal
from urllib.parse import urlsplit
from io import BytesIO

from PIL import Image

from memorybook.extensions import db
from memorybook.models import (
    AdminActivityLog,
    BackgroundJob,
    BookCategory,
    BookCollection,
    BookProduct,
    BookSize,
    BookTemplate,
    BookTemplateVersion,
    CoverType,
    DiscountCode,
    DownloadEntitlement,
    DownloadHistory,
    GeneratedFile,
    EmailLog,
    Notification,
    PaperType,
    PagePricing,
    Payment,
    PaymentAttempt,
    OrderStatusHistory,
    PdfOrder,
    ProjectAsset,
    PricingTier,
    PrintOrder,
    PrintOrderItem,
    ProjectRevision,
    Role,
    ShippingAddress,
    Shipment,
    ShippingRate,
    SupportTicket,
    User,
    UserProject,
    UserRole,
)


class FakeStorage:
    def __init__(self):
        self.objects = {}

    def upload(self, key, stream, mime_type):
        self.objects[key] = (stream.read(), mime_type)

    def download_url(self, key):
        return f"https://assets.example.test/{key}"

    def public_download_url(self, key):
        return f"https://assets.example.test/public/{key}"

    def private_download_url(self, key):
        return f"https://assets.example.test/private/{key}"

    def copy(self, source_key, target_key):
        self.objects[target_key] = self.objects[source_key]

    def delete(self, key):
        self.objects.pop(key, None)

    def download(self, key):
        return self.objects[key][0]

    def content_type(self, key):
        return self.objects[key][1]


def create_category(client, csrf, *, slug="category-test"):
    response = client.post(
        "/api/v1/admin/categories",
        json={"name": "Test Category", "slug": slug, "description": "For category tests"},
        headers=csrf,
    )
    assert response.status_code == 201, response.get_json()
    return response.json["category"]


def valid_png():
    stream = BytesIO()
    Image.new("RGB", (2, 2), (15, 45, 75)).save(stream, format="PNG")
    return stream.getvalue()


def create_draft_book(client, csrf, category_id):
    response = client.post(
        "/api/v1/admin/books",
        json={
            "title": "Test Book",
            "slug": f"test-book-{category_id[:8]}",
            "description": "A draft book for category safety tests",
            "categoryId": category_id,
        },
        headers=csrf,
    )
    assert response.status_code == 201, response.get_json()
    return response.json["book"]


def test_admin_purchases_downloads_and_analytics_are_server_filtered_and_protected(app):
    admin, csrf = admin_client(app, "admin-history@example.test")
    normal_user, _ = admin_client(app, "customer-history@example.test", assign_admin=False)
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "customer-history@example.test"))
        project = UserProject(
            user_id=user.id,
            title="Filterable test project",
            page_count=24,
            document={"schemaVersion": 1, "pages": [{"id": "page-history", "elements": []}]},
        )
        db.session.add(project)
        db.session.flush()
        revision = ProjectRevision(
            project_id=project.id,
            revision_number=1,
            document_version=1,
            document=project.document,
            checksum_sha256="b" * 64,
        )
        db.session.add(revision)
        db.session.flush()
        order = PdfOrder(
            order_number="PDF-HISTORY-1",
            user_id=user.id,
            project_id=project.id,
            project_revision_id=revision.id,
            status="paid",
            currency="PKR",
            service_price=Decimal("100.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            price_snapshot={"total": "100.00"},
            page_count=24,
            paid_at=datetime.now(UTC),
        )
        db.session.add(order)
        db.session.flush()
        payment = Payment(
            user_id=user.id,
            pdf_order_id=order.id,
            provider="manual",
            status="successful",
            amount=Decimal("100.00"),
            currency="PKR",
        )
        generated = GeneratedFile(
            pdf_order_id=order.id,
            generation_profile="digital",
            storage_key="test/history.pdf",
            file_type="application/pdf",
            byte_size=20,
            checksum_sha256="c" * 64,
        )
        db.session.add_all([payment, generated])
        db.session.flush()
        entitlement = DownloadEntitlement(
            user_id=user.id,
            pdf_order_id=order.id,
            generated_file_id=generated.id,
            download_count=1,
        )
        db.session.add(entitlement)
        db.session.flush()
        db.session.add(DownloadHistory(
            entitlement_id=entitlement.id,
            generated_file_id=generated.id,
        ))
        db.session.commit()
        order_id = order.id

    forbidden_orders = normal_user.get("/api/v1/admin/purchases")
    forbidden_downloads = normal_user.get("/api/v1/admin/downloads")
    forbidden_dashboard = normal_user.get("/api/v1/admin/dashboard")
    forbidden_analytics = normal_user.get("/api/v1/admin/analytics/overview")
    forbidden_purchases = normal_user.get("/api/v1/admin/orders")
    forbidden_exports = [
        normal_user.get(path).status_code
        for path in (
            "/api/v1/admin/purchases/export.csv",
            "/api/v1/admin/orders/export.csv",
            "/api/v1/admin/downloads/export.csv",
            "/api/v1/admin/analytics/revenue-chart",
            "/api/v1/admin/analytics/download-chart",
            "/api/v1/admin/analytics/top-selling",
            "/api/v1/admin/analytics/most-downloaded",
            "/api/v1/admin/analytics/most-favorited",
            "/api/v1/admin/analytics/recent-payments",
            "/api/v1/admin/analytics/recent-users",
        )
    ]
    assert forbidden_orders.status_code == 403
    assert forbidden_downloads.status_code == 403
    assert forbidden_dashboard.status_code == 403
    assert forbidden_analytics.status_code == 403
    assert forbidden_purchases.status_code == 403
    assert forbidden_exports == [403] * len(forbidden_exports)

    purchases = admin.get(
        "/api/v1/admin/purchases?type=pdf&user=customer-history&book=Filterable%20test&paymentStatus=successful"
    )
    assert purchases.status_code == 200, purchases.get_json()
    assert purchases.json["pagination"]["totalItems"] == 1
    assert purchases.json["items"][0]["userName"] == "Name not provided"
    assert purchases.json["items"][0]["paymentStatus"] == "successful"
    assert purchases.json["items"][0]["pageCount"] == 24
    assert admin.get("/api/v1/admin/purchases?type=print").json["pagination"]["totalItems"] == 0
    assert admin.get("/api/v1/admin/purchases?dateFrom=2026-30-99").status_code == 400
    assert admin.get("/api/v1/admin/orders?dateFrom=not-a-date").status_code == 400

    downloads = admin.get("/api/v1/admin/downloads?user=customer-history&book=Filterable%20test")
    assert downloads.status_code == 200, downloads.get_json()
    assert downloads.json["pagination"]["totalItems"] == 1
    assert downloads.json["items"][0]["orderNumber"] == "PDF-HISTORY-1"
    assert downloads.json["items"][0]["type"] == "pdf"

    analytics = admin.get("/api/v1/admin/dashboard?days=7")
    assert analytics.status_code == 200, analytics.get_json()
    assert len(analytics.json["revenueSeries"]) == 7
    assert len(analytics.json["downloadsSeries"]) == 7
    assert analytics.json["mostDownloadedBooks"] == []
    assert admin.get("/api/v1/admin/dashboard?days=0").status_code == 400
    assert admin.get("/api/v1/admin/analytics/overview?days=7").status_code == 200
    assert admin.get("/api/v1/admin/analytics/revenue-chart?days=7").json["items"]
    assert len(admin.get("/api/v1/admin/analytics/download-chart?days=7").json["items"]) == 7
    assert admin.get("/api/v1/admin/analytics/most-downloaded").json["items"] == []
    assert admin.get("/api/v1/admin/analytics/top-selling").json["items"] == []
    assert admin.get("/api/v1/admin/analytics/most-favorited").json["items"] == []
    assert admin.get("/api/v1/admin/analytics/recent-users").json["items"]
    assert admin.get("/api/v1/admin/analytics/recent-payments").json["items"]

    export = admin.get("/api/v1/admin/orders/export.csv?type=pdf&user=customer-history")
    assert export.status_code == 200
    assert export.mimetype == "text/csv"
    assert "PDF-HISTORY-1" in export.get_data(as_text=True)
    download_export = admin.get("/api/v1/admin/downloads/export.csv?user=customer-history")
    assert download_export.status_code == 200
    assert "PDF-HISTORY-1" in download_export.get_data(as_text=True)
    timeline = admin.get(f"/api/v1/admin/orders/pdf/{order_id}/history")
    assert timeline.status_code == 200
    assert timeline.json["items"] == []
    assert normal_user.get(f"/api/v1/admin/orders/pdf/{order_id}/history").status_code == 403


def test_collections_require_category_and_books_reject_category_mismatches(app):
    client, csrf = admin_client(app, "collection-category-admin@example.test")
    travel = create_category(client, csrf, slug="collection-travel")
    family = client.post(
        "/api/v1/admin/categories",
        json={"name": "Family", "slug": "collection-family"},
        headers=csrf,
    ).json["category"]

    missing_category = client.post(
        "/api/v1/admin/collections",
        json={"name": "No category", "slug": "no-category"},
        headers=csrf,
    )
    assert missing_category.status_code == 400
    assert missing_category.json["error"]["details"]["categoryId"] == "required"

    collection_response = client.post(
        "/api/v1/admin/collections",
        json={
            "name": "Travel stories",
            "slug": "travel-stories",
            "categoryId": travel["id"],
            "relatedCategories": ["travel"],
        },
        headers=csrf,
    )
    assert collection_response.status_code == 201
    collection = collection_response.json["collection"]
    assert collection["categoryId"] == travel["id"]
    assert collection["categoryName"] == travel["name"]
    assert collection["relatedCategories"] == ["travel"]
    category_row = next(
        item for item in client.get("/api/v1/admin/categories").json["items"]
        if item["id"] == travel["id"]
    )
    assert category_row["collectionCount"] == 1

    mismatch = client.post(
        "/api/v1/admin/books",
        json={
            "title": "Wrong category",
            "slug": "wrong-category-book",
            "description": "A test book",
            "categoryId": family["id"],
            "collectionId": collection["id"],
        },
        headers=csrf,
    )
    assert mismatch.status_code == 400
    assert mismatch.json["error"]["details"]["collectionId"] == "category_mismatch"

    matching = client.post(
        "/api/v1/admin/books",
        json={
            "title": "Right category",
            "slug": "right-category-book",
            "description": "A test book",
            "categoryId": travel["id"],
            "collectionId": collection["id"],
        },
        headers=csrf,
    )
    assert matching.status_code == 201
    assert matching.json["book"]["collectionId"] == collection["id"]

    product_update_mismatch = client.patch(
        f"/api/v1/admin/books/{matching.json['book']['id']}",
        json={"categoryId": family["id"]},
        headers=csrf,
    )
    assert product_update_mismatch.status_code == 400
    assert product_update_mismatch.json["error"]["details"]["collectionId"] == "category_mismatch"

    update_mismatch = client.patch(
        f"/api/v1/admin/collections/{collection['id']}",
        json={"categoryId": family["id"]},
        headers=csrf,
    )
    assert update_mismatch.status_code == 409
    assert update_mismatch.json["error"]["details"]["books"] == 1
    with app.app_context():
        persisted_book = db.session.get(BookProduct, matching.json["book"]["id"])
        persisted_collection = db.session.get(BookCollection, collection["id"])
        assert persisted_book.category_id == travel["id"]
        assert persisted_book.collection_id == collection["id"]
        assert persisted_collection.category_id == travel["id"]


def test_admin_category_create_validation_and_duplicate_slug(app):
    client, csrf = admin_client(app, "category-validation-admin@example.test")
    invalid_slug = client.post(
        "/api/v1/admin/categories",
        json={"name": "Invalid Slug", "slug": "Upper Case"},
        headers=csrf,
    )
    assert invalid_slug.status_code == 400
    assert invalid_slug.json["error"]["details"]["slug"] == "invalid"

    create_category(client, csrf, slug="unique-category")
    duplicate = client.post(
        "/api/v1/admin/categories",
        json={"name": "Duplicate", "slug": "unique-category"},
        headers=csrf,
    )
    assert duplicate.status_code == 409
    assert "slug already exists" in duplicate.json["error"]["message"]
    category = next(
        item for item in client.get("/api/v1/admin/categories").json["items"]
        if item["slug"] == "unique-category"
    )
    empty_name = client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"name": " "},
        headers=csrf,
    )
    assert empty_name.status_code == 400
    invalid_order = client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"sortOrder": 1.5},
        headers=csrf,
    )
    assert invalid_order.status_code == 400
    negative_order = client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"sortOrder": -1},
        headers=csrf,
    )
    assert negative_order.status_code == 400
    valid_order = client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"sortOrder": 7},
        headers=csrf,
    )
    assert valid_order.status_code == 200
    assert valid_order.json["category"]["sortOrder"] == 7


def test_category_list_reports_product_and_collection_references(app):
    client, csrf = admin_client(app, "category-counts-admin@example.test")
    category = create_category(client, csrf, slug="category-counts")
    book = create_draft_book(client, csrf, category["id"])
    with app.app_context():
        db.session.add(BookCollection(
            name="Referenced collection",
            slug="category-counts-collection",
            related_categories=[category["slug"]],
        ))
        db.session.commit()

    listing = client.get("/api/v1/admin/categories?perPage=20")
    assert listing.status_code == 200
    row = next(item for item in listing.json["items"] if item["id"] == category["id"])
    assert row["bookCount"] == 1
    assert row["publishedBookCount"] == 0
    assert row["draftBookCount"] == 1
    assert row["collectionCount"] == 1
    assert book["categoryId"] == category["id"]


def test_category_can_be_deactivated_without_published_books_and_draft_is_preserved(app):
    client, csrf = admin_client(app, "category-deactivate-admin@example.test")
    category = create_category(client, csrf, slug="safe-deactivate")
    book = create_draft_book(client, csrf, category["id"])

    response = client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"isPublished": False},
        headers=csrf,
    )
    assert response.status_code == 200, response.get_json()
    assert response.json["category"]["isPublished"] is False
    with app.app_context():
        persisted_book = db.session.get(BookProduct, book["id"])
        assert persisted_book.category_id == category["id"]
        assert persisted_book.is_active is False
    updated_draft = client.patch(
        f"/api/v1/admin/books/{book['id']}",
        json={"description": "Updated while the category is inactive"},
        headers=csrf,
    )
    assert updated_draft.status_code == 200, updated_draft.get_json()
    assert updated_draft.json["book"]["description"] == "Updated while the category is inactive"
    activated = client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"isPublished": True},
        headers=csrf,
    )
    assert activated.status_code == 200
    assert activated.json["category"]["isPublished"] is True


def test_category_can_be_deactivated_when_it_has_no_references(app):
    client, csrf = admin_client(app, "category-empty-deactivate-admin@example.test")
    category = create_category(client, csrf, slug="empty-deactivate")

    response = client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"isPublished": False},
        headers=csrf,
    )
    assert response.status_code == 200
    assert response.json["category"]["isPublished"] is False


def test_category_deactivation_is_blocked_for_published_books_without_mutation(app):
    client, csrf = admin_client(app, "category-published-admin@example.test")
    category = create_category(client, csrf, slug="published-book-category")
    book = create_draft_book(client, csrf, category["id"])
    with app.app_context():
        persisted_book = db.session.get(BookProduct, book["id"])
        persisted_book.is_active = True
        db.session.commit()

    response = client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"isPublished": False},
        headers=csrf,
    )
    assert response.status_code == 409
    assert response.json["error"]["details"]["publishedBooks"] == 1
    with app.app_context():
        persisted_category = db.session.get(BookCategory, category["id"])
        persisted_book = db.session.get(BookProduct, book["id"])
        assert persisted_category.is_active is True
        assert persisted_book.is_active is True
        assert persisted_book.category_id == category["id"]


def test_category_deletion_is_blocked_for_product_and_collection_references(app):
    client, csrf = admin_client(app, "category-delete-admin@example.test")
    category = create_category(client, csrf, slug="referenced-category")
    book = create_draft_book(client, csrf, category["id"])
    with app.app_context():
        db.session.add(BookCollection(
            name="Referenced collection",
            slug="referenced-collection",
            category_id=category["id"],
            related_categories=[category["slug"]],
        ))
        db.session.commit()

    response = client.delete(f"/api/v1/admin/categories/{category['id']}", headers=csrf)
    assert response.status_code == 409
    assert response.json["error"]["details"] == {"books": 1, "collections": 1}
    with app.app_context():
        persisted_category = db.session.get(BookCategory, category["id"])
        persisted_book = db.session.get(BookProduct, book["id"])
        assert persisted_category.deleted_at is None
        assert persisted_book.category_id == category["id"]


def test_category_deletion_without_references_remains_a_soft_delete(app):
    client, csrf = admin_client(app, "category-soft-delete-admin@example.test")
    category = create_category(client, csrf, slug="unused-category")

    response = client.delete(f"/api/v1/admin/categories/{category['id']}", headers=csrf)
    assert response.status_code == 204
    with app.app_context():
        persisted_category = db.session.get(BookCategory, category["id"])
        assert persisted_category.deleted_at is not None
        assert persisted_category.is_active is False


def test_category_deletion_ignores_soft_deleted_books_and_collections(app):
    client, csrf = admin_client(app, "category-delete-soft-references@example.test")
    category = create_category(client, csrf, slug="soft-referenced-category")
    book = create_draft_book(client, csrf, category["id"])
    collection_response = client.post(
        "/api/v1/admin/collections",
        json={
            "name": "Soft deleted collection",
            "slug": "soft-deleted-category-collection",
            "categoryId": category["id"],
            "relatedCategories": [category["slug"]],
        },
        headers=csrf,
    )
    assert collection_response.status_code == 201, collection_response.get_json()

    assert client.delete(f"/api/v1/admin/books/{book['id']}", headers=csrf).status_code == 204
    assert client.delete(
        f"/api/v1/admin/collections/{collection_response.json['collection']['id']}",
        headers=csrf,
    ).status_code == 204

    deleted = client.delete(f"/api/v1/admin/categories/{category['id']}", headers=csrf)

    assert deleted.status_code == 204, deleted.get_json()
    with app.app_context():
        persisted_category = db.session.get(BookCategory, category["id"])
        assert persisted_category.deleted_at is not None


def test_renaming_category_preserves_collection_json_references(app):
    client, csrf = admin_client(app, "category-rename-admin@example.test")
    category = create_category(client, csrf, slug="old-category-slug")
    with app.app_context():
        collection = BookCollection(
            name="Renamed category collection",
            slug="renamed-category-collection",
            related_categories=[category["slug"]],
        )
        db.session.add(collection)
        db.session.commit()
        collection_id = collection.id

    response = client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"slug": "new-category-slug"},
        headers=csrf,
    )
    assert response.status_code == 200
    with app.app_context():
        persisted_collection = db.session.get(BookCollection, collection_id)
        assert persisted_collection.related_categories == ["new-category-slug"]


def test_public_category_serializer_does_not_expose_private_project_asset(app, client):
    with app.app_context():
        category = BookCategory(
            name="Private asset category",
            slug="private-asset-category",
            hero_asset_key="projects/user-id/project-id/private-image.webp",
        )
        db.session.add(category)
        db.session.commit()

    response = client.get("/api/v1/categories/private-asset-category")
    assert response.status_code == 200
    assert response.json["category"]["image"] is None


def test_category_mutation_requires_admin_role(app, client):
    category = create_category(*admin_client(app, "category-auth-admin@example.test"), slug="auth-category")
    assert client.patch(
        f"/api/v1/admin/categories/{category['id']}",
        json={"isPublished": False},
    ).status_code == 401
    customer, csrf = admin_client(app, "category-auth-customer@example.test", assign_admin=False)
    assert customer.delete(
        f"/api/v1/admin/categories/{category['id']}",
        headers=csrf,
    ).status_code == 403


def admin_client(app, email="admin@example.test", *, assign_admin=True):
    client = app.test_client()
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery"})
    assert response.status_code == 201
    code = re.search(r"\b(\d{6})\b", app.extensions["auth_email_outbox"][-1][2]).group(1)
    assert client.post("/api/v1/auth/verify-otp", json={"email": email, "code": code}).status_code == 200
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    assert login.status_code == 200
    csrf = next(
        value.split(";", 1)[0].split("=", 1)[1]
        for value in login.headers.getlist("Set-Cookie")
        if value.startswith("csrf_access_token=")
    )
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == email))
        if assign_admin:
            role = db.session.scalar(db.select(Role).where(Role.name == "admin"))
            if role is None:
                role = Role(name="admin", description="Admin", is_system=True)
                db.session.add(role)
                db.session.flush()
            db.session.add(UserRole(user_id=user.id, role_id=role.id))
        db.session.commit()
    return client, {"X-CSRF-TOKEN": csrf}


def test_pricing_catalog_crud_validation_and_variant_compatibility(app):
    client, csrf = admin_client(app, "pricing-catalog-admin@example.test")
    invalid_tier = client.post(
        "/api/v1/admin/pricing/tier",
        json={"code": "BASIC", "name": "Basic", "basePrice": "-1", "currency": "US"},
        headers=csrf,
    )
    assert invalid_tier.status_code == 400

    tier_response = client.post(
        "/api/v1/admin/pricing/tier",
        json={"code": "BASIC", "name": "Basic", "description": "Standard print tier", "basePrice": "9.00", "currency": "PKR"},
        headers=csrf,
    )
    assert tier_response.status_code == 201
    tier_id = tier_response.json["item"]["id"]
    duplicate_tier = client.post(
        "/api/v1/admin/pricing/tier",
        json={"code": "BASIC", "name": "Another basic", "basePrice": "0", "currency": "PKR"},
        headers=csrf,
    )
    assert duplicate_tier.status_code == 409

    band_response = client.post(
        "/api/v1/admin/pricing/pagePricing",
        json={"tierId": tier_id, "minimumPages": 24, "maximumPages": 40, "pricePerPage": "0.50"},
        headers=csrf,
    )
    assert band_response.status_code == 201
    overlap = client.post(
        "/api/v1/admin/pricing/pagePricing",
        json={"tierId": tier_id, "minimumPages": 40, "maximumPages": 80, "pricePerPage": "0.75"},
        headers=csrf,
    )
    assert overlap.status_code == 409
    assert client.patch(
        f"/api/v1/admin/pricing/tier/{tier_id}",
        json={"active": False},
        headers=csrf,
    ).status_code == 200

    shipping_response = client.post(
        "/api/v1/admin/pricing/shipping",
        json={
            "countryCode": "us", "serviceCode": "standard", "serviceName": "Standard",
            "price": "5.25", "currency": "PKR", "estimatedDaysMin": 3, "estimatedDaysMax": 7,
        },
        headers=csrf,
    )
    assert shipping_response.status_code == 201
    shipping = next(
        item for item in client.get("/api/v1/admin/pricing").json["shipping"]
        if item["serviceCode"] == "standard"
    )
    assert shipping["countryCode"] == "US"
    assert shipping["estimatedDaysMin"] == 3
    assert shipping["estimatedDaysMax"] == 7
    alternate_shipping = client.post(
        "/api/v1/admin/pricing/shipping",
        json={
            "countryCode": "US", "serviceCode": "express", "serviceName": "Express",
            "price": "8.00", "currency": "PKR",
        },
        headers=csrf,
    )
    assert alternate_shipping.status_code == 201
    duplicate_shipping_update = client.patch(
        f"/api/v1/admin/pricing/shipping/{alternate_shipping.json['item']['id']}",
        json={"serviceCode": "standard"},
        headers=csrf,
    )
    assert duplicate_shipping_update.status_code == 409

    category = create_category(client, csrf, slug="pricing-variant-category")
    book = create_draft_book(client, csrf, category["id"])
    size = client.post(
        "/api/v1/admin/pricing/size",
        json={"code": "square-8", "name": "8 inch square", "widthMm": "203.20", "heightMm": "203.20"},
        headers=csrf,
    )
    cover = client.post(
        "/api/v1/admin/pricing/cover",
        json={"name": "Linen hardback", "description": "Linen finish"},
        headers=csrf,
    )
    paper = client.post(
        "/api/v1/admin/pricing/paper",
        json={"name": "Matte", "weightGsm": 170},
        headers=csrf,
    )
    assert (size.status_code, cover.status_code, paper.status_code) == (201, 201, 201)
    variant_payload = {
        "sku": "PRICING-TEST-8-LINEN",
        "productId": book["id"],
        "sizeId": size.json["item"]["id"],
        "coverTypeId": cover.json["item"]["id"],
        "paperTypeId": paper.json["item"]["id"],
        "basePrice": "20.00",
        "currency": "PKR",
    }
    variant = client.post("/api/v1/admin/pricing/variants", json=variant_payload, headers=csrf)
    assert variant.status_code == 201
    variant_id = variant.json["variant"]["id"]
    duplicate_variant = client.post("/api/v1/admin/pricing/variants", json=variant_payload, headers=csrf)
    assert duplicate_variant.status_code == 409
    currency_mismatch = client.patch(
        f"/api/v1/admin/pricing/variant/{variant_id}",
        json={"currency": "USD"},
        headers=csrf,
    )
    assert currency_mismatch.status_code == 400


def test_print_quote_uses_catalog_price_components_and_product_page_limits(app, monkeypatch):
    client, csrf = admin_client(app, "pricing-quote-admin@example.test")
    category = create_category(client, csrf, slug="pricing-quote-category")
    book = create_draft_book(client, csrf, category["id"])
    with app.app_context():
        product = db.session.get(BookProduct, book["id"])
        product.is_active = True
        product.currency = "PKR"
        product.starting_price = Decimal("10.10")
        product.page_count_min = 24
        product.page_count_max = 80
        product.admin_metadata = {
            "dimensions": {"widthMm": "203.20", "heightMm": "203.20"},
            "printingTiers": ["BASIC"],
            "productionDays": 5,
            "basePageCount": 30,
            "extraPagePrice": "0.33",
            "pdfPrice": "12.50",
        }
        user = db.session.scalar(db.select(User).where(User.email == "pricing-quote-admin@example.test"))
        project = UserProject(
            user_id=user.id,
            product_id=product.id,
            title="Configured quote",
            page_count=30,
            version=1,
            document={"book": {"size": {"width": "8", "height": "8"}}, "pages": []},
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    size = client.post(
        "/api/v1/admin/pricing/size",
        json={"code": "quote-square-8", "name": "Quote 8 inch square", "widthMm": "203.20", "heightMm": "203.20"},
        headers=csrf,
    ).json["item"]
    cover = client.post(
        "/api/v1/admin/pricing/cover",
        json={"name": "Quote Linen hardback"},
        headers=csrf,
    ).json["item"]
    paper = client.post(
        "/api/v1/admin/pricing/paper",
        json={"name": "Quote Premium matte"},
        headers=csrf,
    ).json["item"]
    tier = client.post(
        "/api/v1/admin/pricing/tier",
        json={"code": "BASIC", "name": "Quote Basic", "basePrice": "999.99", "currency": "PKR"},
        headers=csrf,
    ).json["item"]
    band = client.post(
        "/api/v1/admin/pricing/pagePricing",
        json={"tierId": tier["id"], "minimumPages": 24, "maximumPages": 80, "pricePerPage": "0.33"},
        headers=csrf,
    )
    assert band.status_code == 201
    shipping = client.post(
        "/api/v1/admin/pricing/shipping",
        json={
            "countryCode": "US", "serviceCode": "quote-standard", "serviceName": "Quote standard",
            "price": "4.50", "currency": "PKR", "estimatedDaysMin": 3, "estimatedDaysMax": 7,
        },
        headers=csrf,
    )
    assert shipping.status_code == 201
    variant = client.post(
        "/api/v1/admin/pricing/variants",
        json={
            "sku": "QUOTE-BOOK-8-LINEN",
            "productId": book["id"],
            "sizeId": size["id"],
            "coverTypeId": cover["id"],
            "paperTypeId": paper["id"],
            "basePrice": "20.20",
            "currency": "PKR",
        },
        headers=csrf,
    )
    assert variant.status_code == 201

    discount = client.post(
        "/api/v1/admin/discount-codes",
        json={"code": "SAVE5", "type": "fixed", "value": "5.00", "currency": "PKR"},
        headers=csrf,
    )
    assert discount.status_code == 201, discount.get_json()
    quote_payload = {
        "projectId": project_id,
        "configuration": {
            "tier": "basic",
            "cover": "Quote Linen hardback",
            "paper": "Quote Premium matte",
            "quantity": 2,
            "discountCode": "SAVE5",
        },
        "shippingAddress": {
            "fullName": "MemoryBook Admin",
            "line1": "1 Paper Lane",
            "line2": "",
            "city": "Portland",
            "region": "Oregon",
            "postalCode": "97201",
            "country": "US",
            "phone": "555-0100",
        },
    }
    quote = client.post("/api/v1/print/quotes", json=quote_payload, headers=csrf)
    assert quote.status_code == 200, quote.get_json()
    assert quote.json["bookPrice"] == "20.20"
    assert quote.json["printingCharge"] == "40.40"
    assert quote.json["additionalPages"] == "0.00"
    assert quote.json["shipping"] == "9.00"
    assert quote.json["discount"] == "5.00"
    assert quote.json["total"] == "64.60"
    assert quote.json["currency"] == "PKR"
    editor_quote = client.get(f"/api/v1/projects/{project_id}/pricing-quote?pageCount=50")
    assert editor_quote.status_code == 200, editor_quote.get_json()
    assert editor_quote.json["pdfPrice"] == "12.50"
    assert editor_quote.json["extraPageCount"] == 20
    assert editor_quote.json["hardCopyEstimate"] == "36.90"

    from memorybook.services import orders, payments

    monkeypatch.setattr(orders, "provider_for", lambda *args: None)
    monkeypatch.setattr(
        payments,
        "create_payment",
        lambda order, *args, **kwargs: {"id": order.id, "total": str(order.total_amount)},
    )
    tampered_total = client.post(
        "/api/v1/print/orders",
        json={
            **quote_payload,
            "quoteId": quote.json["id"],
            "total": "0.01",
        },
        headers={**csrf, "Idempotency-Key": "tampered-price-check"},
    )
    assert tampered_total.status_code == 201, tampered_total.get_json()
    assert tampered_total.json["total"] == quote.json["total"]
    with app.app_context():
        discount_record = db.session.scalar(db.select(DiscountCode).where(DiscountCode.code == "SAVE5"))
        assert discount_record.uses_count == 1

    with app.app_context():
        project = db.session.get(UserProject, project_id)
        project.page_count = 50
        db.session.commit()
    updated_page_count_quote = client.post("/api/v1/print/quotes", json=quote_payload, headers=csrf)
    assert updated_page_count_quote.status_code == 200, updated_page_count_quote.get_json()
    assert updated_page_count_quote.json["pageCount"] == 50
    assert updated_page_count_quote.json["additionalPages"] == "13.20"
    assert updated_page_count_quote.json["total"] == "77.80"

    with app.app_context():
        product = db.session.get(BookProduct, book["id"])
        product.admin_metadata = {**product.admin_metadata, "sizeOptions": ["different-size-id"]}
        db.session.commit()
    disabled_variant_option = client.post("/api/v1/print/quotes", json=quote_payload, headers=csrf)
    assert disabled_variant_option.status_code == 409
    assert "no longer enabled" in disabled_variant_option.json["error"]["message"]

    with app.app_context():
        product = db.session.get(BookProduct, book["id"])
        product.admin_metadata = {**product.admin_metadata, "sizeOptions": [size["id"]]}
        db.session.commit()
        project = db.session.get(UserProject, project_id)
        project.page_count = 81
        db.session.commit()
    out_of_range = client.post("/api/v1/print/quotes", json=quote_payload, headers=csrf)
    assert out_of_range.status_code == 409
    assert "cannot exceed" in out_of_range.json["error"]["message"]


def add_design_element(document):
    page = next(page for page in document["pages"] if page["type"] != "cover")
    page["elements"].append({
        "id": "master-title",
        "type": "text",
        "text": "A story worth keeping",
        "x": 0.1,
        "y": 0.1,
        "width": 0.8,
        "height": 0.12,
    })


def test_admin_apis_require_admin_role(app, client):
    response = client.get("/api/v1/admin/dashboard")
    assert response.status_code == 401
    customer, _ = admin_client(app, "customer@example.test", assign_admin=False)
    response = customer.get("/api/v1/admin/dashboard")
    assert response.status_code == 403


def test_admin_catalog_image_upload_is_validated_and_stored_as_public_catalog_asset(app):
    client, csrf = admin_client(app, "assets-admin@example.test")
    storage = FakeStorage()
    app.extensions["asset_storage"] = storage
    response = client.post(
        "/api/v1/admin/assets",
        data={"file": (BytesIO(valid_png()), "cover.png")},
        headers=csrf,
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    asset = response.json["asset"]
    assert asset["assetKey"].startswith("catalog/")
    assert asset["url"].startswith("https://assets.example.test/")
    assert storage.objects[asset["assetKey"]][1] == "image/png"

    invalid = client.post(
        "/api/v1/admin/assets",
        data={"file": (BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16), "cover.png")},
        headers=csrf,
        content_type="multipart/form-data",
    )
    assert invalid.status_code == 400


def test_admin_design_upload_is_private_to_its_admin(app, tmp_path):
    app.config["ASSET_STORAGE_BACKEND"] = "filesystem"
    app.config["ASSET_LOCAL_DIRECTORY"] = str(tmp_path)
    admin, csrf = admin_client(app, "private-design-admin@example.test")
    customer, _ = admin_client(app, "private-design-customer@example.test", assign_admin=False)

    response = admin.post(
        "/api/v1/admin/design-assets",
        data={"file": (BytesIO(valid_png()), "draft-design.png")},
        headers=csrf,
        content_type="multipart/form-data",
    )

    assert response.status_code == 201, response.get_json()
    asset = response.json["asset"]
    assert asset["assetKey"].startswith("admin-design/")
    asset_path = urlsplit(asset["url"]).path
    assert admin.get(asset_path).status_code == 200
    assert customer.get(asset_path).status_code == 404
    with app.app_context():
        db.session.add(BookTemplate(
            name="Published asset access",
            slug="published-asset-access",
            is_active=True,
            published_design_document={"assets": [{"assetKey": asset["assetKey"]}]},
        ))
        db.session.commit()
    assert customer.get(asset_path).status_code == 200


def test_local_catalog_asset_url_is_stable_and_public(app, tmp_path):
    app.config["ASSET_STORAGE_BACKEND"] = "filesystem"
    app.config["ASSET_LOCAL_DIRECTORY"] = str(tmp_path)
    app.config["ASSET_S3_PRESIGNED_URL_TTL"] = 1
    admin, csrf = admin_client(app, "stable-catalog-admin@example.test")
    uploaded = admin.post(
        "/api/v1/admin/assets",
        data={"file": (BytesIO(valid_png()), "catalog-cover.png")},
        headers=csrf,
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    url = uploaded.json["asset"]["url"]

    time.sleep(1.1)
    response = app.test_client().get(urlsplit(url).path)
    assert response.status_code == 200
    Image.open(BytesIO(response.data)).verify()


def configure_product_for_publication(app, client, csrf, product, *, sku):
    with app.app_context():
        size = BookSize(code=f"{sku.lower()}-size", name=f"{sku} size", width_mm=203, height_mm=203)
        cover = CoverType(name=f"{sku} cover")
        paper = PaperType(name=f"{sku} paper", weight_gsm=170)
        tier = PricingTier(code="BASIC", name="Basic", base_price=Decimal("10.00"), currency="PKR")
        db.session.add_all([size, cover, paper, tier])
        db.session.flush()
        db.session.add_all([
            PagePricing(tier_id=tier.id, minimum_pages=24, maximum_pages=80, price_per_page=Decimal("0.50")),
            ShippingRate(
                country_code="US", service_code=f"{sku.lower()}-standard", service_name="Standard",
                price=Decimal("5.00"), currency="PKR", is_active=True,
            ),
        ])
        size_id, cover_id, paper_id = size.id, cover.id, paper.id
        db.session.commit()
    updated = client.patch(
        f"/api/v1/admin/books/{product['id']}",
        json={
            "coverAssetKey": "catalog/test-cover.jpg",
            "pageCountMin": 24,
            "pageCountMax": 80,
            "adminMetadata": {
                "dimensions": {"widthMm": "203.00", "heightMm": "203.00"},
                "pageCountOptions": [24, 32, 40],
                "sizeOptions": [size_id],
                "coverOptions": [cover_id],
                "paperOptions": [paper_id],
                "printingTiers": ["BASIC"],
                "previewImageKeys": [],
                "pdfPrice": "0.00",
                "printingPrice": "0.00",
                "productionDays": 10,
            },
        },
        headers=csrf,
    )
    assert updated.status_code == 200, updated.get_json()
    variant = client.post(
        "/api/v1/admin/pricing/variants",
        json={
            "sku": sku, "productId": product["id"], "sizeId": size_id, "coverTypeId": cover_id,
            "paperTypeId": paper_id, "basePrice": "40.00", "currency": "PKR",
        },
        headers=csrf,
    )
    assert variant.status_code == 201, variant.get_json()
    return client.post(f"/api/v1/admin/books/{product['id']}/publish", headers=csrf)


def test_local_filesystem_catalog_upload_can_be_retrieved(app, tmp_path):
    app.config["ASSET_STORAGE_BACKEND"] = "filesystem"
    app.config["ASSET_LOCAL_DIRECTORY"] = str(tmp_path)
    client, csrf = admin_client(app, "local-assets-admin@example.test")
    image = valid_png()

    response = client.post(
        "/api/v1/admin/assets",
        data={"file": (BytesIO(image), "local-cover.png")},
        headers=csrf,
        content_type="multipart/form-data",
    )

    assert response.status_code == 201, response.get_json()
    asset = response.json["asset"]
    assert asset["assetKey"].startswith("catalog/")
    assert asset["url"].startswith("/api/v1/assets/public/catalog/")
    retrieved = client.get(urlsplit(asset["url"]).path)
    assert retrieved.status_code == 200
    Image.open(BytesIO(retrieved.data)).verify()
    assert retrieved.mimetype == "image/png"


def test_local_asset_retrieval_rejects_invalid_and_expired_signatures(app, tmp_path):
    app.config["ASSET_STORAGE_BACKEND"] = "filesystem"
    app.config["ASSET_LOCAL_DIRECTORY"] = str(tmp_path)
    app.config["ASSET_S3_PRESIGNED_URL_TTL"] = 1
    client, _ = admin_client(app, "expiring-local-assets-admin@example.test")
    from memorybook.integrations.asset_storage import LocalFilesystemAssetStorage

    with app.app_context():
        asset_path = urlsplit(LocalFilesystemAssetStorage().download_url("catalog/expired")).path

    invalid = client.get("/api/v1/assets/not-a-valid-signature")
    assert invalid.status_code == 404

    time.sleep(2.1)
    expired = client.get(asset_path)
    assert expired.status_code == 404


def test_admin_book_and_template_workflow_preserves_published_template_versions(app):
    client, csrf = admin_client(app)
    category_response = client.post(
        "/api/v1/admin/categories",
        json={"name": "Travel", "slug": "travel-admin", "description": "Travel books", "isPublished": True},
        headers=csrf,
    )
    assert category_response.status_code == 201
    category_id = category_response.json["category"]["id"]
    book_response = client.post(
        "/api/v1/admin/books",
        json={
            "title": "Alpine Notes", "slug": "alpine-notes", "description": "A trip book",
            "categoryId": category_id, "startingPrice": "39.00", "pageCountMin": 24,
            "pageCountMax": 80, "adminMetadata": {"pdfPrice": "8.00", "productionDays": 7},
        },
        headers=csrf,
    )
    assert book_response.status_code == 201
    book = book_response.json["book"]
    assert book["isPublished"] is False
    assert client.get("/api/v1/books/alpine-notes").status_code == 404
    design = client.post(f"/api/v1/admin/books/{book['id']}/design", headers=csrf)
    assert design.status_code == 200
    design_document = design.json["template"]["designDocument"]
    assert len(design_document["pages"]) == 25
    add_design_element(design_document)
    saved_design = client.put(
        f"/api/v1/admin/books/{book['id']}/design",
        json={"document": design_document},
        headers={**csrf, "If-Match": '"1"'},
    )
    assert saved_design.status_code == 200
    assert saved_design.json["template"]["version"] == 2
    assert client.post(
        f"/api/v1/admin/books/{book['id']}/design/publish",
        headers={**csrf, "If-Match": '"2"'},
    ).status_code == 200
    assert client.get("/api/v1/books/alpine-notes").status_code == 404
    assert client.get(f"/api/v1/templates/{design.json['template']['id']}").status_code == 404
    incomplete_publish = client.post(f"/api/v1/admin/books/{book['id']}/publish", headers=csrf)
    assert incomplete_publish.status_code == 400
    assert incomplete_publish.json["error"]["details"]["coverAssetKey"] == "required"
    assert client.get(f"/api/v1/admin/books?categoryId={category_id}").json["pagination"]["totalItems"] == 1
    with app.app_context():
        size = BookSize(code="square-8", name="8 inch square", width_mm=203.2, height_mm=203.2)
        cover = CoverType(name="Linen hardback")
        paper = PaperType(name="Premium matte", weight_gsm=170)
        tier = PricingTier(code="BASIC", name="Basic", base_price=Decimal("24.00"))
        db.session.add_all([size, cover, paper, tier])
        db.session.commit()
        size_id, cover_id, paper_id, tier_id = size.id, cover.id, paper.id, tier.id
    specification_update = client.patch(
        f"/api/v1/admin/books/{book['id']}",
        json={"adminMetadata": {
            "dimensions": {"widthMm": "203.20", "heightMm": "203.20"},
            "sizeOptions": [size_id], "coverOptions": [cover_id], "paperOptions": [paper_id],
            "pageCountOptions": [24, 32, 40], "printingTiers": ["BASIC"],
            "previewImageKeys": ["catalog/alpine-preview.jpg"], "pdfPrice": "8.00",
            "printingPrice": "44.50", "productionDays": 7,
        }, "coverAssetKey": "catalog/alpine-cover.jpg"},
        headers=csrf,
    )
    assert specification_update.status_code == 200
    assert specification_update.json["book"]["adminMetadata"]["dimensions"]["widthMm"] == "203.20"
    partial_metadata_update = client.patch(
        f"/api/v1/admin/books/{book['id']}",
        json={"adminMetadata": {"productionDays": 8}},
        headers=csrf,
    )
    assert partial_metadata_update.status_code == 200
    assert partial_metadata_update.json["book"]["adminMetadata"]["sizeOptions"] == [size_id]
    assert partial_metadata_update.json["book"]["adminMetadata"]["dimensions"]["widthMm"] == "203.20"
    signed_url_update = client.patch(
        f"/api/v1/admin/books/{book['id']}",
        json={"adminMetadata": {"previewImageKeys": ["https://assets.example.test/temporary?signature=test"]}},
        headers=csrf,
    )
    assert signed_url_update.status_code == 400
    variant = client.post(
        "/api/v1/admin/pricing/variants",
        json={"sku": "ALPINE-8-LINEN-MATTE", "productId": book["id"], "sizeId": size_id, "coverTypeId": cover_id, "paperTypeId": paper_id, "basePrice": "44.50"},
        headers=csrf,
    )
    assert variant.status_code == 201
    variant_id = variant.json["variant"]["id"]
    assert client.patch(
        f"/api/v1/admin/pricing/variant/{variant_id}",
        json={"basePrice": "46.00"},
        headers=csrf,
    ).status_code == 200
    assert client.patch(
        f"/api/v1/admin/pricing/tier/{tier_id}",
        json={"basePrice": "26.50"},
        headers=csrf,
    ).status_code == 200
    assert client.post(
        "/api/v1/admin/pricing/pagePricing",
        json={"tierId": tier_id, "minimumPages": 24, "maximumPages": 80, "pricePerPage": "0.50"},
        headers=csrf,
    ).status_code == 201
    assert client.post(
        "/api/v1/admin/pricing/shipping",
        json={
            "countryCode": "US", "serviceCode": "alpine-standard", "serviceName": "Standard",
            "price": "5.00", "currency": "PKR",
        },
        headers=csrf,
    ).status_code == 201
    product_publication = client.post(f"/api/v1/admin/books/{book['id']}/publish", headers=csrf)
    assert product_publication.status_code == 200, product_publication.get_json()
    assert client.get("/api/v1/books/alpine-notes").status_code == 200
    assert client.get(f"/api/v1/templates/{design.json['template']['id']}").status_code == 200
    blocked_design_unpublish = client.post(f"/api/v1/admin/books/{book['id']}/design/unpublish", headers=csrf)
    assert blocked_design_unpublish.status_code == 409
    unpublished_product = client.post(f"/api/v1/admin/books/{book['id']}/unpublish", headers=csrf)
    assert unpublished_product.status_code == 200
    assert unpublished_product.json["book"]["isPublished"] is False
    assert client.get("/api/v1/books/alpine-notes").status_code == 404
    preserved_design = client.post(f"/api/v1/admin/books/{book['id']}/design", headers=csrf)
    assert preserved_design.status_code == 200
    assert preserved_design.json["template"]["published"] is True
    republished_product = client.post(f"/api/v1/admin/books/{book['id']}/publish", headers=csrf)
    assert republished_product.status_code == 200
    discount = client.post(
        "/api/v1/admin/discount-codes",
        json={"code": "BOOKS10", "type": "percent", "value": "10"},
        headers=csrf,
    )
    assert discount.status_code == 201
    with app.app_context():
        assert db.session.scalar(db.select(DiscountCode).where(DiscountCode.code == "BOOKS10")).value == Decimal("10.00")


    template = client.post(
        "/api/v1/admin/templates",
        json={
            "name": "Alpine Journal", "slug": "alpine-journal", "categoryId": category_id,
            "pages": [{
                "pageNumber": 1, "type": "cover", "layout": "cover-photo",
                "elements": [{
                    "type": "image", "x": 0, "y": 0, "width": 1, "height": 1,
                    "content": {"placeholder": "cover"},
                }],
            }],
        },
        headers=csrf,
    )
    assert template.status_code == 201
    template_id = template.json["template"]["id"]
    assert client.get(f"/api/v1/templates/{template_id}").status_code == 404
    assert client.post(f"/api/v1/admin/templates/{template_id}/publish", headers=csrf).status_code == 200
    with app.app_context():
        project = UserProject(
            user_id=db.session.scalar(db.select(User).where(User.email == "admin@example.test")).id,
            template_id=template_id,
            template_version=1,
            title="Existing project",
            page_count=1,
            document={"pages": [{"id": "saved-page", "elements": []}]},
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    updated = client.patch(
        f"/api/v1/admin/templates/{template_id}",
        json={"description": "Revised design"},
        headers=csrf,
    )
    assert updated.status_code == 200
    assert updated.json["template"]["version"] == 2
    versions = client.get(f"/api/v1/admin/templates/{template_id}/versions")
    assert versions.status_code == 200
    assert versions.json["items"][0]["version"] == 1
    assert versions.json["items"][0]["document"]["description"] is None
    with app.app_context():
        saved_project = db.session.get(UserProject, project_id)
        assert saved_project.template_version == 1
        assert saved_project.document == {"pages": [{"id": "saved-page", "elements": []}]}
        assert db.session.scalar(db.select(BookTemplateVersion).where(BookTemplateVersion.template_id == template_id))


def test_deleting_book_hides_linked_template_without_breaking_project_or_order(app):
    client, csrf = admin_client(app, "delete-book-template-admin@example.test")
    category = create_category(client, csrf, slug="delete-template-category")
    book = create_draft_book(client, csrf, category["id"])
    design = client.post(f"/api/v1/admin/books/{book['id']}/design", headers=csrf)
    assert design.status_code == 200, design.get_json()
    template_id = design.json["template"]["id"]

    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "delete-book-template-admin@example.test"))
        project = UserProject(
            user_id=user.id,
            product_id=book["id"],
            template_id=template_id,
            title="Project based on deleted book",
            page_count=24,
            version=1,
            document={"schemaVersion": 1, "metadata": {"title": "Project based on deleted book"}, "pages": []},
        )
        db.session.add(project)
        db.session.flush()
        revision = ProjectRevision(
            project_id=project.id,
            revision_number=1,
            document_version=1,
            document=project.document,
            checksum_sha256="a" * 64,
        )
        db.session.add(revision)
        db.session.flush()
        order = PdfOrder(
            order_number="PDF-DELETE-TEMPLATE-TEST",
            user_id=user.id,
            project_id=project.id,
            project_revision_id=revision.id,
            status="pending",
            currency="PKR",
            service_price=Decimal("850.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("850.00"),
            price_snapshot={"pdfProfiles": ["digital"]},
            page_count=24,
        )
        db.session.add(order)
        db.session.commit()
        project_id, order_id = project.id, order.id

    deleted = client.delete(f"/api/v1/admin/books/{book['id']}", headers=csrf)

    assert deleted.status_code == 204
    listed_templates = client.get("/api/v1/admin/templates")
    assert listed_templates.status_code == 200
    assert template_id not in {template["id"] for template in listed_templates.json["items"]}
    with app.app_context():
        template = db.session.get(BookTemplate, template_id)
        project = db.session.get(UserProject, project_id)
        order = db.session.get(PdfOrder, order_id)
        assert template is not None
        assert template.deleted_at is not None
        assert template.is_active is False
        assert project.template_id == template_id
        assert order.project_id == project_id


def test_template_publication_requires_a_valid_design(app):
    client, csrf = admin_client(app, "template-admin@example.test")
    created = client.post(
        "/api/v1/admin/templates",
        json={"name": "Empty", "slug": "empty-template", "pages": []},
        headers=csrf,
    )
    template_id = created.json["template"]["id"]
    rejected = client.post(f"/api/v1/admin/templates/{template_id}/publish", headers=csrf)
    assert rejected.status_code == 400
    assert client.get("/api/v1/templates/empty-template").status_code == 404


def test_book_design_requires_admin_and_saved_valid_design_before_publication(app, client):
    admin, csrf = admin_client(app, "book-design-admin@example.test")
    customer, customer_csrf = admin_client(app, "book-design-customer@example.test", assign_admin=False)
    category = admin.post(
        "/api/v1/admin/categories",
        json={"name": "Family", "slug": "family-design"},
        headers=csrf,
    ).json["category"]
    book = admin.post(
        "/api/v1/admin/books",
        json={
            "title": "Family Keepsake", "slug": "family-keepsake",
            "description": "A family book", "categoryId": category["id"],
        },
        headers=csrf,
    ).json["book"]
    design_url = f"/api/v1/admin/books/{book['id']}/design"

    assert client.post(design_url).status_code == 401
    assert customer.post(design_url, headers=customer_csrf).status_code == 403
    initial = admin.post(design_url, headers=csrf)
    assert initial.status_code == 200
    assert admin.post(
        f"{design_url}/publish",
        headers={**csrf, "If-Match": '"1"'},
    ).status_code == 400
    assert admin.put(
        design_url,
        json={"document": initial.json["template"]["designDocument"]},
        headers=csrf,
    ).status_code == 428

    document = initial.json["template"]["designDocument"]
    invalid_document = dict(document)
    invalid_document["pages"] = [dict(page) for page in document["pages"]]
    invalid_document["pageOrder"] = list(document["pageOrder"])
    invalid_document["pages"][1]["elements"] = [{
        "id": "invalid-slot",
        "type": "shape",
        "shape": "photo-placeholder",
        "x": 0.8,
        "y": 0.1,
        "width": 0.3,
        "height": 0.5,
    }]
    out_of_bounds = admin.put(
        design_url,
        json={"document": invalid_document},
        headers={**csrf, "If-Match": '"1"'},
    )
    assert out_of_bounds.status_code == 400
    assert out_of_bounds.json["error"]["details"]["slot"] == "out_of_bounds"

    invalid_document["pages"][1]["elements"][0]["x"] = 0.1
    invalid_document["pages"][1]["elements"][0]["width"] = -0.2
    negative_size = admin.put(
        design_url,
        json={"document": invalid_document},
        headers={**csrf, "If-Match": '"1"'},
    )
    assert negative_size.status_code == 400

    invalid_document["pages"][1]["elements"] = [{
        "id": f"element-{index}",
        "type": "text",
        "text": "Design element",
        "x": 0.1,
        "y": 0.1,
        "width": 0.8,
        "height": 0.1,
    } for index in range(201)]
    too_many_elements = admin.put(
        design_url,
        json={"document": invalid_document},
        headers={**csrf, "If-Match": '"1"'},
    )
    assert too_many_elements.status_code == 400

    add_design_element(document)
    saved = admin.put(
        design_url,
        json={"document": document},
        headers={**csrf, "If-Match": '"1"'},
    )
    assert saved.status_code == 200
    stale = admin.put(
        design_url,
        json={"document": document},
        headers={**csrf, "If-Match": '"1"'},
    )
    assert stale.status_code == 409
    published = admin.post(
        f"{design_url}/publish",
        headers={**csrf, "If-Match": '"2"'},
    )
    assert published.status_code == 200
    assert published.json["product"]["isPublished"] is False
    assert published.json["template"]["published"] is True
    assert published.json["template"]["publishedVersion"] == 2
    assert admin.get("/api/v1/books/family-keepsake").status_code == 404
    assert admin.get(f"/api/v1/templates/{published.json['template']['id']}").status_code == 404


def test_product_publish_api_cannot_bypass_the_design_requirement(app):
    admin, csrf = admin_client(app, "book-publish-admin@example.test")
    category = admin.post(
        "/api/v1/admin/categories",
        json={"name": "Birthday", "slug": "birthday-design"},
        headers=csrf,
    ).json["category"]
    book = admin.post(
        "/api/v1/admin/books",
        json={"title": "Birthday Book", "slug": "birthday-book", "description": "A party book", "categoryId": category["id"]},
        headers=csrf,
    ).json["book"]
    response = admin.post(f"/api/v1/admin/books/{book['id']}/publish", headers=csrf)
    assert response.status_code == 400


def test_published_book_design_creates_independent_user_project_copy(app):
    storage = FakeStorage()
    app.extensions["asset_storage"] = storage
    admin, csrf = admin_client(app, "book-copy-admin@example.test")
    customer, customer_csrf = admin_client(app, "book-copy-customer@example.test", assign_admin=False)
    category = admin.post(
        "/api/v1/admin/categories",
        json={"name": "Travel", "slug": "travel-copy"},
        headers=csrf,
    ).json["category"]
    book = admin.post(
        "/api/v1/admin/books",
        json={"title": "Travel Master", "slug": "travel-master", "description": "A trip", "categoryId": category["id"]},
        headers=csrf,
    ).json["book"]
    design_url = f"/api/v1/admin/books/{book['id']}/design"
    initial = admin.post(design_url, headers=csrf)
    document = initial.json["template"]["designDocument"]
    add_design_element(document)
    image_bytes = b"master catalog image bytes"
    asset_key = "catalog/admin/master-photo"
    storage.objects[asset_key] = (image_bytes, "image/png")
    document["assets"] = [{
        "id": "master-photo",
        "assetKey": asset_key,
        "name": "Master photo.png",
        "mimeType": "image/png",
        "size": len(image_bytes),
        "checksum": hashlib.sha256(image_bytes).hexdigest(),
    }]
    document["pages"][1]["elements"].append({
        "id": "master-photo-element",
        "type": "image",
        "assetId": "master-photo",
        "src": "https://assets.example.test/temporary-preview",
        "name": "Master photo.png",
        "x": 0.1,
        "y": 0.3,
        "width": 0.8,
        "height": 0.6,
    })
    document["cover"]["design"]["front"]["photoAssetId"] = "master-photo"
    saved = admin.put(
        design_url,
        json={"document": document},
        headers={**csrf, "If-Match": '"1"'},
    )
    assert saved.status_code == 200
    template_id = saved.json["template"]["id"]
    assert admin.post(
        f"{design_url}/publish",
        headers={**csrf, "If-Match": '"2"'},
    ).status_code == 200
    assert customer.get(f"/api/v1/templates/{template_id}").status_code == 404
    unavailable_project = customer.post(
        "/api/v1/projects",
        json={"title": "Unavailable master", "pageCount": 24, "productId": book["id"], "templateId": template_id},
        headers=customer_csrf,
    )
    assert unavailable_project.status_code == 400
    product_publication = configure_product_for_publication(app, admin, csrf, book, sku="TRAVEL-MASTER")
    assert product_publication.status_code == 200, product_publication.get_json()

    with app.app_context():
        template = db.session.get(BookTemplate, template_id)
        master_text = template.published_design_document["pages"][1]["elements"][0]["text"]

    created = customer.post(
        "/api/v1/projects",
        json={"title": "My Travel Book", "pageCount": 24, "productId": book["id"], "templateId": template_id},
        headers=customer_csrf,
    )
    assert created.status_code == 201
    project = created.json["project"]
    assert project["templateVersion"] == 2
    assert project["document"]["pages"][1]["elements"][0]["text"] == master_text
    assert project["document"]["metadata"]["owner"] == "book-copy-customer@example.test"
    copied_asset_id = project["document"]["assets"][0]["id"]
    assert copied_asset_id != "master-photo"
    assert project["document"]["pages"][1]["elements"][1]["assetId"] == copied_asset_id
    assert project["document"]["cover"]["design"]["front"]["photoAssetId"] == copied_asset_id
    with app.app_context():
        copied_asset = db.session.get(ProjectAsset, copied_asset_id)
        assert copied_asset.storage_key != asset_key
        assert storage.objects[copied_asset.storage_key] == storage.objects[asset_key]

    changed_document = project["document"]
    changed_document["pages"][1]["elements"][0]["text"] = "My own title"
    updated = customer.patch(
        f"/api/v1/projects/{project['id']}",
        json={"document": changed_document},
        headers={**customer_csrf, "If-Match": '"1"'},
    )
    assert updated.status_code == 200
    with app.app_context():
        template = db.session.get(BookTemplate, template_id)
        assert template.published_design_document["pages"][1]["elements"][0]["text"] == master_text


def test_admin_can_suspend_users_and_soft_delete_catalog_records(app):
    admin, csrf = admin_client(app, "catalog-admin@example.test")
    customer, _ = admin_client(app, "managed-customer@example.test", assign_admin=False)
    users = admin.get("/api/v1/admin/users?search=managed-customer")
    customer_id = users.json["items"][0]["id"]
    assert admin.patch(
        f"/api/v1/admin/users/{customer_id}",
        json={"isActive": False},
        headers=csrf,
    ).status_code == 200
    assert customer.get("/api/v1/auth/me").status_code == 401

    category = admin.post(
        "/api/v1/admin/categories",
        json={"name": "Unused", "slug": "unused-category"},
        headers=csrf,
    ).json["category"]
    collection = admin.post(
        "/api/v1/admin/collections",
        json={"name": "Weekend", "slug": "weekend-collection", "categoryId": category["id"]},
        headers=csrf,
    ).json["collection"]
    assert admin.delete(f"/api/v1/admin/collections/{collection['id']}", headers=csrf).status_code == 204
    product = admin.post(
        "/api/v1/admin/books",
        json={"title": "Archive book", "slug": "archive-book", "description": "Not public", "categoryId": category["id"]},
        headers=csrf,
    ).json["book"]
    assert admin.post(f"/api/v1/admin/books/{product['id']}/publish", headers=csrf).status_code == 400
    assert admin.post(f"/api/v1/admin/books/{product['id']}/unpublish", headers=csrf).status_code == 200
    assert admin.delete(f"/api/v1/admin/books/{product['id']}", headers=csrf).status_code == 204
    category_delete = admin.delete(f"/api/v1/admin/categories/{category['id']}", headers=csrf)
    assert category_delete.status_code == 204
    assert admin.get("/api/v1/books/archive-book").status_code == 404
    with app.app_context():
        assert db.session.get(BookCategory, category["id"]).deleted_at is not None


def test_admin_manages_print_orders_support_settings_pricing_and_notifications(app):
    client, csrf = admin_client(app, "ops-admin@example.test")
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "ops-admin@example.test"))
        project = UserProject(
            user_id=user.id, title="Print proof", page_count=24,
            document={"schemaVersion": 1, "pages": [{"id": "page-a", "elements": []}]},
        )
        db.session.add(project)
        db.session.flush()
        revision = ProjectRevision(
            project_id=project.id, revision_number=1, document_version=1,
            document=project.document, checksum_sha256="a" * 64,
        )
        address = ShippingAddress(
            user_id=user.id, recipient_name="Studio Admin", address_line_1="1 Paper Lane",
            city="Portland", postal_code="97201", country_code="US",
        )
        db.session.add_all([revision, address])
        db.session.flush()
        order = PrintOrder(
            order_number="PRINT-101", user_id=user.id, project_id=project.id,
            project_revision_id=revision.id, shipping_address_id=address.id,
            shipping_address_snapshot={"city": "Portland"}, status="payment_confirmed",
            currency="USD", book_amount=Decimal("20.00"), printing_amount=Decimal("15.00"),
            shipping_amount=Decimal("5.00"), discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"), total_amount=Decimal("40.00"),
            price_snapshot={"total": "40.00"}, paid_at=datetime.now(UTC),
        )
        db.session.add(order)
        db.session.flush()
        payment = Payment(
            user_id=user.id, print_order_id=order.id, provider="test-provider",
            status="successful", amount=Decimal("40.00"), currency="USD",
        )
        pdf_order = PdfOrder(
            order_number="PDF-101", user_id=user.id, project_id=project.id,
            project_revision_id=revision.id, status="paid", currency="USD",
            service_price=Decimal("8.00"), discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"), total_amount=Decimal("8.00"),
            price_snapshot={"total": "8.00"}, page_count=24, paid_at=datetime.now(UTC),
        )
        db.session.add_all([payment, pdf_order])
        db.session.commit()
        order_id, pdf_order_id = order.id, pdf_order.id
        ticket = SupportTicket(
            ticket_number="TICKET-101", user_id=user.id, subject="Order question",
            category="orders", status="open",
        )
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id
    setting = client.post(
        "/api/v1/admin/settings",
        json={"key": "storefront.banner", "value": {"enabled": True}, "public": True},
        headers=csrf,
    )
    assert setting.status_code == 201
    assert client.get("/api/v1/admin/settings").json["items"][0]["value"] == {"enabled": True}
    support = client.patch(
        f"/api/v1/admin/support/{ticket_id}",
        json={"status": "in_progress", "reply": "We are checking the order."},
        headers=csrf,
    )
    assert support.status_code == 200
    assert support.json["ticket"]["status"] == "in_progress"
    assert client.get("/api/v1/admin/support").json["items"][0]["messages"][0]["body"] == "We are checking the order."
    orders = client.get("/api/v1/admin/orders?type=print")
    assert orders.status_code == 200
    assert orders.json["items"][0]["projectRevision"]["document"]["pages"][0]["id"] == "page-a"
    assert orders.json["items"][0]["photosAvailable"] is False
    shipment_update = client.patch(
        f"/api/v1/admin/orders/print/{order_id}",
        json={"status": "printed"},
        headers=csrf,
    )
    assert shipment_update.status_code == 409
    shipment_update = client.patch(
        f"/api/v1/admin/orders/print/{order_id}",
        json={"status": "processing"},
        headers=csrf,
    )
    assert shipment_update.status_code == 200
    assert client.patch(
        f"/api/v1/admin/orders/print/{order_id}",
        json={"status": "printed"},
        headers=csrf,
    ).status_code == 200
    assert client.patch(
        f"/api/v1/admin/orders/print/{order_id}",
        json={"status": "shipped", "carrier": "MemoryShip"},
        headers=csrf,
    ).status_code == 400
    shipment_update = client.patch(
        f"/api/v1/admin/orders/print/{order_id}",
        json={"status": "shipped", "carrier": "MemoryShip", "trackingNumber": "TRACK-101"},
        headers=csrf,
    )
    assert shipment_update.status_code == 200
    assert shipment_update.json["order"]["shipment"]["trackingNumber"] == "TRACK-101"
    assert client.patch(
        f"/api/v1/admin/orders/print/{order_id}",
        json={"status": "out_for_delivery"},
        headers=csrf,
    ).status_code == 200
    assert client.patch(
        f"/api/v1/admin/orders/print/{order_id}",
        json={"status": "delivered"},
        headers=csrf,
    ).status_code == 200
    duplicate_delivery = client.patch(
        f"/api/v1/admin/orders/print/{order_id}",
        json={"status": "delivered"},
        headers=csrf,
    )
    assert duplicate_delivery.status_code == 200
    assert client.get("/api/v1/admin/orders?type=pdf").json["items"][0]["orderNumber"] == "PDF-101"
    assert client.patch(
        f"/api/v1/admin/orders/pdf/{pdf_order_id}",
        json={"status": "cancelled"},
        headers=csrf,
    ).status_code == 409
    assert client.patch(
        f"/api/v1/admin/orders/pdf/{pdf_order_id}",
        json={"status": "cancellation_requested"},
        headers=csrf,
    ).status_code == 200
    user_notices = client.get("/api/v1/payments/notifications")
    assert user_notices.status_code == 200
    notice_messages = {item["title"]: item["message"] for item in user_notices.json["items"]}
    assert notice_messages["Your book is being prepared"] == "Your book is being prepared."
    assert notice_messages["Your book has been printed"] == "Your book has been printed."
    assert notice_messages["Your book has been shipped"] == "Your book has been shipped (tracking: TRACK-101)."
    assert notice_messages["Your book is out for delivery"] == "Your book is out for delivery."
    assert notice_messages["Your book has been delivered"] == "Your book has been delivered."
    assert sum(item["title"] == "Your book has been delivered" for item in user_notices.json["items"]) == 1
    with app.app_context():
        payment = db.session.scalar(db.select(Payment).where(Payment.print_order_id == order_id))
        payment.status = "succeeded"
        db.session.commit()
    assert client.get("/api/v1/admin/pricing").status_code == 200
    assert client.get("/api/v1/admin/payments").status_code == 200
    assert client.get("/api/v1/admin/refunds").status_code == 200
    notices = client.get("/api/v1/admin/notifications")
    assert any(item["title"] == "New support ticket" for item in notices.json["items"])
    assert any(item["title"] == "Print order placed" for item in notices.json["items"])
    assert any(item["title"] == "New paid print order" for item in notices.json["items"])
    assert any(item["title"] == "Payment failed" for item in notices.json["items"])
    assert any(item["title"] == "Payment confirmed" for item in notices.json["items"])
    assert any(item["title"] == "PDF purchased" for item in notices.json["items"])
    assert any(item["title"] == "Cancellation requested" for item in notices.json["items"])
    with app.app_context():
        event_email = db.session.scalar(
            db.select(EmailLog).where(
                EmailLog.template_key == "print_order_placed",
                EmailLog.recipient_email == "ops-admin@example.test",
            )
        )
        assert event_email.status == "queued"
        job = db.session.scalar(
            db.select(BackgroundJob).where(
                BackgroundJob.job_type == "send_admin_email",
                BackgroundJob.reference_id == event_email.id,
            )
        )
        assert job.status == "queued"
        app.extensions["background_jobs"]._run_job(job.id)
        db.session.refresh(event_email)
        assert event_email.status == "sent"
        db.session.refresh(job)
        assert job.status == "completed"
    assert client.get("/api/v1/admin/reports").status_code == 200
    assert client.get("/api/v1/admin/activity").json["pagination"]["totalItems"] >= 2
    email = client.post(
        "/api/v1/admin/emails",
        json={"recipient": "ops-admin@example.test", "subject": "Order update", "body": "Your order is being prepared."},
        headers=csrf,
    )
    assert email.status_code == 202
    assert email.json["email"]["status"] == "sent"


def test_private_print_photos_are_gated_and_every_access_is_logged(app):
    admin, _ = admin_client(app, "private-photo-admin@example.test")
    customer, _ = admin_client(app, "private-photo-customer@example.test", assign_admin=False)
    logged_out = app.test_client()
    storage = FakeStorage()
    app.extensions["asset_storage"] = storage
    photo_bytes = valid_png()

    with app.app_context():
        owner = db.session.scalar(db.select(User).where(User.email == "private-photo-customer@example.test"))
        project = UserProject(
            user_id=owner.id,
            title="Private production book",
            status="in_progress",
            page_count=1,
            version=1,
            privacy_override=True,
        )
        db.session.add(project)
        db.session.flush()
        asset = ProjectAsset(
            project_id=project.id,
            storage_key=f"projects/{owner.id}/{project.id}/private.png",
            mime_type="image/png",
            byte_size=len(photo_bytes),
            checksum_sha256=hashlib.sha256(photo_bytes).hexdigest(),
            original_filename="private.png",
        )
        db.session.add(asset)
        db.session.flush()
        document = {
            "assets": [{"id": asset.id}],
            "pages": [{"id": "private-page", "elements": [{"type": "image", "assetId": asset.id}]}],
        }
        revision = ProjectRevision(
            project_id=project.id,
            revision_number=1,
            document_version=1,
            document=document,
            checksum_sha256=hashlib.sha256(b"private-revision").hexdigest(),
        )
        address = ShippingAddress(
            user_id=owner.id,
            recipient_name="Private Customer",
            address_line_1="1 Main Street",
            city="Lahore",
            postal_code="54000",
            country_code="PK",
        )
        db.session.add_all([revision, address])
        db.session.flush()
        order = PrintOrder(
            order_number="PRIVATE-PRINT-1",
            user_id=owner.id,
            project_id=project.id,
            project_revision_id=revision.id,
            shipping_address_id=address.id,
            shipping_address_snapshot={"city": "Lahore"},
            status="in_production",
            currency="PKR",
            book_amount=Decimal("1000.00"),
            printing_amount=Decimal("500.00"),
            shipping_amount=Decimal("100.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("1600.00"),
            price_snapshot={"total": "1600.00"},
            paid_at=datetime.now(UTC),
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(Payment(
            user_id=owner.id,
            print_order_id=order.id,
            provider="test-provider",
            status="successful",
            amount=order.total_amount,
            currency=order.currency,
        ))
        db.session.commit()
        order_id, asset_id = order.id, asset.id
        storage.objects[asset.storage_key] = (photo_bytes, "image/png")

    photo_list_path = f"/api/v1/admin/orders/print/{order_id}/photos"
    assert logged_out.get(photo_list_path).status_code == 401
    assert customer.get(photo_list_path).status_code == 403
    listed = admin.get("/api/v1/admin/orders?type=print")
    assert listed.status_code == 200
    item = listed.json["items"][0]
    assert item["privateProject"] is True
    assert item["photosAvailable"] is True
    assert "projectRevision" not in item

    photo_list = admin.get(photo_list_path)
    assert photo_list.status_code == 200
    assert [photo["id"] for photo in photo_list.json["items"]] == [asset_id]
    image = admin.get(f"/api/v1{photo_list.json['items'][0]['url']}")
    assert image.status_code == 200
    assert image.data == photo_bytes

    with app.app_context():
        order = db.session.get(PrintOrder, order_id)
        order.status = "payment_confirmed"
        db.session.commit()
        assert db.session.scalar(
            db.select(db.func.count(AdminActivityLog.id)).where(
                AdminActivityLog.target_id == order_id,
                AdminActivityLog.action == "private_print_order.photos_accessed",
            )
        ) == 2
    assert admin.get(photo_list_path).status_code == 404
    with app.app_context():
        order = db.session.get(PrintOrder, order_id)
        order.status = "delivered"
        db.session.add(Shipment(
            print_order_id=order_id,
            status="delivered",
            delivered_at=datetime.now(UTC) - timedelta(days=31),
        ))
        db.session.commit()
    cleanup = app.test_cli_runner().invoke(args=["cleanup-delivered-uploads", "--days", "30"])
    assert cleanup.exit_code == 0, cleanup.output
    with app.app_context():
        persisted_asset = db.session.get(ProjectAsset, asset_id)
        assert persisted_asset.original_deleted_at is not None
    assert storage.objects == {}


def test_admin_print_pdf_download_requires_paid_order_and_logs_access(app):
    admin, _ = admin_client(app, "print-pdf-admin@example.test")
    customer, _ = admin_client(app, "print-pdf-customer@example.test", assign_admin=False)
    storage = FakeStorage()
    app.extensions["asset_storage"] = storage

    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "print-pdf-customer@example.test"))
        project = UserProject(
            user_id=user.id,
            title="Print PDF project",
            page_count=24,
            privacy_override=True,
            document={"schemaVersion": 1, "pages": [{"id": "page-pdf", "elements": []}]},
        )
        db.session.add(project)
        db.session.flush()
        revision = ProjectRevision(
            project_id=project.id,
            revision_number=1,
            document_version=1,
            document=project.document,
            checksum_sha256="c" * 64,
        )
        address = ShippingAddress(
            user_id=user.id,
            recipient_name="Print PDF Customer",
            address_line_1="2 Book Street",
            city="Lahore",
            postal_code="54000",
            country_code="PK",
        )
        db.session.add_all([revision, address])
        db.session.flush()
        paid_order = PrintOrder(
            order_number="PRINT-PDF-PAID",
            user_id=user.id,
            project_id=project.id,
            project_revision_id=revision.id,
            shipping_address_id=address.id,
            shipping_address_snapshot={"fullName": "Print PDF Customer", "city": "Lahore"},
            status="payment_confirmed",
            currency="PKR",
            book_amount=Decimal("1000.00"),
            printing_amount=Decimal("500.00"),
            shipping_amount=Decimal("100.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("1600.00"),
            price_snapshot={"pageCount": 24, "quantity": 1, "total": "1600.00"},
            paid_at=datetime.now(UTC),
        )
        unpaid_order = PrintOrder(
            order_number="PRINT-PDF-UNPAID",
            user_id=user.id,
            project_id=project.id,
            project_revision_id=revision.id,
            shipping_address_id=address.id,
            shipping_address_snapshot={"fullName": "Print PDF Customer", "city": "Lahore"},
            status="pending_payment",
            currency="PKR",
            book_amount=Decimal("1000.00"),
            printing_amount=Decimal("500.00"),
            shipping_amount=Decimal("100.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("1600.00"),
            price_snapshot={"pageCount": 24, "quantity": 1, "total": "1600.00"},
        )
        db.session.add_all([paid_order, unpaid_order])
        db.session.flush()
        paid_payment = Payment(
            user_id=user.id,
            print_order_id=paid_order.id,
            provider="paypal",
            status="successful",
            amount=paid_order.total_amount,
            currency=paid_order.currency,
        )
        pdf_order = PdfOrder(
            order_number="PDF-PRINT-PDF-PAID",
            user_id=user.id,
            project_id=project.id,
            project_revision_id=revision.id,
            status="paid",
            currency="PKR",
            service_price=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            price_snapshot={"total": "0.00"},
            page_count=24,
            paid_at=datetime.now(UTC),
            idempotency_key=f"print-free:{paid_order.id}",
        )
        storage_key = f"generated/pdf/{pdf_order.id}/print/test.pdf"
        db.session.add_all([paid_payment, pdf_order])
        db.session.flush()
        db.session.add_all([
            PrintOrderItem(
                print_order_id=paid_order.id,
                quantity=1,
                page_count=24,
                unit_price=Decimal("1600.00"),
                line_total=Decimal("1600.00"),
                specification_snapshot={
                    "tier": "premium",
                    "size": "Square",
                    "cover": "Hardcover",
                    "paper": "Premium",
                },
            ),
            GeneratedFile(
                pdf_order_id=pdf_order.id,
                generation_profile="print",
                storage_key=storage_key,
                file_type="application/pdf",
                byte_size=100,
                checksum_sha256="d" * 64,
            ),
        ])
        db.session.commit()
        storage.objects[storage_key] = (b"%PDF-1.4 test", "application/pdf")
        paid_order_id = paid_order.id
        unpaid_order_id = unpaid_order.id

    paid_path = f"/api/v1/admin/orders/print/{paid_order_id}/pdf"
    unpaid_path = f"/api/v1/admin/orders/print/{unpaid_order_id}/pdf"
    assert customer.get(paid_path).status_code == 403

    production_queue = admin.get("/api/v1/admin/orders?type=print")
    assert production_queue.status_code == 200
    assert [item["id"] for item in production_queue.json["items"]] == [paid_order_id]
    production_order = production_queue.json["items"][0]
    assert production_order["customer"]["email"] == "print-pdf-customer@example.test"
    assert production_order["deliveryAddress"]["city"] == "Lahore"
    assert production_order["configuration"]["cover"] == "Hardcover"
    assert production_order["pageCount"] == 24
    assert "projectRevision" not in production_order

    assert admin.get(unpaid_path).status_code == 404
    response = admin.get(paid_path)
    assert response.status_code == 200, response.get_json()
    assert response.json["url"].startswith(f"/admin/orders/print/{paid_order_id}/pdf/")
    assert response.json["expiresInSeconds"] == app.config["ASSET_S3_PRESIGNED_URL_TTL"]
    download_path = f"/api/v1{response.json['url']}"
    assert customer.get(download_path).status_code == 403
    downloaded = admin.get(download_path)
    assert downloaded.status_code == 200
    assert downloaded.data == b"%PDF-1.4 test"
    assert downloaded.headers["Content-Disposition"].endswith("PRINT-PDF-PAID-print.pdf")
    assert admin.get(download_path).status_code == 200
    with app.app_context():
        audits = db.session.scalars(
            db.select(AdminActivityLog).where(
                AdminActivityLog.target_id == paid_order_id,
                AdminActivityLog.action == "private_print_order.pdf_accessed",
            )
        ).all()
        assert len(audits) == 2
        assert all(audit.details["generationProfile"] == "print" for audit in audits)
