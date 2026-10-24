import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from memorybook.errors import ConflictError, ServiceUnavailableError, ValidationError
from memorybook.extensions import db
from memorybook.integrations.payment_gateways import (
    CheckoutSession,
    StripeGateway,
    available_payment_methods,
    provider_for,
)
from memorybook.models import (
    DownloadEntitlement,
    GeneratedFile,
    Payment,
    PaymentAttempt,
    PaymentWebhookEvent,
    PdfOrder,
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


def test_payment_methods_fail_closed_for_unverified_pkr_gateways(app, client):
    with app.app_context():
        app.config.update(
            PAYMENT_PRIMARY_GATEWAY="payfast",
            PAYFAST_ENABLED=True,
            PAYFAST_CONTRACT_VERIFIED=True,
            JAZZCASH_ENABLED=True,
            JAZZCASH_CHECKOUT_CONTRACT_VERIFIED=True,
            JAZZCASH_CALLBACK_CONTRACT_VERIFIED=False,
        )
        assert available_payment_methods("PKR") == []
        with pytest.raises(ServiceUnavailableError):
            provider_for("PKR")

    response = client.get("/api/v1/payments/methods?currency=PKR")
    assert response.status_code == 200
    assert response.json == {"currency": "PKR", "items": [], "primaryGateway": "payfast"}


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
        assert available_payment_methods("PKR") == []
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

    assert captured["authorization"] == f"Bearer {api_secret}"


def _make_pdf_payment(
    *,
    paid: bool,
    provider: str = "stripe",
    currency: str = "USD",
) -> tuple[str, str, str | None]:
    user = User(email="payments@example.test", password_hash="test-hash")
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
        provider_reference="cs_test_session" if provider == "stripe" else "MB-test-session",
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
