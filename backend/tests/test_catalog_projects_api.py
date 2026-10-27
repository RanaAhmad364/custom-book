import io
import re
import time
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlsplit

from PIL import Image
from sqlalchemy import select

from memorybook.extensions import db
from memorybook.models import (
    BookCategory,
    BookCollection,
    BookProduct,
    BookTemplate,
    ProjectAsset,
    ProjectRevision,
    UserProject,
)


class FakeAssetStorage:
    def __init__(self):
        self.objects = {}

    def upload(self, key, stream, mime_type):
        self.objects[key] = (stream.read(), mime_type)

    def download_url(self, key):
        return f"https://storage.example.test/{key}?signature=test"

    def public_download_url(self, key):
        return f"https://storage.example.test/public/{key}"

    def private_download_url(self, key):
        return f"https://storage.example.test/private/{key}?signature=test"

    def delete(self, key):
        self.objects.pop(key, None)

    def copy(self, source_key, target_key):
        self.objects[target_key] = self.objects[source_key]


def authenticated_client(app, email):
    client = app.test_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery"},
    )
    assert response.status_code == 201
    message = app.extensions["auth_email_outbox"][-1][2]
    code = re.search(r"\b(\d{6})\b", message).group(1)
    assert client.post("/api/v1/auth/verify-otp", json={"email": email, "code": code}).status_code == 200
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    assert login.status_code == 200
    csrf = next(
        value.split(";", 1)[0].split("=", 1)[1]
        for value in login.headers.getlist("Set-Cookie")
        if value.startswith("csrf_access_token=")
    )
    return client, {"X-CSRF-TOKEN": csrf}


def valid_png():
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), (20, 40, 60)).save(stream, format="PNG")
    return stream.getvalue()


def valid_jpeg():
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), (20, 40, 60)).save(stream, format="JPEG")
    return stream.getvalue()


def project_document(project_id=None, *, title="A real project"):
    return {
        "schemaVersion": 1,
        "metadata": {"id": project_id, "title": title, "owner": "alice@example.test"},
        "book": {"pageCount": 1, "size": {"width": 10, "height": 10}},
        "pageOrder": ["cover-page", "interior-page"],
        "pages": [
            {"id": "cover-page", "type": "cover", "label": "Cover", "elements": []},
            {"id": "interior-page", "type": "page", "label": "Page 1", "elements": []},
        ],
        "assets": [],
        "styles": {},
        "cover": {"pageId": "cover-page"},
    }


def seed_catalog():
    category = BookCategory(name="Travel", slug="travel", description="Books for journeys", style="Editorial")
    db.session.add(category)
    db.session.flush()
    collection = BookCollection(
        name="Far & near",
        slug="far-and-near",
        description="Travel collection",
        category_id=category.id,
    )
    db.session.add(collection)
    db.session.flush()
    product = BookProduct(
        category_id=category.id,
        collection_id=collection.id,
        title="Our Alpine Journey",
        slug="our-alpine-journey",
        description="A photo book of a mountain trip",
        style="Minimal",
        occasion="Travel",
        book_type="BASIC",
        page_count_min=24,
        page_count_max=80,
        starting_price=Decimal("42.50"),
        is_featured=True,
        is_active=True,
    )
    hidden = BookProduct(
        category_id=category.id,
        title="Unpublished sample",
        slug="unpublished-sample",
        description="Not public",
        starting_price=Decimal("1.00"),
        is_active=False,
    )
    template = BookTemplate(
        category_id=category.id,
        name="Travel Journal",
        slug="travel-journal",
        description="A clean editorial template",
        is_active=True,
    )
    hidden_template = BookTemplate(name="Hidden", slug="hidden-template", is_active=False)
    db.session.add_all([product, hidden, template, hidden_template])
    db.session.commit()
    return category, collection, product, template


def test_public_catalog_only_returns_active_records_with_search_filters_and_pagination(app, client):
    with app.app_context():
        category, collection, product, template = seed_catalog()
        category_id = category.id

    response = client.get("/api/v1/books?search=alpine&category=travel&style=minimal&bookType=BASIC&minPrice=40&maxPrice=45&page=1&perPage=1")
    assert response.status_code == 200
    assert [item["slug"] for item in response.json["items"]] == ["our-alpine-journey"]
    assert response.json["pagination"] == {"page": 1, "perPage": 1, "totalItems": 1, "totalPages": 1}
    assert client.get("/api/v1/books/unpublished-sample").status_code == 404

    categories = client.get("/api/v1/categories")
    collections = client.get("/api/v1/collections")
    templates = client.get("/api/v1/templates")
    assert [item["slug"] for item in categories.json["items"]] == ["travel"]
    assert [item["slug"] for item in collections.json["items"]] == ["far-and-near"]
    assert collections.json["items"][0]["categoryId"] == category_id
    assert collections.json["items"][0]["categoryName"] == "Travel"
    assert [item["slug"] for item in templates.json["items"]] == ["travel-journal"]
    assert client.get("/api/v1/templates/hidden-template").status_code == 404


def test_public_plan_catalog_uses_active_catalog_prices_and_configured_currency(app, client):
    with app.app_context():
        seed_catalog()

    response = client.get("/api/v1/pricing/tiers")

    assert response.status_code == 200
    plans = {item["id"]: item for item in response.json["items"]}
    assert set(plans) == {"basic", "medium", "premium"}
    assert plans["basic"]["startingPrice"] == "42.50"
    assert plans["basic"]["currency"] == "PKR"
    assert plans["basic"]["maximumPages"] == 80
    assert plans["medium"]["startingPrice"] is None
    assert plans["premium"]["startingPrice"] is None


def test_favorites_are_private_idempotent_and_included_in_catalog_responses(app, client):
    with app.app_context():
        _, _, product, _ = seed_catalog()
        book_id = product.id
        book_slug = product.slug

    assert client.get("/api/v1/favorites").status_code == 401
    assert client.post(f"/api/v1/favorites/{book_id}").status_code == 401
    assert client.delete(f"/api/v1/favorites/{book_id}").status_code == 401
    assert client.get("/api/v1/books").json["items"][0]["is_favorite"] is False

    owner, owner_headers = authenticated_client(app, "favorites-owner@example.test")
    other, other_headers = authenticated_client(app, "favorites-other@example.test")
    add_path = f"/api/v1/favorites/{book_id}"
    assert owner.post(add_path, headers=owner_headers).status_code == 200
    assert owner.post(f"/api/v1/favorites/{book_slug}", headers=owner_headers).status_code == 200
    assert owner.get("/api/v1/favorites").json["items"][0]["id"] == book_id
    assert owner.get("/api/v1/books").json["items"][0]["is_favorite"] is True
    assert owner.get(f"/api/v1/books/{book_slug}").json["book"]["is_favorite"] is True
    from memorybook.services.admin import _product_dict, dashboard_metrics
    with app.app_context():
        assert dashboard_metrics()["favoritesCount"] == 1
        assert _product_dict(db.session.get(BookProduct, book_id))["favorites_count"] == 1

    assert other.get("/api/v1/favorites").json["items"] == []
    assert other.get("/api/v1/books").json["items"][0]["is_favorite"] is False
    assert other.delete(add_path, headers=other_headers).status_code == 204
    assert owner.get("/api/v1/favorites").json["items"][0]["id"] == book_id
    assert owner.delete(add_path, headers=owner_headers).status_code == 204
    assert owner.delete(add_path, headers=owner_headers).status_code == 204
    assert owner.get("/api/v1/favorites").json["items"] == []


def test_favorites_reject_unpublished_books(app, client):
    with app.app_context():
        _, _, _, _ = seed_catalog()
        hidden = db.session.scalar(select(BookProduct).where(BookProduct.slug == "unpublished-sample"))
        hidden_id = hidden.id
    member, headers = authenticated_client(app, "favorites-hidden@example.test")
    assert member.post(f"/api/v1/favorites/{hidden_id}", headers=headers).status_code == 404


def test_inactive_collection_details_are_hidden_without_hiding_public_books(app, client):
    with app.app_context():
        category, collection, product, _ = seed_catalog()
        collection.is_active = False
        db.session.commit()
        product_slug = product.slug

    books = client.get("/api/v1/books?search=alpine")
    assert books.status_code == 200
    assert [item["slug"] for item in books.json["items"]] == ["our-alpine-journey"]
    assert books.json["items"][0]["collection"] == ""
    assert books.json["items"][0]["collectionSlug"] == ""
    assert client.get("/api/v1/collections").json["items"] == []
    assert client.get(f"/api/v1/books/{product_slug}").json["book"]["collection"] == ""


def test_book_details_resolves_persisted_gallery_keys_without_expanding_catalog_list(app, client):
    app.extensions["asset_storage"] = FakeAssetStorage()
    with app.app_context():
        _, _, product, _ = seed_catalog()
        design_template = BookTemplate(
            product_id=product.id,
            category_id=product.category_id,
            name="Alpine Master Design",
            slug="alpine-master-design",
            is_active=True,
            published_version=3,
            published_design_document=project_document(),
        )
        product.cover_asset_key = "catalog/test-cover.jpg"
        product.admin_metadata = {
            "previewImageKeys": ["catalog/test-page-1.jpg", "catalog/test-page-2.jpg"],
        }
        db.session.add(design_template)
        db.session.commit()
        slug = product.slug
        design_template_id = design_template.id

    details = client.get(f"/api/v1/books/{slug}")
    assert details.status_code == 200
    gallery = details.json["book"]["gallery"]
    assert details.json["book"]["designTemplateId"] == design_template_id
    assert [item["label"] for item in gallery] == ["Cover", "Preview 1", "Preview 2"]
    assert [item["image"] for item in gallery] == [
        "https://storage.example.test/public/catalog/test-cover.jpg",
        "https://storage.example.test/public/catalog/test-page-1.jpg",
        "https://storage.example.test/public/catalog/test-page-2.jpg",
    ]

    listing = client.get("/api/v1/books")
    assert listing.status_code == 200
    assert "gallery" not in listing.json["items"][0]
    assert "designTemplateId" not in listing.json["items"][0]


def test_catalog_rejects_invalid_pagination_and_filters(client):
    assert client.get("/api/v1/books?page=0").status_code == 400
    assert client.get("/api/v1/books?perPage=101").status_code == 400
    assert client.get("/api/v1/books?sort=arbitrary").status_code == 400
    assert client.get("/api/v1/books?pageCount=bad").status_code == 400


def test_projects_are_user_scoped_and_use_optimistic_versioning(app):
    alice, alice_headers = authenticated_client(app, "alice@example.test")
    bob, bob_headers = authenticated_client(app, "bob@example.test")
    document = project_document()
    created = alice.post(
        "/api/v1/projects",
        json={"title": "A real project", "pageCount": 1, "document": document},
        headers=alice_headers,
    )
    assert created.status_code == 201
    project = created.json["project"]
    project_id = project["id"]
    assert project["version"] == 1
    assert len(project["document"]["pages"]) == 2

    assert bob.get(f"/api/v1/projects/{project_id}").status_code == 404
    assert bob.patch(
        f"/api/v1/projects/{project_id}",
        json={"title": "Stolen"},
        headers={**bob_headers, "If-Match": '"1"'},
    ).status_code == 404
    assert bob.delete(
        f"/api/v1/projects/{project_id}",
        headers={**bob_headers, "If-Match": '"1"'},
    ).status_code == 404

    saved = alice.patch(
        f"/api/v1/projects/{project_id}",
        json={"title": "Renamed"},
        headers={**alice_headers, "If-Match": '"1"'},
    )
    assert saved.status_code == 200
    assert saved.headers["ETag"] == '"2"'
    stale = alice.patch(
        f"/api/v1/projects/{project_id}",
        json={"title": "Stale update"},
        headers={**alice_headers, "If-Match": '"1"'},
    )
    assert stale.status_code == 409
    assert stale.json["error"]["details"]["currentVersion"] == 2
    assert alice.patch(f"/api/v1/projects/{project_id}", json={"title": "Missing version"}, headers=alice_headers).status_code == 428

    listing = alice.get("/api/v1/projects?search=Renamed&page=1&perPage=2")
    assert [item["id"] for item in listing.json["items"]] == [project_id]
    assert bob.get("/api/v1/projects").json["items"] == []


def test_product_projects_require_its_published_master_design(app):
    customer, headers = authenticated_client(app, "published-design-customer@example.test")
    with app.app_context():
        _, _, product, template = seed_catalog()
        product.page_count_min = 1
        db.session.commit()
        product_id = product.id
        template_id = template.id

    no_design_id = customer.post(
        "/api/v1/projects",
        json={"title": "Missing master", "pageCount": 1, "productId": product_id},
        headers=headers,
    )
    assert no_design_id.status_code == 400

    generic_template = customer.post(
        "/api/v1/projects",
        json={"title": "Mismatched master", "pageCount": 1, "productId": product_id, "templateId": template_id},
        headers=headers,
    )
    assert generic_template.status_code == 400

    with app.app_context():
        master = db.session.get(BookTemplate, template_id)
        master.product_id = product_id
        db.session.commit()

    unpublished_design = customer.post(
        "/api/v1/projects",
        json={"title": "Unpublished master", "pageCount": 1, "productId": product_id, "templateId": template_id},
        headers=headers,
    )
    assert unpublished_design.status_code == 400

    with app.app_context():
        master = db.session.get(BookTemplate, template_id)
        master_document = project_document("master-owned")
        master_document["pages"][1]["elements"] = [{
            "id": "master-text-element",
            "type": "text",
            "text": "A master design remains untouched.",
            "x": 0.1,
            "y": 0.2,
            "width": 0.8,
            "height": 0.1,
        }]
        master.published_design_document = master_document
        master.published_version = master.version
        db.session.commit()

    created = customer.post(
        "/api/v1/projects",
        json={"title": "Independent copy", "pageCount": 1, "productId": product_id, "templateId": template_id},
        headers=headers,
    )
    assert created.status_code == 201, created.get_json()
    assert created.json["project"]["document"]["metadata"]["id"] == created.json["project"]["id"]
    first_document = created.json["project"]["document"]
    second = customer.post(
        "/api/v1/projects",
        json={"title": "Second independent copy", "pageCount": 1, "productId": product_id, "templateId": template_id},
        headers=headers,
    )
    assert second.status_code == 201, second.get_json()
    second_document = second.json["project"]["document"]
    assert set(first_document["pageOrder"]).isdisjoint(second_document["pageOrder"])
    assert first_document["cover"]["pageId"] != second_document["cover"]["pageId"]
    first_element_id = first_document["pages"][1]["elements"][0]["id"]
    second_element_id = second_document["pages"][1]["elements"][0]["id"]
    assert first_element_id != second_element_id

    with app.app_context():
        master = db.session.get(BookTemplate, template_id)
        assert master.published_design_document["pages"][1]["elements"][0]["id"] == "master-text-element"


def test_project_pages_assets_and_revisions_are_owned_and_round_trip(app):
    app.extensions["asset_storage"] = FakeAssetStorage()
    alice, headers = authenticated_client(app, "alice@example.test")
    bob, bob_headers = authenticated_client(app, "bob@example.test")
    created = alice.post(
        "/api/v1/projects",
        json={"title": "Photo project", "pageCount": 1, "document": project_document()},
        headers=headers,
    )
    project_id = created.json["project"]["id"]

    added_page = alice.post(
        f"/api/v1/projects/{project_id}/pages",
        json={
            "id": "new-page",
            "pageNumber": 3,
            "label": "Closing",
            "type": "page",
            "layout": "blank",
            "background": {"color": "#fffdf9"},
            "elements": [],
        },
        headers={**headers, "If-Match": '"1"'},
    )
    assert added_page.status_code == 201, added_page.get_json()
    assert added_page.json["project"]["version"] == 2

    storage = app.extensions["asset_storage"]
    upload = alice.post(
        f"/api/v1/projects/{project_id}/assets",
        data={"assetId": "asset-one", "file": (io.BytesIO(valid_png()), "memory.png", "image/png")},
        headers={**headers, "If-Match": '"2"'},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201
    assert upload.json["asset"]["id"] == "asset-one"
    assert storage.objects
    assert upload.json["projectVersion"] == 3
    assert bob.get(f"/api/v1/projects/{project_id}/assets").status_code == 404

    saved_document = added_page.json["project"]["document"]
    asset = upload.json["asset"]
    saved_document["assets"].append(asset)
    page = next(page for page in saved_document["pages"] if page["id"] == "interior-page")
    page["elements"].append({
        "id": "photo-element",
        "type": "image",
        "assetId": "asset-one",
        "src": asset["src"],
        "x": 0.1,
        "y": 0.1,
        "width": 0.8,
        "height": 0.8,
    })
    saved_document["metadata"]["owner"] = "alice@example.test"
    saved = alice.patch(
        f"/api/v1/projects/{project_id}",
        json={"document": saved_document},
        headers={**headers, "If-Match": '"3"'},
    )
    assert saved.status_code == 200
    assert saved.json["project"]["document"]["pages"][1]["elements"][0]["src"].startswith("https://storage.example.test/")
    asset_delete = alice.delete(
        f"/api/v1/projects/{project_id}/assets/asset-one",
        headers={**headers, "If-Match": '"4"'},
    )
    assert asset_delete.status_code == 409

    revision = alice.post(
        f"/api/v1/projects/{project_id}/revisions",
        headers={**headers, "If-Match": '"4"'},
    )
    assert revision.status_code == 201
    revision_id = revision.json["revision"]["id"]
    assert alice.get(f"/api/v1/projects/{project_id}/revisions/{revision_id}").status_code == 200
    assert bob.get(f"/api/v1/projects/{project_id}/revisions/{revision_id}").status_code == 404

    removed_page = alice.delete(
        f"/api/v1/projects/{project_id}/pages/new-page",
        headers={**headers, "If-Match": '"4"'},
    )
    assert removed_page.status_code == 200
    restored = alice.post(
        f"/api/v1/projects/{project_id}/revisions/{revision_id}/restore",
        headers={**headers, "If-Match": '"5"'},
    )
    assert restored.status_code == 200
    assert "new-page" in restored.json["project"]["document"]["pageOrder"]
    with app.app_context():
        assert db.session.scalar(db.select(ProjectRevision).where(ProjectRevision.id == revision_id)) is not None


def test_duplicated_project_owns_copied_assets_and_survives_source_deletion(app):
    app.extensions["asset_storage"] = FakeAssetStorage()
    owner, headers = authenticated_client(app, "duplicate-owner@example.test")
    other_user, _ = authenticated_client(app, "duplicate-other@example.test")
    created = owner.post(
        "/api/v1/projects",
        json={"title": "Source project", "pageCount": 1, "document": project_document(title="Source project")},
        headers=headers,
    )
    project_id = created.json["project"]["id"]
    uploaded = owner.post(
        f"/api/v1/projects/{project_id}/assets",
        data={"assetId": "source-asset", "file": (io.BytesIO(valid_png()), "source.png", "image/png")},
        headers={**headers, "If-Match": '"1"'},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    document = created.json["project"]["document"]
    asset = uploaded.json["asset"]
    document["assets"].append(asset)
    document["pages"][1]["elements"].append({
        "id": "source-photo",
        "type": "image",
        "assetId": asset["id"],
        "src": asset["src"],
        "x": 0.1,
        "y": 0.1,
        "width": 0.8,
        "height": 0.8,
    })
    saved = owner.patch(
        f"/api/v1/projects/{project_id}",
        json={"document": document},
        headers={**headers, "If-Match": '"2"'},
    )
    assert saved.status_code == 200

    duplicated = owner.post(f"/api/v1/projects/{project_id}/duplicate", headers=headers)
    assert duplicated.status_code == 201, duplicated.get_json()
    duplicate = duplicated.json["project"]
    duplicate_asset = duplicate["document"]["assets"][0]
    assert duplicate["id"] != project_id
    assert duplicate_asset["id"] != asset["id"]
    assert duplicate["document"]["pages"][1]["elements"][0]["assetId"] == duplicate_asset["id"]
    storage = app.extensions["asset_storage"]
    with app.app_context():
        original_record = db.session.get(ProjectAsset, asset["id"])
        duplicate_record = db.session.get(ProjectAsset, duplicate_asset["id"])
        assert original_record.storage_key != duplicate_record.storage_key
        original_key = original_record.storage_key
        duplicate_key = duplicate_record.storage_key
    assert storage.objects[original_key] == storage.objects[duplicate_key]
    assert other_user.get(f"/api/v1/projects/{duplicate['id']}").status_code == 404

    deleted = owner.delete(
        f"/api/v1/projects/{project_id}",
        headers={**headers, "If-Match": '"3"'},
    )
    assert deleted.status_code == 204
    assert duplicate_key in storage.objects
    assert owner.get(f"/api/v1/projects/{duplicate['id']}").status_code == 200


def test_project_asset_upload_rejects_unsupported_mime_and_delete_checks_usage(app):
    app.extensions["asset_storage"] = FakeAssetStorage()
    client, headers = authenticated_client(app, "asset@example.test")
    created = client.post(
        "/api/v1/projects",
        json={"title": "Asset project", "pageCount": 1, "document": project_document()},
        headers=headers,
    )
    project_id = created.json["project"]["id"]
    unsupported = client.post(
        f"/api/v1/projects/{project_id}/assets",
        data={"file": (io.BytesIO(b"svg"), "image.svg", "image/svg+xml")},
        headers={**headers, "If-Match": '"1"'},
        content_type="multipart/form-data",
    )
    assert unsupported.status_code == 400
    assert client.post(
        f"/api/v1/projects/{project_id}/assets",
        data={"file": (io.BytesIO(valid_jpeg()), "image.jpg", "image/jpeg")},
        headers={**headers, "If-Match": '"1"'},
        content_type="multipart/form-data",
    ).status_code == 201


def test_local_project_asset_download_requires_its_owner(app, tmp_path):
    app.config["ASSET_STORAGE_BACKEND"] = "filesystem"
    app.config["ASSET_LOCAL_DIRECTORY"] = str(tmp_path)
    owner, owner_headers = authenticated_client(app, "local-photo-owner@example.test")
    other_user, _ = authenticated_client(app, "local-photo-other@example.test")
    created = owner.post(
        "/api/v1/projects",
        json={"title": "Private local photo", "pageCount": 1, "document": project_document()},
        headers=owner_headers,
    )
    assert created.status_code == 201
    project_id = created.json["project"]["id"]
    uploaded = owner.post(
        f"/api/v1/projects/{project_id}/assets",
        data={"file": (io.BytesIO(valid_png()), "private.png", "image/png")},
        headers={**owner_headers, "If-Match": '"1"'},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201, uploaded.get_json()
    asset_url = uploaded.json["asset"]["src"]
    asset_path = urlsplit(asset_url).path

    assert app.test_client().get(asset_path).status_code == 401
    assert other_user.get(asset_path).status_code == 404
    retrieved = owner.get(asset_path)
    assert retrieved.status_code == 200
    Image.open(io.BytesIO(retrieved.data)).verify()
    assert retrieved.mimetype == "image/png"


def test_reopening_project_refreshes_expired_local_asset_url(app, tmp_path):
    app.config["ASSET_STORAGE_BACKEND"] = "filesystem"
    app.config["ASSET_LOCAL_DIRECTORY"] = str(tmp_path)
    app.config["ASSET_S3_PRESIGNED_URL_TTL"] = 1
    owner, headers = authenticated_client(app, "local-photo-reopen@example.test")
    created = owner.post(
        "/api/v1/projects",
        json={"title": "Reopen after asset expiry", "pageCount": 1, "document": project_document()},
        headers=headers,
    )
    project_id = created.json["project"]["id"]
    uploaded = owner.post(
        f"/api/v1/projects/{project_id}/assets",
        data={"file": (io.BytesIO(valid_png()), "refresh.png", "image/png")},
        headers={**headers, "If-Match": '"1"'},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201, uploaded.get_json()
    document = created.json["project"]["document"]
    document["assets"].append(uploaded.json["asset"])
    saved = owner.patch(
        f"/api/v1/projects/{project_id}",
        json={"document": document},
        headers={**headers, "If-Match": '"2"'},
    )
    assert saved.status_code == 200, saved.get_json()
    original_url = uploaded.json["asset"]["src"]
    original_path = urlsplit(original_url).path
    assert owner.get(original_path).status_code == 200

    time.sleep(2.1)
    assert owner.get(original_path).status_code == 404

    reopened = owner.get(f"/api/v1/projects/{project_id}")
    assert reopened.status_code == 200
    refreshed_url = reopened.json["project"]["document"]["assets"][0]["src"]
    refreshed_path = urlsplit(refreshed_url).path
    assert refreshed_path != original_path
    refreshed = owner.get(refreshed_path)
    assert refreshed.status_code == 200
    Image.open(io.BytesIO(refreshed.data)).verify()


def test_project_deletion_is_soft_and_assets_do_not_leak_to_other_users(app):
    owner, headers = authenticated_client(app, "delete@example.test")
    project = owner.post(
        "/api/v1/projects",
        json={"title": "Remove me", "pageCount": 1},
        headers=headers,
    ).json["project"]
    deleted = owner.delete(
        f"/api/v1/projects/{project['id']}",
        headers={**headers, "If-Match": '"1"'},
    )
    assert deleted.status_code == 204
    assert owner.get(f"/api/v1/projects/{project['id']}").status_code == 404
    with app.app_context():
        persisted = db.session.get(UserProject, project["id"])
        assert persisted.status == "deleted"


def test_account_privacy_and_project_overrides_are_persisted(app):
    client, headers = authenticated_client(app, "privacy-settings@example.test")
    enabled = client.patch("/api/v1/auth/me", json={"privacyMode": True}, headers=headers)
    assert enabled.status_code == 200
    assert enabled.json["user"]["privacyMode"] is True

    inherited = client.post(
        "/api/v1/projects",
        json={"title": "Inherited privacy", "pageCount": 1},
        headers=headers,
    )
    standard = client.post(
        "/api/v1/projects",
        json={
            "title": "Project-specific standard",
            "pageCount": 1,
            "privacyOverride": False,
        },
        headers=headers,
    )
    assert inherited.status_code == 201
    assert inherited.json["project"]["privacyMode"] is True
    assert inherited.json["project"]["privacyOverride"] is None
    assert standard.status_code == 201
    assert standard.json["project"]["privacyMode"] is False
    assert standard.json["project"]["privacyOverride"] is False

    private_override = client.patch(
        f"/api/v1/projects/{standard.json['project']['id']}",
        json={"privacyOverride": True},
        headers={**headers, "If-Match": '"1"'},
    )
    assert private_override.status_code == 200
    assert private_override.json["project"]["privacyMode"] is True
    assert client.patch(
        "/api/v1/auth/me",
        json={"privacyMode": "yes"},
        headers=headers,
    ).status_code == 400
