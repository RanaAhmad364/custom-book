import io
import re
import base64
from datetime import UTC, datetime
from decimal import Decimal

from PIL import Image
from pypdf import PdfReader
import pytest
import pypdfium2

from memorybook.extensions import db
from memorybook.models import (
    BackgroundJob,
    BookCategory,
    BookProduct,
    DownloadEntitlement,
    DownloadHistory,
    OrderStatusHistory,
    Payment,
    PdfJob,
    PdfOrder,
    ProjectAsset,
    ProjectRevision,
    User,
    UserProject,
)
from memorybook.services.pdf_renderer import PdfRenderError, render_project_pdf


class MemoryStorage:
    def __init__(self):
        self.objects = {}

    def upload(self, key, stream, mime_type):
        self.objects[key] = (stream.read(), mime_type)

    def download(self, key):
        return self.objects[key][0]

    def download_url(self, key):
        return f"https://storage.example.test/{key}?signature=private"

    def private_download_url(self, key):
        token = base64.urlsafe_b64encode(key.encode()).decode().rstrip("=")
        return f"/api/v1/assets/private/{token}"

    def download_token(self, token):
        return base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()

    def content_type(self, key):
        return self.objects[key][1]


def make_image(size=(3000, 3000), color=(174, 83, 51)):
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, format="JPEG", quality=92)
    return stream.getvalue()


def document_with_photos(asset_id="photo-1"):
    return {
        "schemaVersion": 1,
        "metadata": {"id": "project-1", "title": "A Saved Memorybook", "owner": "reader@example.test"},
        "book": {"pageCount": 2, "size": {"width": 8, "height": 8}, "coverType": "Hardcover"},
        "pageOrder": ["cover-page", "interior-first", "interior-second"],
        "pages": [
            {
                "id": "cover-page",
                "type": "cover",
                "label": "Cover",
                "background": {"color": "#e8ece5"},
                "elements": [],
            },
            {
                "id": "interior-first",
                "type": "page",
                "label": "First",
                "background": {"color": "#fffdf9"},
                "elements": [
                    {
                        "id": "first-text",
                        "type": "text",
                        "text": "Page one in saved order",
                        "x": 0.1,
                        "y": 0.12,
                        "width": 0.8,
                        "height": 0.2,
                        "fontSize": 0.04,
                        "fontFamily": "Georgia",
                        "fontWeight": "700",
                        "color": "#20352d",
                        "alignment": "center",
                    }
                ],
            },
            {
                "id": "interior-second",
                "type": "page",
                "label": "Second",
                "background": {"color": "#dce8e1"},
                "elements": [
                    {
                        "id": "page-photo",
                        "type": "image",
                        "assetId": asset_id,
                        "x": 0.08,
                        "y": 0.08,
                        "width": 0.84,
                        "height": 0.84,
                        "fit": "cover",
                        "cropX": 0.25,
                        "cropY": 0.75,
                        "zoom": 1.1,
                        "rotation": 0,
                        "opacity": 1,
                    },
                    {
                        "id": "second-text",
                        "type": "text",
                        "text": "A second page caption",
                        "x": 0.15,
                        "y": 0.78,
                        "width": 0.7,
                        "height": 0.08,
                        "fontSize": 0.025,
                        "fontFamily": "DM Sans",
                        "color": "#20352d",
                    },
                ],
            },
        ],
        "assets": [{"id": asset_id, "name": "memory.jpg", "mimeType": "image/jpeg"}],
        "styles": {},
        "cover": {
            "pageId": "cover-page",
            "finish": "Hardcover",
            "design": {
                "bleedInches": 0.125,
                "front": {
                    "title": "Front cover title",
                    "subtitle": "A keepsake",
                    "backgroundColor": "#e8ece5",
                    "textColor": "#20352d",
                    "fontFamily": "Georgia",
                    "layout": "center",
                    "photoAssetId": asset_id,
                },
                "spine": {"title": "A Saved Memorybook", "backgroundColor": "#e8ece5", "fontFamily": "Georgia"},
                "back": {
                    "title": "Back cover",
                    "description": "A note on the back.",
                    "backgroundColor": "#f4eee5",
                    "fontFamily": "Georgia",
                },
            },
        },
    }


def test_renderer_creates_valid_digital_and_print_pdfs_from_revision_document():
    source = document_with_photos()
    source["pages"][1]["background"].update({"borderColor": "#315b49", "borderStyle": "dotted"})
    source["pages"][1]["elements"].append({
        "id": "photo-slot",
        "type": "shape",
        "shape": "photo-placeholder",
        "x": 0.55,
        "y": 0.55,
        "width": 0.35,
        "height": 0.35,
        "fill": "#edf0eb",
        "stroke": "#d8ded8",
        "strokeWidth": 0.001,
    })
    photo = make_image()
    digital_bytes, digital_info = render_project_pdf(source, {"photo-1": photo}, "digital")
    digital = PdfReader(io.BytesIO(digital_bytes), strict=True)
    assert len(digital.pages) == 4
    assert digital_info["pageCount"] == 4
    assert "Front cover title" in digital.pages[0].extract_text()
    assert "Page one in saved order" in digital.pages[1].extract_text()
    assert "A second page caption" in digital.pages[2].extract_text()
    assert "Back cover" in digital.pages[3].extract_text()
    assert len(digital.pages[2].images) == 1
    assert float(digital.pages[1].mediabox.width) == 8 * 72

    print_bytes, print_info = render_project_pdf(
        source,
        {"photo-1": photo},
        "print",
        print_specification={"spineWidthInches": 0.2, "bleedInches": 0.125, "safeMarginInches": 0.25},
    )
    printed = PdfReader(io.BytesIO(print_bytes), strict=True)
    assert len(printed.pages) == 3
    assert print_info["pageCount"] == 3
    assert float(printed.pages[0].mediabox.width) == pytest.approx((16 + 0.2 + 0.25) * 72)
    assert float(printed.pages[1].mediabox.width) == pytest.approx((8 + 0.25) * 72)
    assert round(float(printed.pages[1].trimbox.width), 2) == 8 * 72
    assert round(float(printed.pages[1].trimbox.height), 2) == 8 * 72
    assert "Front cover title" in printed.pages[0].extract_text()
    assert "Back cover" in printed.pages[0].extract_text()
    assert "Page one in saved order" in printed.pages[1].extract_text()
    assert "A second page caption" in printed.pages[2].extract_text()
    assert len(printed.pages[2].images) == 1
    assert print_info["checksumSha256"]


def test_digital_cover_uses_project_background_and_does_not_duplicate_cover_face_content():
    source = document_with_photos()
    cover = next(page for page in source["pages"] if page["type"] == "cover")
    cover["background"] = {
        "color": "#355849",
        "borderColor": "#111111",
        "borderStyle": "solid",
    }
    source["cover"]["design"]["front"]["photoAssetId"] = None
    cover["elements"] = [
        {
            "id": "duplicate-cover-photo",
            "type": "image",
            "assetId": "photo-1",
            "x": 0.08,
            "y": 0.08,
            "width": 0.84,
            "height": 0.84,
        },
        {
            "id": "duplicate-cover-title",
            "type": "text",
            "text": "Front cover title",
            "x": 0.1,
            "y": 0.1,
            "width": 0.8,
            "height": 0.1,
        },
    ]

    pdf_bytes, _ = render_project_pdf(source, {"photo-1": make_image()}, "digital")
    first_page = PdfReader(io.BytesIO(pdf_bytes), strict=True).pages[0]
    rendered_page = pypdfium2.PdfDocument(pdf_bytes)[0].render(scale=1).to_pil().convert("RGB")
    pixel = rendered_page.getpixel((2, 2))
    assert pixel == (53, 88, 73)
    assert first_page.extract_text().count("Front cover title") == 1
    assert len(first_page.images) == 1

    source["cover"]["design"]["front"]["photoAssetId"] = "photo-1"
    photographed_pdf, _ = render_project_pdf(source, {"photo-1": make_image()}, "digital")
    photographed_cover = PdfReader(io.BytesIO(photographed_pdf), strict=True).pages[0]
    assert photographed_cover.extract_text().count("Front cover title") == 1
    assert len(photographed_cover.images) == 1


def test_print_renderer_rejects_low_resolution_images_and_unsafe_text():
    source = document_with_photos()
    with pytest.raises(PdfRenderError, match="below the required 300 DPI"):
        render_project_pdf(source, {"photo-1": make_image((600, 600))}, "print")

    unsafe = document_with_photos()
    unsafe_page = next(page for page in unsafe["pages"] if page["id"] == "interior-first")
    unsafe_page["elements"][0]["x"] = 0.01
    with pytest.raises(PdfRenderError, match="safe margin"):
        render_project_pdf(unsafe, {"photo-1": make_image()}, "print")


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
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    assert response.status_code == 200
    csrf = next(
        value.split(";", 1)[0].split("=", 1)[1]
        for value in response.headers.getlist("Set-Cookie")
        if value.startswith("csrf_access_token=")
    )
    return client, {"X-CSRF-TOKEN": csrf}


def test_pdf_order_creation_persists_status_history_with_order_id(app):
    client, csrf = authenticated_client(app, "pdf-history@example.test")
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "pdf-history@example.test"))
        category = BookCategory(name="Order tests", slug="pdf-history")
        db.session.add(category)
        db.session.flush()
        product = BookProduct(
            category_id=category.id,
            title="Order test book",
            slug="pdf-history-book",
            description="A book for the PDF order history regression test.",
            book_type="BASIC",
            page_count_min=1,
            page_count_max=80,
            starting_price=Decimal("10.00"),
            currency="PKR",
            is_active=True,
            admin_metadata={"pdfPrice": "850.00", "basePageCount": 1},
        )
        db.session.add(product)
        db.session.flush()
        project = UserProject(
            user_id=user.id,
            product_id=product.id,
            title="Order test project",
            page_count=2,
            version=1,
            status="completed",
            document=document_with_photos(),
        )
        db.session.add(project)
        db.session.commit()
        project_id = project.id

    response = client.post(
        "/api/v1/pdf/orders",
        json={"projectId": project_id, "provider": "manual"},
        headers={**csrf, "Idempotency-Key": "pdf-order-history-regression"},
    )

    assert response.status_code == 201, response.get_json()
    with app.app_context():
        history = db.session.scalar(
            db.select(OrderStatusHistory).where(
                OrderStatusHistory.pdf_order_id == response.json["id"],
                OrderStatusHistory.status == "order_placed",
            )
        )
        assert history is not None
        assert history.pdf_order_id == response.json["id"]
        assert history.print_order_id is None


def test_pdf_generation_requires_payment_is_idempotent_and_download_is_owner_scoped(app):
    client, csrf = authenticated_client(app, "reader@example.test")
    fake_storage = MemoryStorage()
    app.extensions["asset_storage"] = fake_storage
    photo = make_image()
    fake_storage.objects["projects/photo-1.jpg"] = (photo, "image/jpeg")
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "reader@example.test"))
        project = UserProject(
            user_id=user.id,
            title="A Saved Memorybook",
            status="completed",
            page_count=2,
            version=3,
            document=document_with_photos(),
        )
        db.session.add(project)
        db.session.flush()
        db.session.add(ProjectAsset(
            id="photo-1",
            project_id=project.id,
            storage_key="projects/photo-1.jpg",
            mime_type="image/jpeg",
            byte_size=len(photo),
            checksum_sha256="f" * 64,
            original_filename="memory.jpg",
            width_px=3000,
            height_px=3000,
        ))
        revision = ProjectRevision(
            project_id=project.id,
            revision_number=1,
            document_version=3,
            document=document_with_photos(),
            checksum_sha256="e" * 64,
        )
        db.session.add(revision)
        db.session.flush()
        order = PdfOrder(
            order_number="PDF-ENGINE-1",
            user_id=user.id,
            project_id=project.id,
            project_revision_id=revision.id,
            status="pending",
            currency="USD",
            service_price=Decimal("8.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("8.00"),
            price_snapshot={"printPdfIncluded": True},
            page_count=2,
        )
        db.session.add(order)
        db.session.commit()
        db.session.add(Payment(
            user_id=user.id,
            pdf_order_id=order.id,
            provider="stripe",
            status="successful",
            amount=Decimal("8.00"),
            currency="USD",
            provider_payment_id="pi_verified-test",
        ))
        db.session.commit()
        order_id = order.id

    unpaid = client.post(f"/api/v1/pdf/orders/{order_id}/generate", json={"profile": "digital"}, headers=csrf)
    assert unpaid.status_code == 409
    with app.app_context():
        order = db.session.get(PdfOrder, order_id)
        order.status = "paid"
        order.paid_at = datetime.now(UTC)
        db.session.commit()

    generated = client.post(f"/api/v1/pdf/orders/{order_id}/generate", json={"profile": "digital"}, headers=csrf)
    duplicate = client.post(f"/api/v1/pdf/orders/{order_id}/generate", json={"profile": "digital"}, headers=csrf)
    assert generated.status_code == 202
    assert duplicate.status_code == 202
    assert generated.json["job"]["id"] == duplicate.json["job"]["id"]
    job_id = generated.json["job"]["id"]
    with app.app_context():
        background_job = db.session.scalar(
            db.select(BackgroundJob).where(
                BackgroundJob.job_type == "generate_pdf",
                BackgroundJob.reference_id == job_id,
            )
        )
        assert background_job.status == "queued"
        background_job_id = background_job.id
        assert db.session.scalar(
            db.select(db.func.count()).select_from(BackgroundJob).where(
                BackgroundJob.job_type == "generate_pdf",
                BackgroundJob.reference_id == job_id,
            )
        ) == 1
    app.extensions["background_jobs"]._run_job(background_job_id)
    with app.app_context():
        background_job = db.session.get(BackgroundJob, background_job_id)
        assert background_job.status == "completed"
        assert db.session.get(PdfJob, job_id).status == "ready"
    assert fake_storage.objects[f"generated/pdf/{order_id}/digital/{job_id}.pdf"][1] == "application/pdf"
    notifications = client.get("/api/v1/payments/notifications")
    assert notifications.status_code == 200
    assert any(item["title"] == "PDF ready" for item in notifications.json["items"])

    downloads = client.get("/api/v1/pdf/downloads")
    assert downloads.status_code == 200
    assert len(downloads.json["items"]) == 1
    entitlement_id = downloads.json["items"][0]["id"]
    link = client.get(f"/api/v1/pdf/downloads/{entitlement_id}")
    assert link.status_code == 200
    assert link.json["download"]["url"].startswith("/api/v1/assets/private/")
    assert link.json["download"]["checksumSha256"]
    private_pdf = client.get(link.json["download"]["url"])
    assert private_pdf.status_code == 200
    assert private_pdf.mimetype == "application/pdf"
    assert private_pdf.headers["Cache-Control"] == "private, no-store"
    with app.app_context():
        assert db.session.scalar(db.select(DownloadEntitlement).where(DownloadEntitlement.id == entitlement_id)).download_count == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(DownloadHistory)) == 1
        assert db.session.scalar(db.select(PdfJob).where(PdfJob.id == job_id)).status == "ready"

    other_client, _ = authenticated_client(app, "other-reader@example.test")
    assert other_client.get(link.json["download"]["url"]).status_code == 404
    assert other_client.get(f"/api/v1/pdf/jobs/{job_id}").status_code == 404
    assert other_client.get(f"/api/v1/pdf/downloads/{entitlement_id}").status_code == 404
