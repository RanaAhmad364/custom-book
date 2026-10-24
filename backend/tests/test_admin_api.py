import hashlib
import re
from datetime import UTC, datetime
import time
from decimal import Decimal
from urllib.parse import urlsplit
from io import BytesIO

from memorybook.extensions import db
from memorybook.models import (
    BookSize,
    BookTemplate,
    BookTemplateVersion,
    CoverType,
    DiscountCode,
    EmailLog,
    PaperType,
    Payment,
    PdfOrder,
    ProjectAsset,
    PricingTier,
    PrintOrder,
    ProjectRevision,
    Role,
    ShippingAddress,
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

    def copy(self, source_key, target_key):
        self.objects[target_key] = self.objects[source_key]

    def delete(self, key):
        self.objects.pop(key, None)


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


def test_admin_catalog_image_upload_is_validated_and_stored_privately(app):
    client, csrf = admin_client(app, "assets-admin@example.test")
    storage = FakeStorage()
    app.extensions["asset_storage"] = storage
    response = client.post(
        "/api/v1/admin/assets",
        data={"file": (BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16), "cover.png")},
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
        data={"file": (BytesIO(b"not an image"), "cover.png")},
        headers=csrf,
        content_type="multipart/form-data",
    )
    assert invalid.status_code == 400


def test_local_filesystem_catalog_upload_can_be_retrieved(app, tmp_path):
    app.config["ASSET_STORAGE_BACKEND"] = "filesystem"
    app.config["ASSET_LOCAL_DIRECTORY"] = str(tmp_path)
    client, csrf = admin_client(app, "local-assets-admin@example.test")
    image = b"\x89PNG\r\n\x1a\n" + b"local image bytes"

    response = client.post(
        "/api/v1/admin/assets",
        data={"file": (BytesIO(image), "local-cover.png")},
        headers=csrf,
        content_type="multipart/form-data",
    )

    assert response.status_code == 201, response.get_json()
    asset = response.json["asset"]
    assert asset["assetKey"].startswith("catalog/")
    assert asset["url"].startswith("/api/v1/assets/")
    retrieved = client.get(urlsplit(asset["url"]).path)
    assert retrieved.status_code == 200
    assert retrieved.data == image
    assert retrieved.mimetype == "image/png"


def test_local_asset_retrieval_rejects_invalid_and_expired_signatures(app, tmp_path):
    app.config["ASSET_STORAGE_BACKEND"] = "filesystem"
    app.config["ASSET_LOCAL_DIRECTORY"] = str(tmp_path)
    app.config["ASSET_S3_PRESIGNED_URL_TTL"] = 1
    client, csrf = admin_client(app, "expiring-local-assets-admin@example.test")
    response = client.post(
        "/api/v1/admin/assets",
        data={"file": (BytesIO(b"\x89PNG\r\n\x1a\nlocal"), "temporary.png")},
        headers=csrf,
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    asset_path = urlsplit(response.json["asset"]["url"]).path

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
    assert client.get("/api/v1/books/alpine-notes").status_code == 200
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
            "pageCountOptions": [24, 32, 40], "printingTiers": ["LIGHT", "BASIC", "PREMIUM"],
            "previewImageKeys": ["catalog/alpine-preview.jpg"], "pdfPrice": "8.00",
            "printingPrice": "44.50", "productionDays": 7,
        }},
        headers=csrf,
    )
    assert specification_update.status_code == 200
    assert specification_update.json["book"]["adminMetadata"]["dimensions"]["widthMm"] == "203.20"
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
    assert published.json["product"]["isPublished"] is True
    assert published.json["template"]["published"] is True
    assert published.json["template"]["publishedVersion"] == 2
    assert admin.get("/api/v1/books/family-keepsake").status_code == 200


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
        json={"name": "Weekend", "slug": "weekend-collection"},
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
    assert admin.delete(f"/api/v1/admin/categories/{category['id']}", headers=csrf).status_code == 204
    assert admin.get("/api/v1/books/archive-book").status_code == 404


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
            price_snapshot={"total": "40.00"},
        )
        db.session.add(order)
        db.session.flush()
        payment = Payment(
            user_id=user.id, print_order_id=order.id, provider="test-provider",
            status="failed", amount=Decimal("40.00"), currency="USD",
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
    shipment_update = client.patch(
        f"/api/v1/admin/orders/print/{order_id}",
        json={"status": "in_production", "carrier": "MemoryShip", "trackingNumber": "TRACK-101"},
        headers=csrf,
    )
    assert shipment_update.status_code == 200
    assert shipment_update.json["order"]["shipment"]["trackingNumber"] == "TRACK-101"
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
    assert any(item["title"] == "Order status updated" for item in user_notices.json["items"])
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
        task = app.extensions["celery"].tasks["memorybook.send_admin_event_email"]
        task.apply(args=[event_email.id, "Print order placed", "A print order was placed."], throw=True)
        db.session.refresh(event_email)
        assert event_email.status == "sent"
    assert client.get("/api/v1/admin/reports").status_code == 200
    assert client.get("/api/v1/admin/activity").json["pagination"]["totalItems"] >= 2
    email = client.post(
        "/api/v1/admin/emails",
        json={"recipient": "ops-admin@example.test", "subject": "Order update", "body": "Your order is being prepared."},
        headers=csrf,
    )
    assert email.status_code == 202
    assert email.json["email"]["status"] == "sent"
