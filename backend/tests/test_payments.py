import hashlib
import hmac
import json
import re
import time
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from memorybook.errors import ConflictError, ServiceUnavailableError, ValidationError
from memorybook.extensions import db
from memorybook.integrations.payment_gateways import (
    CheckoutSession,
    PayPalGateway,
    StripeGateway,
    available_payment_methods,
    pkr_amount_to_usd,
    pkr_to_usd_rate,
    provider_for,
)
from memorybook.models import (
    DownloadEntitlement,
    GeneratedFile,
    Invoice,
    Payment,
    PaymentAttempt,
    PaymentWebhookEvent,
    PdfOrder,
    OrderStatusHistory,
    Notification,
    ProjectRevision,
    Refund,
    User,
    UserProject,
)
from memorybook.services import payments
from werkzeug.exceptions import NotFound


def test_payment_routes_are_registered_and_user_history_is_protected(client):
    assert client.get("/api/v1/payments/history").status_code == 401
    assert client.get("/api/v1/payments/notifications").status_code == 401
    webhook = client.post(
        "/api/v1/payments/webhooks/stripe",
        data=b"{}",
        headers={"Stripe-Signature": "invalid"},
    )
    assert webhook.status_code == 400


def test_customer_order_serialization_includes_status_and_paid_at(app):
    paid_at = datetime.now(UTC)
    created_at = datetime.now(UTC)
    pdf_order = SimpleNamespace(
        id="pdf-order-serialization",
        project_id="project-pdf",
        project_revision_id="missing-revision",
        order_number="PDF-SERIALIZATION",
        total_amount=Decimal("850.00"),
        currency="PKR",
        status="paid",
        paid_at=paid_at,
        created_at=created_at,
        page_count=24,
    )
    print_order = SimpleNamespace(
        id="print-order-serialization",
        project_id="project-print",
        project_revision_id="missing-revision",
        order_number="PRT-SERIALIZATION",
        total_amount=Decimal("4250.00"),
        currency="PKR",
        status="payment_confirmed",
        paid_at=paid_at,
        created_at=created_at,
        price_snapshot={},
        book_amount=Decimal("2500.00"),
        printing_amount=Decimal("1000.00"),
        additional_pages_amount=Decimal("0.00"),
        shipping_amount=Decimal("750.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        shipping_address_snapshot={},
    )

    with app.app_context():
        serialized_pdf = payments.serialize_order(pdf_order, "pdf")
        serialized_print = payments.serialize_order(print_order, "print")

    assert serialized_pdf["status"] == "paid"
    assert serialized_pdf["paidAt"] == paid_at.isoformat()
    assert serialized_print["status"] == "payment_confirmed"
    assert serialized_print["paidAt"] == paid_at.isoformat()


def test_payment_methods_fail_closed_for_unverified_pkr_gateways(app, client):
    with app.app_context():
        app.config.update(
            PAYMENT_PRIMARY_GATEWAY="payfast",
            MANUAL_PAYMENTS_ENABLED=True,
            PAYPAL_MODE="sandbox",
            PAYPAL_CLIENT_ID=None,
            PAYPAL_CLIENT_SECRET=None,
            PAYFAST_ENABLED=True,
            PAYFAST_CONTRACT_VERIFIED=True,
            JAZZCASH_ENABLED=True,
            JAZZCASH_CHECKOUT_CONTRACT_VERIFIED=True,
            JAZZCASH_CALLBACK_CONTRACT_VERIFIED=False,
        )
        methods = available_payment_methods("PKR")
        assert {method["provider"] for method in methods} == {"manual"}
        with pytest.raises(ServiceUnavailableError):
            provider_for("PKR")

    response = client.get("/api/v1/payments/methods?currency=PKR")
    assert response.status_code == 200
    assert response.json["currency"] == "PKR"
    assert response.json["primaryGateway"] == "payfast"
    assert {method["provider"] for method in response.json["items"]} == {"manual"}


def test_manual_payment_methods_are_disabled_by_default(app):
    with app.app_context():
        app.config.update(
            MANUAL_PAYMENTS_ENABLED=False,
            PAYPAL_CLIENT_ID=None,
            PAYPAL_CLIENT_SECRET=None,
            PAYPAL_WEBHOOK_ID=None,
        )
        assert available_payment_methods("PKR") == []


def test_paypal_method_and_admin_rate_setting_are_server_configured(app, monkeypatch):
    with app.test_request_context("/api/v1/admin/settings"), app.app_context():
        app.config.update(
            PAYPAL_MODE="sandbox",
            PAYPAL_CLIENT_ID="server-client",
            PAYPAL_CLIENT_SECRET="server-secret",
            PAYPAL_WEBHOOK_ID=None,
            PAYPAL_PKR_TO_USD_RATE="0.0036",
        )
        user = User(email="paypal-admin-rate@example.test", password_hash="test-hash")
        db.session.add(user)
        db.session.flush()
        monkeypatch.setattr(
            "memorybook.permissions.get_authenticated_user",
            lambda: SimpleNamespace(id=user.id),
        )
        from memorybook.services.admin import save_setting

        saved = save_setting({
            "key": "paypal_pkr_to_usd_rate",
            "value": {"rate": "0.0037"},
            "public": False,
        })
        assert saved["value"] == {"rate": "0.0037"}
        assert pkr_to_usd_rate() == Decimal("0.0037")
        method = next(item for item in available_payment_methods("PKR") if item["provider"] == "paypal")
        assert method["method"] == "paypal_checkout"
        assert pkr_amount_to_usd(Decimal("1000.00"), pkr_to_usd_rate()) == Decimal("3.70")

        with pytest.raises(ValidationError, match="conversion rate"):
            save_setting({"key": "paypal_pkr_to_usd_rate", "value": {"rate": "-1"}})


def test_jazzcash_method_stays_blocked_without_server_inquiry_implementation(app):
    with app.app_context():
        app.config.update(
            PAYMENT_PRIMARY_GATEWAY="jazzcash",
            JAZZCASH_ENABLED=True,
            JAZZCASH_CHECKOUT_CONTRACT_VERIFIED=True,
            JAZZCASH_CALLBACK_CONTRACT_VERIFIED=True,
            JAZZCASH_API_URL="https://merchant.example.test/checkout",
            JAZZCASH_MERCHANT_ID="merchant-test",
            JAZZCASH_PASSWORD="password-test",
            JAZZCASH_INTEGRITY_SALT="salt-test",
            PAYMENT_RETURN_URL="https://memorybook.example.test/payment-return",
            JAZZCASH_PAYMENT_METHODS="jazzcash_wallet",
        )
        assert not any(method["provider"] == "jazzcash" for method in available_payment_methods("PKR"))
        with pytest.raises(ServiceUnavailableError):
            provider_for("PKR", "jazzcash", "jazzcash_wallet")


def test_stripe_request_uses_configured_bearer_secret(app, monkeypatch):
    captured = {}
    api_secret = "sk_test_header_validation_only"
    with app.app_context():
        app.config.update(
            STRIPE_ENABLED=True,
            STRIPE_SECRET_KEY=api_secret,
            STRIPE_WEBHOOK_SECRET="whsec_header_validation_only",
        )

        def capture_request(request, provider):
            captured["authorization"] = request.get_header("Authorization")
            return {}

        monkeypatch.setattr("memorybook.integrations.payment_gateways._read_json_response", capture_request)
        StripeGateway()._request("POST", "/v1/checkout/sessions", {}, idempotency_key="header-check")

    assert captured["authorization"] == "Bearer " + api_secret


def _make_pdf_payment(
    *,
    paid: bool,
    provider: str = "stripe",
    currency: str = "USD",
    email: str = "payments@example.test",
) -> tuple[str, str, str | None]:
    user = db.session.scalar(db.select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash="test-hash")
        db.session.add(user)
        db.session.flush()
    project = UserProject(
        user_id=user.id,
        title="Payment test book",
        page_count=24,
        version=1,
        document={"schemaVersion": 1, "pages": []},
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
        order_number="PDF-PAYMENT-TEST",
        user_id=user.id,
        project_id=project.id,
        project_revision_id=revision.id,
        status="paid" if paid else "pending",
        currency=currency,
        service_price=Decimal("8.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("8.00"),
        price_snapshot={"pdfProfiles": ["digital"]},
        page_count=24,
        paid_at=datetime.now(UTC) if paid else None,
    )
    db.session.add(order)
    db.session.flush()
    payment = Payment(
        user_id=user.id,
        pdf_order_id=order.id,
        provider=provider,
        provider_payment_id="cs_test_session" if provider == "stripe" else "MB-test-session",
        status="successful" if paid else "pending",
        amount=Decimal("8.00"),
        currency=currency,
    )
    db.session.add(payment)
    db.session.flush()
    attempt = PaymentAttempt(
        payment_id=payment.id,
        attempt_number=1,
        status="successful" if paid else "pending",
        provider_reference="cs_test_session" if provider == "stripe" else (
            None if provider == "manual" else "MB-test-session"
        ),
        amount=payment.amount,
        idempotency_key=f"{payment.id}:attempt:1",
    )
    db.session.add(attempt)
    download_id = None
    if paid:
        generated_file = GeneratedFile(
            pdf_order_id=order.id,
            generation_profile="digital",
            storage_key=f"generated/{order.id}.pdf",
            file_type="application/pdf",
            byte_size=100,
            checksum_sha256="b" * 64,
        )
        db.session.add(generated_file)
        db.session.flush()
        entitlement = DownloadEntitlement(
            user_id=user.id,
            pdf_order_id=order.id,
            generated_file_id=generated_file.id,
            max_downloads=5,
            expires_at=None,
        )
        db.session.add(entitlement)
        db.session.flush()
        download_id = entitlement.id
    db.session.commit()
    return payment.id, order.id, download_id


def _make_paypal_payment(email="payments@example.test") -> tuple[str, str]:
    payment_id, order_id, _ = _make_pdf_payment(
        paid=False,
        provider="paypal",
        currency="PKR",
        email=email,
    )
    payment = db.session.get(Payment, payment_id)
    payment.amount = Decimal("2800.00")
    payment.pkr_amount = Decimal("2800.00")
    payment.usd_amount = Decimal("10.08")
    payment.exchange_rate = Decimal("0.00360000")
    payment.provider_payment_id = "PAYPAL-ORDER-1"
    order = db.session.get(PdfOrder, order_id)
    order.total_amount = Decimal("2800.00")
    attempt = db.session.scalar(
        db.select(PaymentAttempt).where(PaymentAttempt.payment_id == payment_id)
    )
    attempt.provider_reference = "PAYPAL-ORDER-1"
    db.session.commit()
    return payment_id, order_id


def _make_smart_paypal_payment(email="payments@example.test") -> tuple[str, str]:
    payment_id, order_id = _make_paypal_payment(email)
    payment = db.session.get(Payment, payment_id)
    attempt = db.session.scalar(
        db.select(PaymentAttempt).where(PaymentAttempt.payment_id == payment_id)
    )
    payment.provider_payment_id = None
    attempt.provider_reference = None
    db.session.commit()
    return payment_id, order_id


def _authenticated_payment_client(app, email):
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


def _paypal_completed_capture(order_id, reference_id, capture_id="PAYPAL-SMART-CAPTURE", value="10.08"):
    return {
        "id": order_id,
        "status": "COMPLETED",
        "purchase_units": [{
            "reference_id": reference_id,
            "payments": {"captures": [{
                "id": capture_id,
                "status": "COMPLETED",
                "amount": {"currency_code": "USD", "value": value},
            }]},
        }],
    }


def test_paypal_smart_button_api_owner_create_capture_and_double_capture(app, monkeypatch):
    app.config.update(PAYPAL_MODE="sandbox", PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret")
    email = "paypal-smart-owner@example.test"
    client, csrf = _authenticated_payment_client(app, email)
    with app.app_context():
        payment_id, order_id = _make_smart_paypal_payment(email)
        payment = db.session.get(Payment, payment_id)
        order = db.session.get(PdfOrder, order_id)
        calls = []
        generation_calls = []
        monkeypatch.setattr(
            payments,
            "_queue_pdf_generation",
            lambda item: generation_calls.append(item.id),
        )

        def fake_request(_self, method, path, payload, *, request_id=None):
            calls.append((method, path, payload))
            if path == "/v2/checkout/orders":
                return {"id": "PAYPAL-SMART-ORDER", "status": "CREATED"}
            return _paypal_completed_capture(
                "PAYPAL-SMART-ORDER",
                order.order_number,
            )

        monkeypatch.setattr(PayPalGateway, "_request", fake_request)
        headers = {**csrf, "Idempotency-Key": "paypal-smart-create"}
        created = client.post(
            f"/api/v1/payments/{payment_id}/paypal/create-order",
            headers=headers,
        )
        repeated_create = client.post(
            f"/api/v1/payments/{payment_id}/paypal/create-order",
            headers=headers,
        )
        assert created.status_code == 200
        assert repeated_create.json == created.json
        assert created.json == {
            "paypalOrderId": "PAYPAL-SMART-ORDER",
            "chargedAmountUsd": "10.08",
            "rate": "0.00360000",
        }
        captured = client.post(
            f"/api/v1/payments/{payment_id}/paypal/capture-order",
            json={"paypalOrderId": "PAYPAL-SMART-ORDER"},
            headers=csrf,
        )
        repeated = client.post(
            f"/api/v1/payments/{payment_id}/paypal/capture-order",
            json={"paypalOrderId": "PAYPAL-SMART-ORDER"},
            headers=csrf,
        )
        assert captured.status_code == 200
        assert captured.json["status"] == "successful"
        assert repeated.status_code == 200
        assert repeated.json["status"] == "successful"
        assert [path for _, path, _ in calls].count("/v2/checkout/orders/PAYPAL-SMART-ORDER/capture") == 1
        assert payment.status == "successful"
        assert payment.pkr_amount == Decimal("2800.00")
        assert payment.usd_amount == Decimal("10.08")
        assert payment.exchange_rate == Decimal("0.00360000")
        assert payment.provider_capture_id == "PAYPAL-SMART-CAPTURE"
        assert order.status == "paid"
        assert order.paid_at is not None
        assert generation_calls == [payment_id]
        invoices = db.session.scalars(
            db.select(Invoice).where(Invoice.payment_id == payment_id)
        ).all()
        assert len(invoices) == 1
        assert invoices[0].amount == Decimal("2800.00")
        assert invoices[0].currency == "PKR"


def test_paypal_smart_button_endpoints_reject_wrong_owner(app):
    app.config.update(PAYPAL_MODE="sandbox", PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret")
    client, csrf = _authenticated_payment_client(app, "paypal-smart-other@example.test")
    with app.app_context():
        payment_id, _ = _make_smart_paypal_payment()

    response = client.post(
        f"/api/v1/payments/{payment_id}/paypal/create-order",
        headers=csrf,
    )
    assert response.status_code == 404
    response = client.post(
        f"/api/v1/payments/{payment_id}/paypal/capture-order",
        json={"paypalOrderId": "NOT-OWNED"},
        headers=csrf,
    )
    assert response.status_code == 404


def test_paypal_smart_button_rejects_mismatched_capture_amount(app, monkeypatch):
    app.config.update(PAYPAL_MODE="sandbox", PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret")
    with app.app_context():
        payment_id, order_id = _make_smart_paypal_payment()
        payment = db.session.get(Payment, payment_id)
        monkeypatch.setattr(
            PayPalGateway,
            "create_smart_order",
            lambda *_args: "PAYPAL-SMART-MISMATCH",
        )
        created = payments.create_paypal_order(payment)
        monkeypatch.setattr(
            PayPalGateway,
            "capture_order",
            lambda *_args: _paypal_completed_capture(
                "PAYPAL-SMART-MISMATCH",
                "PDF-PAYMENT-TEST",
                value="9.99",
            ),
        )
        with pytest.raises(ValidationError, match="amount or currency"):
            payments.capture_paypal_order(payment, created["paypalOrderId"])
        db.session.rollback()
        db.session.expire_all()
        assert db.session.get(Payment, payment_id).status == "pending"
        assert db.session.get(PdfOrder, order_id).paid_at is None


def test_paypal_cancelled_capture_can_retry_same_payment(app, monkeypatch):
    app.config.update(PAYPAL_MODE="sandbox", PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret")
    with app.app_context():
        payment_id, order_id = _make_smart_paypal_payment()
        payment = db.session.get(Payment, payment_id)
        order_ids = iter(["PAYPAL-SMART-CANCELLED", "PAYPAL-SMART-RETRY"])
        monkeypatch.setattr(PayPalGateway, "create_smart_order", lambda *_args: next(order_ids))
        first = payments.create_paypal_order(payment)
        monkeypatch.setattr(
            PayPalGateway,
            "capture_order",
            lambda *_args: {"id": first["paypalOrderId"], "status": "VOIDED"},
        )
        failed = payments.capture_paypal_order(payment, first["paypalOrderId"])
        assert failed["status"] == "failed"
        assert payment.status == "failed"
        assert db.session.get(PdfOrder, order_id).paid_at is None

        retried = payments.retry_payment(payment, "paypal-smart-retry", "paypal")
        next_order = payments.create_paypal_order(payment)
        monkeypatch.setattr(
            PayPalGateway,
            "capture_order",
            lambda *_args: _paypal_completed_capture(
                "PAYPAL-SMART-RETRY",
                "PDF-PAYMENT-TEST",
                capture_id="PAYPAL-SMART-RETRY-CAPTURE",
            ),
        )
        completed = payments.capture_paypal_order(payment, next_order["paypalOrderId"])
        attempts = db.session.scalars(
            db.select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment_id)
            .order_by(PaymentAttempt.attempt_number)
        ).all()
        assert retried["paymentStatus"] == "pending"
        assert next_order["paypalOrderId"] == "PAYPAL-SMART-RETRY"
        assert completed["status"] == "successful"
        assert len(attempts) == 2
        assert attempts[0].status == "failed"
        assert attempts[1].status == "successful"
        assert db.session.get(PdfOrder, order_id).paid_at is not None


def test_paypal_webhook_after_smart_capture_does_not_repeat_success_work(app, monkeypatch):
    app.config.update(PAYPAL_MODE="sandbox", PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret")
    with app.app_context():
        payment_id, _order_id = _make_smart_paypal_payment()
        payment = db.session.get(Payment, payment_id)
        monkeypatch.setattr(PayPalGateway, "create_smart_order", lambda *_args: "PAYPAL-SMART-WEBHOOK")
        created = payments.create_paypal_order(payment)
        monkeypatch.setattr(
            PayPalGateway,
            "capture_order",
            lambda *_args: _paypal_completed_capture(
                created["paypalOrderId"],
                "PDF-PAYMENT-TEST",
                capture_id="PAYPAL-SMART-WEBHOOK-CAPTURE",
            ),
        )
        generation_calls = []
        monkeypatch.setattr(payments, "_queue_pdf_generation", lambda item: generation_calls.append(item.id))
        payments.capture_paypal_order(payment, created["paypalOrderId"])
        notifications_before = db.session.scalar(
            db.select(db.func.count(Notification.id)).where(Notification.user_id == payment.user_id)
        )

    event = {
        "id": "WH-PAYPAL-SMART-CAPTURE-LATE",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "PAYPAL-SMART-WEBHOOK-CAPTURE",
            "amount": {"currency_code": "USD", "value": "10.08"},
            "supplementary_data": {"related_ids": {"order_id": "PAYPAL-SMART-WEBHOOK"}},
        },
    }
    monkeypatch.setattr(PayPalGateway, "handle_webhook", lambda *_args: event)
    with app.app_context():
        result = payments.process_paypal_event(json.dumps(event).encode(), _paypal_headers())
        payment = db.session.get(Payment, payment_id)
        notifications_after = db.session.scalar(
            db.select(db.func.count(Notification.id)).where(Notification.user_id == payment.user_id)
        )
        assert result["processed"] is True
        assert payment.status == "successful"
        assert generation_calls == [payment_id]
        assert notifications_after == notifications_before
        assert db.session.scalar(
            db.select(db.func.count(Invoice.id)).where(Invoice.payment_id == payment_id)
        ) == 1


def _paypal_headers():
    return {
        "PayPal-Transmission-Id": "transmission-123",
        "PayPal-Transmission-Time": "2026-10-27T18:00:00Z",
        "PayPal-Transmission-Sig": "signature",
        "PayPal-Cert-Url": "https://api.paypal.com/cert",
        "PayPal-Auth-Algo": "SHA256withRSA",
    }


def _fake_paypal_webhook(monkeypatch, event):
    monkeypatch.setattr(PayPalGateway, "handle_webhook", lambda _self, _body, _headers: event)


def test_paypal_approved_order_captures_and_marks_paid_once(app, monkeypatch):
    with app.app_context():
        payment_id, order_id = _make_paypal_payment()
    event = {
        "id": "WH-PAYPAL-APPROVED-1",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {
            "id": "PAYPAL-ORDER-1",
            "purchase_units": [{"custom_id": payment_id, "reference_id": "PDF-PAYMENT-TEST"}],
        },
    }
    _fake_paypal_webhook(monkeypatch, event)
    captures = []

    def capture_order(_self, paypal_order_id, idempotency_key):
        captures.append((paypal_order_id, idempotency_key))
        return {
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"captures": [{
                "id": "PAYPAL-CAPTURE-1",
                "status": "COMPLETED",
                "amount": {"currency_code": "USD", "value": "10.08"},
            }]}}],
        }

    monkeypatch.setattr(PayPalGateway, "capture_order", capture_order)
    generated = []
    monkeypatch.setattr(payments, "_queue_pdf_generation", lambda payment: generated.append(payment.id))
    with app.app_context():
        result = payments.process_paypal_event(json.dumps(event).encode(), _paypal_headers())
        duplicate = payments.process_paypal_event(json.dumps(event).encode(), _paypal_headers())
        payment = db.session.get(Payment, payment_id)
        order = db.session.get(PdfOrder, order_id)
        assert result["processed"] is True
        assert duplicate["duplicate"] is True
        assert payment.status == "successful"
        assert payment.provider_capture_id == "PAYPAL-CAPTURE-1"
        assert payment.pkr_amount == Decimal("2800.00")
        assert payment.usd_amount == Decimal("10.08")
        assert payment.exchange_rate == Decimal("0.00360000")
        assert order.status == "paid"
        assert order.paid_at is not None
        assert captures == [("PAYPAL-ORDER-1", f"{payment_id}:attempt:1")]
        assert generated == [payment_id]
        history = db.session.scalars(
            db.select(OrderStatusHistory).where(OrderStatusHistory.pdf_order_id == order_id)
        ).all()
        assert [row.status for row in history] == ["paid"]


def test_paypal_wrong_capture_amount_does_not_mark_order_paid(app, monkeypatch):
    with app.app_context():
        payment_id, order_id = _make_paypal_payment()
    event = {
        "id": "WH-PAYPAL-WRONG-AMOUNT",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {
            "id": "PAYPAL-ORDER-1",
            "purchase_units": [{"custom_id": payment_id, "reference_id": "PDF-PAYMENT-TEST"}],
        },
    }
    _fake_paypal_webhook(monkeypatch, event)
    monkeypatch.setattr(
        PayPalGateway,
        "capture_order",
        lambda *_args: {
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"captures": [{
                "id": "PAYPAL-CAPTURE-WRONG",
                "amount": {"currency_code": "USD", "value": "9.99"},
            }]}}],
        },
    )
    with app.app_context(), pytest.raises(ValidationError, match="amount or currency"):
        payments.process_paypal_event(json.dumps(event).encode(), _paypal_headers())
        db.session.rollback()
    with app.app_context():
        db.session.expire_all()
        assert db.session.get(Payment, payment_id).status == "pending"
        assert db.session.get(PdfOrder, order_id).paid_at is None


def test_paypal_bad_webhook_signature_is_rejected(app, monkeypatch):
    app.config.update(
        PAYPAL_MODE="sandbox",
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-123",
    )
    event = {"id": "WH-BAD-SIGNATURE", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "PAYPAL-ORDER-1"}}
    monkeypatch.setattr(PayPalGateway, "_request", lambda *_args, **_kwargs: {"verification_status": "FAILURE"})
    with app.app_context(), pytest.raises(ValidationError, match="signature is invalid"):
        PayPalGateway().handle_webhook(json.dumps(event).encode(), _paypal_headers())


def test_paypal_cancelled_payment_can_retry_without_creating_another_order(app, monkeypatch):
    app.config.update(
        PAYPAL_MODE="sandbox",
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-123",
    )
    with app.app_context():
        payment_id, order_id = _make_paypal_payment()
    event = {
        "id": "WH-PAYPAL-CANCELLED",
        "event_type": "CHECKOUT.ORDER.VOIDED",
        "resource": {"id": "PAYPAL-ORDER-1"},
    }
    _fake_paypal_webhook(monkeypatch, event)
    monkeypatch.setattr(
        PayPalGateway,
        "create_smart_order",
        lambda *_args: "PAYPAL-ORDER-2",
    )
    with app.app_context():
        failed = payments.process_paypal_event(json.dumps(event).encode(), _paypal_headers())
        payment = db.session.get(Payment, payment_id)
        assert failed["processed"] is True
        assert payment.status == "failed"
        assert db.session.get(PdfOrder, order_id).paid_at is None

        retry = payments.retry_payment(payment, "retry-key-1", "paypal")
        created = payments.create_paypal_order(payment)
        attempts = db.session.scalars(
            db.select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment_id)
            .order_by(PaymentAttempt.attempt_number)
        ).all()
        assert retry["paymentStatus"] == "pending"
        assert retry["checkoutUrl"] is None
        assert created["paypalOrderId"] == "PAYPAL-ORDER-2"
        assert len(attempts) == 2
        assert attempts[-1].provider_reference == "PAYPAL-ORDER-2"


def test_paypal_smart_order_uses_server_snapshot_and_order_number_reference(app, monkeypatch):
    app.config.update(
        PAYPAL_MODE="sandbox",
        PAYPAL_CLIENT_ID="server-client-id",
        PAYPAL_CLIENT_SECRET="server-only-secret",
    )
    with app.app_context():
        payment_id, _order_id = _make_paypal_payment()
        payment = db.session.get(Payment, payment_id)
        calls = []

        def fake_request(_self, method, path, payload, *, request_id=None):
            calls.append((method, path, payload, request_id))
            return {"id": "PAYPAL-CREATED-ORDER", "status": "CREATED"}

        monkeypatch.setattr(PayPalGateway, "_request", fake_request)
        paypal_order_id = PayPalGateway().create_smart_order(
            payment,
            "PDF-PAYMENT-TEST",
            "test-idempotency-key",
        )

    assert paypal_order_id == "PAYPAL-CREATED-ORDER"
    assert calls[0][1] == "/v2/checkout/orders"
    assert calls[0][2]["intent"] == "CAPTURE"
    assert calls[0][2]["purchase_units"][0]["reference_id"] == "PDF-PAYMENT-TEST"
    assert "application_context" not in calls[0][2]
    assert calls[0][2]["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "10.08"}


def test_new_paypal_payment_snapshots_pkr_usd_and_admin_rate(app, monkeypatch):
    app.config.update(
        PAYPAL_MODE="sandbox",
        PAYPAL_CLIENT_ID="server-client-id",
        PAYPAL_CLIENT_SECRET="server-only-secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_PKR_TO_USD_RATE="0.0037",
        MANUAL_PAYMENTS_ENABLED=False,
    )
    with app.app_context():
        _old_payment_id, order_id, _ = _make_pdf_payment(paid=False, currency="PKR")
        old_payment = db.session.get(Payment, _old_payment_id)
        db.session.delete(old_payment)
        db.session.flush()
        order = db.session.get(PdfOrder, order_id)
        order.total_amount = Decimal("2800.00")
        order.service_price = Decimal("2800.00")

        monkeypatch.setattr(
            PayPalGateway,
            "create_checkout",
            lambda *_args: CheckoutSession(
                "https://www.sandbox.paypal.com/checkoutnow?token=order",
                "PAYPAL-SNAPSHOT-ORDER",
            ),
        )
        result = payments.create_payment(order, "pdf", "paypal", "new-paypal-payment")
        payment = db.session.scalar(
            db.select(Payment).where(Payment.pdf_order_id == order_id)
        )
        assert result["paymentProvider"] == "paypal"
        assert payment.amount == Decimal("2800.00")
        assert payment.currency == "PKR"
        assert payment.pkr_amount == Decimal("2800.00")
        assert payment.usd_amount == Decimal("10.36")
        assert payment.exchange_rate == Decimal("0.00370000")
        assert result["usdAmount"] == "10.36"


def test_paypal_refund_uses_the_payment_rate_snapshot(app, monkeypatch):
    with app.app_context():
        payment_id, _order_id = _make_paypal_payment()
        payment = db.session.get(Payment, payment_id)
        payment.status = "successful"
        payment.provider_capture_id = "PAYPAL-CAPTURE-REFUND"
        payment.exchange_rate = Decimal("0.00360000")
        captured = {}

        def fake_request(_self, method, path, payload, *, request_id=None):
            captured.update(method=method, path=path, payload=payload, request_id=request_id)
            return {"id": "PAYPAL-REFUND-1", "status": "COMPLETED"}

        monkeypatch.setattr(PayPalGateway, "_request", fake_request)
        refund_id, status = PayPalGateway().refund(payment, Decimal("280.00"), "refund-key-1")

    assert refund_id == "PAYPAL-REFUND-1"
    assert status == "succeeded"
    assert captured["path"] == "/v2/payments/captures/PAYPAL-CAPTURE-REFUND/refund"
    assert captured["payload"]["amount"] == {"value": "1.01", "currency_code": "USD"}


def test_manual_payment_requires_customer_reference_and_admin_approval_before_paid(app, monkeypatch):
    app.config["MANUAL_PAYMENTS_ENABLED"] = True
    with app.app_context():
        payment_id, order_id, _ = _make_pdf_payment(paid=False, provider="manual", currency="PKR")
        payment = db.session.get(Payment, payment_id)
        attempt = db.session.scalar(
            db.select(PaymentAttempt).where(PaymentAttempt.payment_id == payment_id)
        )
        user_id = payment.user_id
        assert attempt.status == "pending"
        assert payment.provider == "manual"

        submitted = payments.submit_manual_payment_reference(payment, user_id, "TXN-849201")
        assert submitted["status"] == "pending"
        assert db.session.get(PdfOrder, order_id).paid_at is None
        assert db.session.get(PaymentAttempt, attempt.id).status == "submitted"

        generated = []
        monkeypatch.setattr(payments, "_queue_pdf_generation", lambda item: generated.append(item.id))
        reviewed = payments.review_manual_payment(payment_id, approved=True, actor_id=user_id)
        order = db.session.get(PdfOrder, order_id)
        assert reviewed["status"] == "successful"
        assert order.paid_at is not None
        assert order.status == "paid"
        assert db.session.get(PaymentAttempt, attempt.id).provider_reference == "TXN-849201"
        assert generated == [payment_id]
        history = db.session.scalars(
            db.select(OrderStatusHistory).where(OrderStatusHistory.pdf_order_id == order_id)
        ).all()
        assert [item.status for item in history][-1] == "paid"
        notices = db.session.scalars(
            db.select(Notification).where(Notification.user_id == user_id)
        ).all()
        assert {item.title for item in notices} >= {"Payment received", "PDF purchased"}


def test_rejected_manual_payment_is_failed_and_not_paid(app):
    app.config["MANUAL_PAYMENTS_ENABLED"] = True
    with app.app_context():
        payment_id, order_id, _ = _make_pdf_payment(paid=False, provider="manual", currency="PKR")
        payment = db.session.get(Payment, payment_id)
        payments.submit_manual_payment_reference(payment, payment.user_id, "TXN-REJECT-9")

        result = payments.review_manual_payment(
            payment_id,
            approved=False,
            actor_id=payment.user_id,
        )

        order = db.session.get(PdfOrder, order_id)
        assert result["status"] == "failed"
        assert order.paid_at is None
        assert order.status == "pending"
        history = db.session.scalars(
            db.select(OrderStatusHistory).where(OrderStatusHistory.pdf_order_id == order_id)
        ).all()
        assert [item.status for item in history][-1] == "payment_failed"
        assert db.session.scalar(
            db.select(Notification.id).where(
                Notification.user_id == payment.user_id,
                Notification.title == "Payment failed",
            )
        )


def test_verified_webhook_is_idempotent_and_updates_payment_once(app, monkeypatch):
    with app.app_context():
        payment_id, order_id, _ = _make_pdf_payment(paid=False)
    generated = []
    monkeypatch.setattr(payments, "_queue_pdf_generation", lambda payment: generated.append(payment.id))

    event_data = {
        "provider": "stripe",
        "event_id": "evt_payment_success",
        "event_type": "checkout.session.completed",
        "safe_payload": {"id": "evt_payment_success"},
        "payment_id": payment_id,
        "provider_reference": "cs_test_session",
        "success": True,
        "failure": False,
        "refund_event": False,
        "amount": Decimal("8.00"),
        "currency": "USD",
        "provider_payload": {},
    }
    with app.app_context():
        first = payments._process_verified_event(**event_data)
        duplicate = payments._process_verified_event(**event_data)
        payment = db.session.get(Payment, payment_id)
        order = db.session.get(PdfOrder, order_id)
        assert first == {"received": True, "processed": True}
        assert duplicate == {"received": True, "duplicate": True}
        assert payment.status == "successful"
        assert order.paid_at is not None
        assert db.session.scalar(
            db.select(db.func.count()).select_from(PaymentWebhookEvent)
        ) == 1
    assert generated == [payment_id]


def test_stripe_webhook_requires_valid_signature_and_matches_order_amount(app, monkeypatch):
    with app.app_context():
        payment_id, _, _ = _make_pdf_payment(paid=False)
    app.config["STRIPE_WEBHOOK_SECRET"] = "test-webhook-secret"
    generated = []
    monkeypatch.setattr(payments, "_queue_pdf_generation", lambda payment: generated.append(payment.id))
    payload = {
        "id": "evt_signed_payment",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_session",
                "payment_intent": "pi_verified",
                "payment_status": "paid",
                "amount_total": 800,
                "currency": "usd",
                "metadata": {"payment_id": payment_id},
            }
        },
    }
    raw_body = json.dumps(payload).encode()
    timestamp = int(time.time())
    digest = hmac.new(
        b"test-webhook-secret",
        str(timestamp).encode() + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    with app.app_context():
        with pytest.raises(ValidationError, match="signature is invalid"):
            payments.process_stripe_event(raw_body, f"t={timestamp},v1=invalid")
        with pytest.raises(ValidationError, match="amount or currency"):
            mismatched = {**payload, "data": {"object": {**payload["data"]["object"], "amount_total": 700}}}
            raw_mismatch = json.dumps(mismatched).encode()
            mismatch_digest = hmac.new(
                b"test-webhook-secret",
                str(timestamp).encode() + b"." + raw_mismatch,
                hashlib.sha256,
            ).hexdigest()
            payments.process_stripe_event(raw_mismatch, f"t={timestamp},v1={mismatch_digest}")
        assert db.session.get(Payment, payment_id).status == "pending"
        result = payments.process_stripe_event(raw_body, f"t={timestamp},v1={digest}")
        assert result["processed"] is True
        assert db.session.get(Payment, payment_id).status == "successful"
    assert generated == [payment_id]


def test_successful_refund_revokes_pdf_entitlement_and_supports_remaining_balance(app, monkeypatch):
    with app.app_context():
        payment_id, _, download_id = _make_pdf_payment(paid=True)
    provider_calls = []

    def fake_refund(self, payment, amount, key):
        provider_calls.append((amount, key))
        return f"re_{len(provider_calls)}", "succeeded"

    monkeypatch.setattr(StripeGateway, "refund", fake_refund)
    with app.app_context():
        partial = payments.request_refund(payment_id, Decimal("3.00"), "Customer request", "refund-1")
        repeated = payments.request_refund(payment_id, Decimal("3.00"), "Customer request", "refund-1")
        payment = db.session.get(Payment, payment_id)
        entitlement = db.session.get(DownloadEntitlement, download_id)
        assert partial["status"] == "succeeded"
        assert repeated["id"] == partial["id"]
        assert payment.status == "partially_refunded"
        assert entitlement.revoked_at is not None

        full = payments.request_refund(payment_id, Decimal("5.00"), "Remaining balance", "refund-2")
        assert full["status"] == "succeeded"
        assert db.session.get(Payment, payment_id).status == "refunded"
    assert len(provider_calls) == 2


def test_failed_payment_retry_is_idempotent_and_keeps_the_selected_provider(app, monkeypatch):
    with app.app_context():
        payment_id, _, _ = _make_pdf_payment(paid=False)
        payment = db.session.get(Payment, payment_id)
        payment.status = "failed"
        attempt = db.session.scalar(db.select(PaymentAttempt).where(PaymentAttempt.payment_id == payment_id))
        attempt.status = "failed"
        db.session.commit()

    class FakeGateway:
        name = "stripe"

        def create_checkout(self, payment, title, idempotency_key):
            provider_calls.append(idempotency_key)
            return CheckoutSession("https://checkout.stripe.com/cs_retry", "cs_retry")

    provider_calls = []
    monkeypatch.setattr(payments, "provider_for", lambda currency, preferred: FakeGateway())
    with app.app_context():
        payment = db.session.get(Payment, payment_id)
        first = payments.retry_payment(payment, "retry-key", "stripe")
        duplicate = payments.retry_payment(payment, "retry-key", "stripe")
        assert first["paymentStatus"] == "pending"
        assert first["checkoutUrl"] == "https://checkout.stripe.com/cs_retry"
        assert duplicate["checkoutUrl"] == first["checkoutUrl"]
        assert db.session.get(Payment, payment_id).status == "pending"
    assert provider_calls == [f"{payment_id}:retry-key"]


def test_uncertain_refund_is_retryable_with_the_same_idempotency_key(app, monkeypatch):
    with app.app_context():
        payment_id, _, _ = _make_pdf_payment(paid=True)
    provider_calls = []

    def retryable_refund(self, payment, amount, key):
        provider_calls.append(key)
        if len(provider_calls) == 1:
            raise ServiceUnavailableError("Provider response was unavailable.")
        return "re_retried", "succeeded"

    monkeypatch.setattr(StripeGateway, "refund", retryable_refund)
    with app.app_context():
        with pytest.raises(ServiceUnavailableError):
            payments.request_refund(payment_id, Decimal("2.00"), "Network retry", "uncertain-refund")
        pending = db.session.scalar(
            db.select(Refund).where(Refund.idempotency_key == "uncertain-refund")
        )
        assert pending.status == "pending"
        result = payments.request_refund(
            payment_id,
            Decimal("2.00"),
            "Network retry",
            "uncertain-refund",
        )
        assert result["status"] == "succeeded"
    assert provider_calls == [f"{payment_id}:uncertain-refund"] * 2


def test_jazzcash_refund_requires_manual_provider_confirmation(app):
    with app.app_context():
        payment_id, _, _ = _make_pdf_payment(paid=True, provider="jazzcash", currency="PKR")
        created = payments.request_refund(payment_id, Decimal("2.00"), "Customer request", "jazzcash-refund")
        assert created["status"] == "manual_required"
        refund = db.session.scalar(
            db.select(Refund).where(Refund.idempotency_key == "jazzcash-refund")
        )
        assert refund.status == "manual_required"
        with pytest.raises(ValidationError, match="verified provider confirmation"):
            payments.complete_manual_refund(refund.id, "succeeded", "JC-REF-001")
        completed = payments.complete_manual_refund(
            refund.id,
            "succeeded",
            "JC-REF-001",
            verified=True,
        )
        assert completed["status"] == "succeeded"


def test_customer_refund_request_is_owned_reserved_and_admin_approvable(app):
    with app.app_context():
        payment_id, _, _ = _make_pdf_payment(paid=True, provider="jazzcash", currency="PKR")
        payment = db.session.get(Payment, payment_id)
        request = payments.create_refund_request(
            payment_id,
            payment.user_id,
            Decimal("3.00"),
            "Order cancellation",
            "customer-refund-1",
        )
        assert request["status"] == "requested"
        repeated = payments.create_refund_request(
            payment_id,
            payment.user_id,
            Decimal("3.00"),
            "Order cancellation",
            "customer-refund-1",
        )
        assert repeated["id"] == request["id"]
        with pytest.raises(NotFound):
            payments.create_refund_request(
                payment_id,
                "another-user",
                Decimal("1.00"),
                "Not my payment",
                "customer-refund-2",
            )
        with pytest.raises(ConflictError, match="unrefunded payment balance"):
            payments.create_refund_request(
                payment_id,
                payment.user_id,
                Decimal("6.00"),
                "Exceeds the remaining payment",
                "customer-refund-3",
            )
        approved = payments.approve_refund_request(request["id"])
        assert approved["status"] == "manual_required"
