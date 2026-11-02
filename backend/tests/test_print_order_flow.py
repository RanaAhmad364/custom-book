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
    AdminActivityLog,
    BackgroundJob,
    EmailLog,
    GeneratedFile,
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


def _create_admin(email):
    user = User(email=email, password_hash="test-hash")
    role = db.session.scalar(select(Role).where(Role.name == "admin"))
    if role is None:
        role = Role(name="admin", description="Admin", is_system=True)
        db.session.add(role)
        db.session.flush()
    db.session.add(user)
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.flush()
    return user


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


def test_successful_print_payment_queues_only_expected_admin_events_once(app):
    with app.app_context():
        admin = _create_admin("print-payment-events-admin@example.test")
        _, _, _, order, payment, _ = _create_print_order(
            email="print-payment-events-customer@example.test",
        )
        payments._apply_payment_result(
            payment,
            success=True,
            provider_reference="print-event-capture",
        )
        db.session.commit()

        payments._apply_payment_result(
            db.session.get(Payment, payment.id),
            success=True,
            provider_reference="print-event-capture",
        )
        db.session.commit()

        event_notifications = [
            item
            for item in db.session.scalars(
                select(Notification).where(Notification.user_id == admin.id)
            ).all()
            if (item.data or {}).get("event", "").startswith(
                ("payment_confirmed:", "paid_print_order:", "payment_failed:")
            )
        ]
        assert sorted(item.title for item in event_notifications) == [
            "New paid print order",
            "Payment confirmed",
        ], [(item.title, item.event_key) for item in event_notifications]
        assert all(order.order_number in item.message for item in event_notifications)

        event_emails = [
            item
            for item in db.session.scalars(
                select(EmailLog).where(EmailLog.user_id == admin.id)
            ).all()
            if item.event_key.startswith(
                ("payment_confirmed:", "paid_print_order:", "payment_failed:")
            )
        ]
        assert len(event_emails) == 2
        assert {item.event_key for item in event_emails} == {item.event_key for item in event_notifications}


def test_declined_payment_creates_exactly_one_admin_failure_event_and_email(app):
    with app.app_context():
        admin = _create_admin("declined-payment-events-admin@example.test")
        _, _, _, _, payment, _ = _create_print_order(
            email="declined-payment-events-customer@example.test",
        )
        payments._apply_payment_result(
            payment,
            success=False,
            provider_reference="provider-declined",
        )
        db.session.commit()

        event_notifications = [
            item
            for item in db.session.scalars(
                select(Notification).where(Notification.user_id == admin.id)
            ).all()
            if (item.data or {}).get("event", "").startswith("payment_failed:")
        ]
        event_emails = db.session.scalars(
            select(EmailLog).where(
                EmailLog.user_id == admin.id,
                EmailLog.event_key.like("payment_failed:%"),
            )
        ).all()
        assert len(event_notifications) == 1
        assert event_notifications[0].title == "Payment failed"
        assert len(event_emails) == 1
        assert event_emails[0].event_key == event_notifications[0].event_key


def test_successful_retry_emits_payment_recovered_not_another_failure(app):
    with app.app_context():
        admin = _create_admin("recovered-payment-events-admin@example.test")
        _, _, _, order, payment, _ = _create_print_order(
            email="recovered-payment-events-customer@example.test",
        )
        payments._apply_payment_result(
            payment,
            success=False,
            provider_reference="first-attempt-declined",
        )
        db.session.commit()

        payments._apply_payment_result(
            db.session.get(Payment, payment.id),
            success=True,
            provider_reference="retry-captured",
        )
        db.session.commit()

        events = [
            item
            for item in db.session.scalars(
                select(Notification).where(Notification.user_id == admin.id)
            ).all()
            if (item.data or {}).get("event", "").startswith(
                ("payment_failed:", "payment_recovered:", "payment_confirmed:", "paid_print_order:")
            )
        ]
        assert sorted(item.title for item in events) == [
            "New paid print order",
            "Payment confirmed",
            "Payment failed",
            "Payment recovered",
        ], [(item.title, item.event_key) for item in events]
        recovered = next(item for item in events if item.title == "Payment recovered")
        assert order.order_number in recovered.message
        assert "previous failed attempt" in recovered.message
        assert sum(item.title == "Payment failed" for item in events) == 1
        assert len([
            item
            for item in db.session.scalars(
                select(EmailLog).where(EmailLog.user_id == admin.id)
            ).all()
            if item.event_key.startswith(
                ("payment_failed:", "payment_recovered:", "payment_confirmed:", "paid_print_order:")
            )
        ]) == 4


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


def test_paypal_print_order_full_production_and_tracking_flow(app, monkeypatch):
    class MemoryStorage:
        def __init__(self):
            self.objects = {}

        def upload(self, key, stream, content_type):
            self.objects[key] = (stream.read(), content_type)

        def download(self, key):
            return self.objects[key][0]

        def content_type(self, key):
            return self.objects[key][1]

        def private_download_url(self, key):
            return f"/private/{key}"

    app.config.update(
        PAYPAL_MODE="sandbox",
        PAYPAL_CLIENT_ID="sandbox-client",
        PAYPAL_CLIENT_SECRET="sandbox-secret",
    )
    customer_email = "paypal-print-e2e@example.test"
    admin_email = "paypal-print-e2e-admin@example.test"
    customer, customer_csrf = _authenticated_client(app, customer_email)
    admin, admin_csrf = _authenticated_client(app, admin_email)
    storage = MemoryStorage()
    app.extensions["asset_storage"] = storage

    with app.app_context():
        admin_user = db.session.scalar(select(User).where(User.email == admin_email))
        admin_role = db.session.scalar(select(Role).where(Role.name == "admin"))
        if admin_role is None:
            admin_role = Role(name="admin", description="Admin", is_system=True)
            db.session.add(admin_role)
            db.session.flush()
        db.session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
        db.session.flush()
        _, project, original_revision, order, payment, _ = _create_print_order(
            email=customer_email,
        )
        original_revision_id = original_revision.id
        order.currency = "USD"
        order.total_amount = Decimal("16.00")
        order.book_amount = Decimal("16.00")
        order.printing_amount = Decimal("0.00")
        order.shipping_amount = Decimal("0.00")
        payment.currency = "USD"
        payment.amount = Decimal("16.00")
        payment.usd_amount = Decimal("16.00")
        order_id, payment_id, project_id = order.id, payment.id, project.id
        order_number = order.order_number
        original_document = original_revision.document
        changed_document = {**project.document, "metadata": {"title": "Changed after order submission"}}
        project.document = changed_document
        project.version += 1
        db.session.commit()

    monkeypatch.setattr(
        "memorybook.integrations.payment_gateways.PayPalGateway.create_smart_order",
        lambda _self, _payment, _reference_id, _key: "PAYPAL-PRINT-E2E",
    )
    monkeypatch.setattr(
        "memorybook.integrations.payment_gateways.PayPalGateway.capture_order",
        lambda _self, paypal_order_id, _key: {
            "id": paypal_order_id,
            "status": "COMPLETED",
            "purchase_units": [{
                "reference_id": order_number,
                "payments": {"captures": [{
                    "id": "PAYPAL-PRINT-E2E-CAPTURE",
                    "status": "COMPLETED",
                    "amount": {"currency_code": "USD", "value": "16.00"},
                }]},
            }],
        },
    )
    paypal_order = customer.post(
        f"/api/v1/payments/{payment_id}/paypal/create-order",
        headers=customer_csrf,
    )
    assert paypal_order.status_code == 200, paypal_order.get_json()
    captured = customer.post(
        f"/api/v1/payments/{payment_id}/paypal/capture-order",
        json={"paypalOrderId": paypal_order.json["paypalOrderId"]},
        headers=customer_csrf,
    )
    assert captured.status_code == 200, captured.get_json()
    assert captured.json["status"] == "successful"

    with app.app_context():
        print_job = db.session.scalar(
            select(PdfJob).where(PdfJob.generation_profile == "print")
        )
        digital_job = db.session.scalar(
            select(PdfJob).where(PdfJob.generation_profile == "digital")
        )
        print_background_id = db.session.scalar(
            select(BackgroundJob.id).where(
                BackgroundJob.job_type == "generate_pdf",
                BackgroundJob.reference_id == print_job.id,
            )
        )
        digital_background_id = db.session.scalar(
            select(BackgroundJob.id).where(
                BackgroundJob.job_type == "generate_pdf",
                BackgroundJob.reference_id == digital_job.id,
            )
        )
        free_pdf_order = db.session.scalar(
            select(PdfOrder).where(PdfOrder.idempotency_key == f"print-free:{order_id}")
        )
        frozen_revision_id = free_pdf_order.project_revision_id
        assert frozen_revision_id == original_revision_id
        assert print_background_id and digital_background_id

    from memorybook.services import pdf_generation

    renderer = pdf_generation.render_project_pdf
    rendered_documents = []

    def capture_rendered_document(document, *args, **kwargs):
        rendered_documents.append(document)
        return renderer(document, *args, **kwargs)

    monkeypatch.setattr(pdf_generation, "render_project_pdf", capture_rendered_document)
    app.extensions["background_jobs"]._run_job(digital_background_id)
    app.extensions["background_jobs"]._run_job(print_background_id)

    with app.app_context():
        print_job = db.session.get(PdfJob, print_job.id)
        generated_file = db.session.scalar(
            select(GeneratedFile).where(
                GeneratedFile.pdf_order_id == free_pdf_order.id,
                GeneratedFile.generation_profile == "print",
            )
        )
        assert print_job.status == "ready"
        assert generated_file is not None
        print_bytes = storage.download(generated_file.storage_key)
        assert print_bytes.startswith(b"%PDF")
        assert rendered_documents
        assert all(document == original_document for document in rendered_documents)

    admin_pdf_link = admin.get(f"/api/v1/admin/orders/print/{order_id}/pdf")
    assert admin_pdf_link.status_code == 200, admin_pdf_link.get_json()
    admin_pdf = admin.get(f"/api/v1{admin_pdf_link.json['url']}")
    assert admin_pdf.status_code == 200
    assert admin_pdf.mimetype == "application/pdf"
    assert admin_pdf.data.startswith(b"%PDF")
    with app.app_context():
        assert db.session.scalar(
            select(AdminActivityLog.id).where(
                AdminActivityLog.action == "private_print_order.pdf_accessed",
                AdminActivityLog.target_id == order_id,
            )
        )

    for status, extra in (
        ("processing", {}),
        ("printed", {}),
        ("shipped", {"carrier": "Sandbox Courier", "trackingNumber": "SBX-TRACK-2101"}),
        ("out_for_delivery", {}),
        ("delivered", {}),
    ):
        response = admin.patch(
            f"/api/v1/admin/orders/print/{order_id}",
            json={"status": status, **extra},
            headers=admin_csrf,
        )
        assert response.status_code == 200, response.get_json()

    order_response = customer.get(f"/api/v1/print/orders/{order_id}")
    assert order_response.status_code == 200
    statuses = [item["status"] for item in order_response.json["statusHistory"]]
    assert statuses[-5:] == ["processing", "printed", "shipped", "out_for_delivery", "delivered"]
    assert order_response.json["shipment"]["carrier"] == "Sandbox Courier"
    assert order_response.json["shipment"]["trackingNumber"] == "SBX-TRACK-2101"
    assert order_response.json["shippingAddress"]["city"] == "Lahore"

    customer_notifications = customer.get("/api/v1/payments/notifications")
    assert customer_notifications.status_code == 200
    titles = {item["title"] for item in customer_notifications.json["items"]}
    assert {
        "Payment received",
        "Your book is being prepared",
        "Your book has been printed",
        "Your book has been shipped",
        "Your book is out for delivery",
        "Your book has been delivered",
    } <= titles
    admin_notifications = admin.get("/api/v1/admin/notifications")
    assert admin_notifications.status_code == 200
    assert any(item["title"] == "New paid print order" for item in admin_notifications.json["items"])

    with app.app_context():
        pending_email_jobs = db.session.scalars(
            select(BackgroundJob.id).where(
                BackgroundJob.job_type.in_(("send_admin_email", "send_notification_email")),
                BackgroundJob.status == "queued",
            )
        ).all()
    for background_id in pending_email_jobs:
        app.extensions["background_jobs"]._run_job(background_id)
    delivered_subjects = {subject for _, subject, _ in app.extensions["auth_email_outbox"]}
    assert {
        "New paid print order",
        "Payment received",
        "Your book is being prepared",
        "Your book has been printed",
        "Your book has been shipped",
        "Your book is out for delivery",
        "Your book has been delivered",
    } <= delivered_subjects
    with app.app_context():
        email_logs = db.session.scalars(
            select(EmailLog).where(
                EmailLog.template_key.in_(
                    ("paid_print_order", "payment_confirmed", "order_status")
                )
            )
        ).all()
        assert email_logs
        assert all(log.status == "sent" for log in email_logs)


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
