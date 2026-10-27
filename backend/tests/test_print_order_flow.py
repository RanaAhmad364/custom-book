import io
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from PIL import Image
import pytest
from sqlalchemy import select
from werkzeug.exceptions import NotFound

from memorybook.errors import ConflictError
from memorybook.extensions import db
from memorybook.models import (
    EmailLog,
    Notification,
    OrderStatusHistory,
    Payment,
    PaymentAttempt,
    PdfJob,
    PdfOrder,
    Role,
    PrintOrder,
    ProjectAsset,
    ProjectRevision,
    ShippingAddress,
    Shipment,
    User,
    UserRole,
    UserProject,
)
from memorybook.services import payments
from memorybook.services.orders import cancel_unpaid_print_order, expire_pending_print_orders
from memorybook.tasks.background_jobs import PermanentJobError
from memorybook.tasks.pdf_generation import generate_pdf_in_process


def _create_print_order(*, created_at=None, email="print-flow@example.test"):
    user = db.session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash="test-hash")
        db.session.add(user)
        db.session.flush()
    document = {
        "schemaVersion": 1,
        "metadata": {"title": "Print workflow story"},
        "book": {"pageCount": 2, "size": {"width": 8, "height": 8}},
        "pageOrder": ["cover", "inside"],
        "pages": [
            {"id": "cover", "type": "cover", "label": "Cover", "background": {"color": "#ffffff"}, "elements": []},
            {
                "id": "inside",
                "type": "page",
                "label": "Inside",
                "background": {"color": "#ffffff"},
                "elements": [],
            },
        ],
        "assets": [],
    }
    project = UserProject(
        user_id=user.id,
        title="Print workflow story",
        page_count=2,
        version=1,
        document=document,
    )
    db.session.add(project)
    db.session.flush()
    revision = ProjectRevision(
        project_id=project.id,
        revision_number=1,
        document_version=1,
        document=document,
        checksum_sha256="b" * 64,
    )
    address = ShippingAddress(
        user_id=user.id,
        recipient_name="Print Customer",
        address_line_1="1 Story Lane",
        city="Lahore",
        postal_code="54000",
        country_code="PK",
    )
    db.session.add_all([revision, address])
    db.session.flush()
    order = PrintOrder(
        order_number=f"PRT-{user.id[:12]}",
        user_id=user.id,
        project_id=project.id,
        project_revision_id=revision.id,
        shipping_address_id=address.id,
        shipping_address_snapshot={"fullName": "Print Customer", "city": "Lahore"},
        status="pending_payment",
        currency="PKR",
        book_amount=Decimal("1000.00"),
        printing_amount=Decimal("500.00"),
        additional_pages_amount=Decimal("0.00"),
        shipping_amount=Decimal("100.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("1600.00"),
        price_snapshot={
            "pageCount": 2,
            "quantity": 1,
            "sizeName": "Square",
            "coverName": "Hardcover",
            "paperName": "Premium",
            "pdfProfiles": ["digital", "print"],
            "printPdfIncluded": True,
        },
        idempotency_key=f"print-{user.id}",
        created_at=created_at or datetime.now(UTC),
    )
    db.session.add(order)
    db.session.flush()
    payment = Payment(
        user_id=user.id,
        print_order_id=order.id,
        provider="paypal",
        status="pending",
        amount=order.total_amount,
        currency=order.currency,
    )
    db.session.add(payment)
    db.session.flush()
    attempt = PaymentAttempt(
        payment_id=payment.id,
        attempt_number=1,
        status="pending",
        amount=payment.amount,
        idempotency_key=f"{payment.id}:attempt:1",
    )
    db.session.add(attempt)
    db.session.flush()
    return user, project, revision, order, payment, attempt


def _authenticated_client(app, email):
    client = app.test_client()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery"},
    )
    assert response.status_code == 201
    message = app.extensions["auth_email_outbox"][-1][2]
    code = re.search(r"\b(\d{6})\b", message).group(1)
    assert client.post("/api/v1/auth/verify-otp", json={"email": email, "code": code}).status_code == 200
    assert client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "correct-horse-battery"},
    ).status_code == 200
    csrf = client.get_cookie("csrf_access_token").value
    return client, {"X-CSRF-TOKEN": csrf}


def test_customer_print_order_endpoint_returns_history_shipment_and_address(app):
    email = "order-timeline@example.test"
    client, _ = _authenticated_client(app, email)
    with app.app_context():
        user, _, _, order, _, _ = _create_print_order(email=email)
        order.shipping_address_snapshot = {
            "fullName": "Print Customer",
            "line1": "1 Story Lane",
            "city": "Lahore",
            "postalCode": "54000",
            "country": "PK",
        }
        history_items = [
            ("pending_payment", "Print order created."),
            ("payment_confirmed", "Payment verified."),
            ("processing", "Production started."),
            ("printed", "Book printed."),
            ("shipped", "Order shipped."),
            ("out_for_delivery", "Courier is delivering."),
            ("delivered", "Order delivered."),
        ]
        start_time = datetime.now(UTC)
        for index, (status, note) in enumerate(history_items):
            db.session.add(OrderStatusHistory(
                print_order_id=order.id,
                status=status,
                note=note,
                created_at=start_time + timedelta(seconds=index),
            ))
        shipment = Shipment(
            print_order_id=order.id,
            carrier="MemoryShip",
            tracking_number="TRACK-ORDER-1",
            status="delivered",
            shipped_at=start_time + timedelta(seconds=4),
            delivered_at=start_time + timedelta(seconds=6),
        )
        db.session.add(shipment)
        db.session.commit()
        order_id = order.id

    response = client.get(f"/api/v1/print/orders/{order_id}")

    assert response.status_code == 200, response.json
    assert [item["status"] for item in response.json["statusHistory"]] == [
        "pending_payment",
        "payment_confirmed",
        "processing",
        "printed",
        "shipped",
        "out_for_delivery",
        "delivered",
    ]
    assert all(item["id"] and item["createdAt"] for item in response.json["statusHistory"])
    assert response.json["shipment"]["trackingNumber"] == "TRACK-ORDER-1"
    assert response.json["shipment"]["carrier"] == "MemoryShip"
    assert response.json["shipment"]["shippedAt"]
    assert response.json["shipment"]["deliveredAt"]
    assert response.json["shippingAddress"]["city"] == "Lahore"
    assert response.json["shippingAddress"]["country"] == "PK"


def test_payment_received_notification_and_no_smtp_do_not_break_payment(app):
    with app.app_context():
        app.extensions.pop("auth_email_sender", None)
        app.config.update(
            AUTH_EMAIL_MODE="smtp",
            SMTP_HOST=None,
            SMTP_FROM_EMAIL=None,
        )
        user, _, _, order, payment, _ = _create_print_order(email="no-smtp-payment@example.test")
        payments._apply_payment_result(
            payment,
            success=True,
            provider_reference="capture-no-smtp",
            capture_reference="capture-no-smtp",
        )
        db.session.commit()
        db.session.refresh(order)
        db.session.refresh(payment)
        assert payment.status == "successful"
        assert order.paid_at is not None
        notice = db.session.scalar(select(Notification).where(
            Notification.user_id == user.id,
            Notification.event_key == f"payment_confirmed:{payment.id}:user:{user.id}",
        ))
        assert notice is not None
        assert notice.title == "Payment received"
        assert notice.message == f"We received your payment for order {order.order_number}."
        email_log = db.session.scalar(select(EmailLog).where(EmailLog.event_key == notice.event_key))
        assert email_log is not None
        from memorybook.tasks.email_delivery import deliver_email_log

        deliver_email_log(email_log.id)
        db.session.refresh(email_log)
        assert email_log.status == "failed"
        assert email_log.error_message == "Email delivery is not configured."
        assert db.session.get(PrintOrder, order.id).paid_at is not None


def test_print_pdf_failure_notifies_admin_once_with_error_message(app):
    with app.app_context():
        customer, _, revision, order, _, _ = _create_print_order(email="print-pdf-failure-customer@example.test")
        admin_user = User(email="print-pdf-failure-admin@example.test", password_hash="test-hash")
        admin_role = db.session.scalar(select(Role).where(Role.name == "admin"))
        if admin_role is None:
            admin_role = Role(name="admin", description="Admin", is_system=True)
            db.session.add(admin_role)
            db.session.flush()
        db.session.add(admin_user)
        db.session.flush()
        db.session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
        pdf_order = PdfOrder(
            order_number="FREE-PRINT-PDF-FAILURE",
            user_id=customer.id,
            project_id=order.project_id,
            project_revision_id=revision.id,
            status="paid",
            currency=order.currency,
            service_price=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            price_snapshot={"total": "0.00"},
            page_count=order.price_snapshot["pageCount"],
            paid_at=datetime.now(UTC),
            idempotency_key=f"print-free:{order.id}",
        )
        db.session.add(pdf_order)
        db.session.flush()
        job = PdfJob(order_id=pdf_order.id, generation_profile="print", status="queued")
        db.session.add(job)
        db.session.flush()
        job.status = "failed"
        job.error_code = "low_resolution"
        job.error_message = "Photo on page 2 is below print resolution."
        db.session.commit()

        notice_key = f"print_pdf_failed:{job.id}:admin:{admin_user.id}"
        notice = db.session.scalar(select(Notification).where(Notification.event_key == notice_key))
        assert notice is not None
        assert notice.title == "Print PDF generation failed"
        assert order.order_number in notice.message
        assert "Photo on page 2 is below print resolution." in notice.message
        email_log = db.session.scalar(select(EmailLog).where(EmailLog.event_key == notice_key))
        assert email_log is not None
        assert email_log.recipient_email == admin_user.email

        job.error_message = "A repeated failure must not create another alert."
        db.session.commit()
        assert db.session.scalar(
            select(db.func.count(Notification.id)).where(Notification.event_key == notice_key)
        ) == 1


def test_unpaid_print_order_can_be_cancelled_by_its_owner(app):
    with app.app_context():
        user, _, _, order, payment, attempt = _create_print_order()
        db.session.commit()
        result = cancel_unpaid_print_order(order.id, user.id)
        assert result["status"] == "cancelled"
        assert db.session.get(Payment, payment.id).status == "failed"
        assert db.session.get(PaymentAttempt, attempt.id).status == "cancelled"
        assert db.session.scalar(
            select(OrderStatusHistory).where(
                OrderStatusHistory.print_order_id == order.id,
                OrderStatusHistory.status == "cancelled",
            )
        )
        assert db.session.scalar(select(Notification).where(Notification.user_id == user.id))
        with pytest.raises(NotFound):
            cancel_unpaid_print_order(order.id, "another-customer")


def test_expiry_cleanup_cancels_unpaid_orders_and_late_capture_is_refunded(app, monkeypatch):
    with app.app_context():
        app.config["PRINT_ORDER_PAYMENT_EXPIRY_HOURS"] = 24
        due = datetime.now(UTC)
        user, _, _, order, payment, attempt = _create_print_order(
            created_at=due - timedelta(hours=25),
            email="expired-print@example.test",
        )
        db.session.commit()
        with pytest.raises(ConflictError, match="expired"):
            payments.create_payment(order, "print", "paypal", "late-attempt")
        assert expire_pending_print_orders(now=due) == 1
        assert db.session.get(PrintOrder, order.id).status == "cancelled"
        assert db.session.get(Payment, payment.id).status == "failed"
        assert db.session.get(PaymentAttempt, attempt.id).status == "cancelled"
        assert expire_pending_print_orders(now=due) == 0
        payment.usd_amount = Decimal("5.00")
        db.session.commit()

        refunds = []
        monkeypatch.setattr(
            payments,
            "request_refund",
            lambda *args: refunds.append(args) or {"status": "pending"},
        )
        payments._process_verified_event(
            provider="paypal",
            event_id="late-print-capture-event",
            event_type="PAYMENT.CAPTURE.COMPLETED",
            safe_payload={"id": "late-print-capture-event"},
            payment_id=payment.id,
            provider_reference="late-capture",
            success=True,
            failure=False,
            refund_event=False,
            amount=Decimal("5.00"),
            currency="USD",
            provider_payload={},
            capture_reference="late-capture",
        )
        assert db.session.get(Payment, payment.id).status == "successful"
        assert db.session.get(PrintOrder, order.id).status == "cancelled"
        assert db.session.get(PrintOrder, order.id).paid_at is None
        assert refunds and refunds[0][0] == payment.id


def test_verified_print_payment_unlocks_pdf_and_queues_both_profiles(app, monkeypatch):
    dispatched = []
    monkeypatch.setattr("memorybook.tasks.dispatch.dispatch_pdf_generation", dispatched.append)
    with app.app_context():
        user, _, revision, order, payment, attempt = _create_print_order(email="paid-print@example.test")
        db.session.commit()
        payments._apply_payment_result(
            payment,
            success=True,
            provider_reference="capture-print-1",
            capture_reference="capture-print-1",
        )
        db.session.commit()
        assert order.status == "payment_confirmed"
        assert order.paid_at is not None
        free_order = db.session.scalar(
            select(PdfOrder).where(PdfOrder.idempotency_key == f"print-free:{order.id}")
        )
        assert free_order is not None
        assert free_order.project_revision_id == revision.id
        assert free_order.total_amount == Decimal("0.00")
        assert db.session.scalar(
            select(Payment).where(Payment.pdf_order_id == free_order.id)
        ).status == "successful"
        assert payments._create_print_pdf_entitlement(order).id == free_order.id

        payments._queue_print_order_pdfs(payment)
        jobs = db.session.scalars(select(PdfJob).where(PdfJob.order_id == free_order.id)).all()
        assert {job.generation_profile for job in jobs} == {"digital", "print"}
        assert all(job.status == "queued" for job in jobs)
        assert len(dispatched) == 2
        assert db.session.get(PaymentAttempt, attempt.id).status == "successful"


def test_customer_can_retry_failed_print_pdf_after_replacing_low_resolution_photo(app, monkeypatch):
    class MemoryStorage:
        def __init__(self):
            self.objects = {}

        def download(self, key):
            return self.objects[key]

        def upload(self, key, stream, _content_type):
            self.objects[key] = stream.read()

        def private_download_url(self, key):
            return f"/private/{key}"

    def jpeg(size):
        stream = io.BytesIO()
        Image.new("RGB", size, (50, 90, 60)).save(stream, format="JPEG")
        return stream.getvalue()

    email = "print-pdf-retry@example.test"
    client, csrf = _authenticated_client(app, email)
    storage = MemoryStorage()
    app.extensions["asset_storage"] = storage
    storage.objects["projects/tiny.jpg"] = jpeg((500, 500))
    with app.app_context():
        user, project, _, order, payment, _ = _create_print_order(email=email)
        document = {
            "schemaVersion": 1,
            "metadata": {"title": "Print retry story"},
            "book": {"pageCount": 1, "size": {"width": 8, "height": 8}},
            "pageOrder": ["cover", "inside"],
            "pages": [
                {"id": "cover", "type": "cover", "label": "Cover", "background": {"color": "#ffffff"}, "elements": []},
                {
                    "id": "inside",
                    "type": "page",
                    "label": "Page 1",
                    "background": {"color": "#ffffff"},
                    "elements": [{
                        "id": "page-photo",
                        "type": "image",
                        "assetId": "tiny-photo",
                        "x": 0.1,
                        "y": 0.1,
                        "width": 0.8,
                        "height": 0.8,
                        "fit": "cover",
                        "zoom": 1,
                        "cropX": 0.5,
                        "cropY": 0.5,
                    }],
                },
            ],
            "assets": [],
        }
        project.document = document
        project.version = 2
        db.session.add(ProjectAsset(
            id="tiny-photo",
            project_id=project.id,
            storage_key="projects/tiny.jpg",
            mime_type="image/jpeg",
            byte_size=len(storage.objects["projects/tiny.jpg"]),
            checksum_sha256="c" * 64,
            original_filename="tiny.jpg",
            width_px=500,
            height_px=500,
        ))
        revision = ProjectRevision(
            project_id=project.id,
            revision_number=2,
            document_version=2,
            document=document,
            checksum_sha256="d" * 64,
        )
        db.session.add(revision)
        db.session.flush()
        order.project_revision_id = revision.id
        db.session.commit()
        project_id = project.id
        revision_id = revision.id
        payments._apply_payment_result(
            payment,
            success=True,
            provider_reference="capture-retry",
            capture_reference="capture-retry",
        )
        db.session.commit()
        order_id = order.id
        payment_id = payment.id

    dispatched = []
    monkeypatch.setattr("memorybook.tasks.dispatch.dispatch_pdf_generation", dispatched.append)
    with app.app_context():
        payments._queue_print_order_pdfs(db.session.get(Payment, payment_id))
        print_job = db.session.scalar(
            select(PdfJob).where(PdfJob.generation_profile == "print")
        )
        print_job_id = print_job.id
    with app.app_context(), pytest.raises(PermanentJobError):
        generate_pdf_in_process(print_job_id, attempt=1, maximum=1)
    with app.app_context():
        failed_job = db.session.get(PdfJob, print_job_id)
        assert failed_job.status == "failed"
        assert failed_job.error_code == "low_resolution_image"
        assert 'Photo "tiny.jpg" on page "Page 1"' in failed_job.error_message
        assert db.session.get(PrintOrder, order_id).status == "payment_confirmed"
        customer_order = payments.serialize_order(db.session.get(PrintOrder, order_id), "print")
        assert customer_order["printPdf"]["print"]["error"]["message"] == failed_job.error_message
        from memorybook.services.admin import _order_dict

        assert _order_dict(db.session.get(PrintOrder, order_id), "print")["printPdf"]["print"]["error"]["message"] == failed_job.error_message

        project = db.session.get(UserProject, project_id)
        new_document = dict(project.document)
        new_pages = [dict(page) for page in new_document["pages"]]
        new_pages[1] = dict(new_pages[1])
        new_pages[1]["elements"] = [dict(element) for element in new_pages[1]["elements"]]
        new_pages[1]["elements"][0]["assetId"] = "replacement-photo"
        new_document["pages"] = new_pages
        project.document = new_document
        project.version += 1
        storage.objects["projects/replacement.jpg"] = jpeg((3000, 3000))
        db.session.add(ProjectAsset(
            id="replacement-photo",
            project_id=project.id,
            storage_key="projects/replacement.jpg",
            mime_type="image/jpeg",
            byte_size=len(storage.objects["projects/replacement.jpg"]),
            checksum_sha256="e" * 64,
            original_filename="replacement.jpg",
            width_px=3000,
            height_px=3000,
        ))
        db.session.commit()

    response = client.post(f"/api/v1/print/orders/{order_id}/retry-pdf", headers=csrf)
    assert response.status_code == 202, response.get_json()
    assert response.json["job"]["status"] == "queued"
    with app.app_context():
        generate_pdf_in_process(print_job_id, attempt=1, maximum=1)
    with app.app_context():
        assert db.session.get(PdfJob, print_job_id).status == "ready"
        assert db.session.get(PrintOrder, order_id).project_revision_id != revision_id
        assert len(dispatched) == 3
        assert dispatched[-1] == print_job_id
