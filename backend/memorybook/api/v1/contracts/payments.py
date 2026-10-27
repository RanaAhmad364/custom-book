from __future__ import annotations

from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, jsonify, redirect, request
from sqlalchemy import select
from werkzeug.exceptions import NotFound

from memorybook.errors import ServiceUnavailableError, ValidationError
from memorybook.extensions import db, limiter
from memorybook.integrations.payment_gateways import available_payment_methods
from memorybook.models import Notification, Payment, PaymentAttempt, Refund
from memorybook.permissions import active_user_required, get_authenticated_user, roles_required
from memorybook.services.payments import (
    process_jazzcash_callback,
    process_paypal_event,
    process_stripe_event,
    create_refund_request,
    request_refund,
    submit_manual_payment_reference,
    retry_payment,
    serialize_transaction,
)

payments_blueprint = Blueprint("payments", __name__)


@payments_blueprint.get("/methods")
def payment_methods():
    currency = request.args.get("currency", "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValidationError("A three-letter currency code is required.", {"currency": "invalid"})
    methods = available_payment_methods(currency)
    return jsonify({
        "currency": currency,
        "items": methods,
        "primaryGateway": current_app.config.get("PAYMENT_PRIMARY_GATEWAY"),
    })


@payments_blueprint.post("/webhooks/stripe")
@limiter.limit("120 per minute")
def stripe_webhook():
    process_stripe_event(request.get_data(cache=False), request.headers.get("Stripe-Signature"))
    return jsonify({"received": True})


@payments_blueprint.post("/webhooks/paypal")
@limiter.limit("120 per minute")
def paypal_webhook():
    process_paypal_event(request.get_data(cache=False), {
        "PayPal-Transmission-Id": request.headers.get("PayPal-Transmission-Id", ""),
        "PayPal-Transmission-Time": request.headers.get("PayPal-Transmission-Time", ""),
        "PayPal-Transmission-Sig": request.headers.get("PayPal-Transmission-Sig", ""),
        "PayPal-Cert-Url": request.headers.get("PayPal-Cert-Url", ""),
        "PayPal-Auth-Algo": request.headers.get("PayPal-Auth-Algo", ""),
    })
    return jsonify({"received": True})


@payments_blueprint.post("/webhooks/jazzcash")
@limiter.limit("120 per minute")
def jazzcash_callback():
    if not any(method["provider"] == "jazzcash" for method in available_payment_methods("PKR")):
        raise ServiceUnavailableError("JazzCash callback processing is disabled until its merchant contract is verified.")
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = request.form.to_dict(flat=True)
    if not isinstance(payload, dict):
        raise ValidationError("JazzCash callback payload is invalid.")
    txn_ref = payload.get("pp_TxnRefNo")
    result = process_jazzcash_callback(payload)
    payment = db.session.scalar(
        select(Payment)
        .where(Payment.provider == "jazzcash", Payment.provider_payment_id == txn_ref)
    )
    if payment is None and isinstance(txn_ref, str):
        payment = db.session.scalar(
            select(Payment)
            .join(PaymentAttempt, PaymentAttempt.payment_id == Payment.id)
            .where(Payment.provider == "jazzcash", PaymentAttempt.provider_reference == txn_ref)
        )
    if payment is None:
        raise NotFound("JazzCash payment could not be matched to an order.")
    order_id = payment.pdf_order_id or payment.print_order_id
    route = "pdf" if payment.pdf_order_id else "print"
    target = f"{current_app.config['PUBLIC_APP_URL'].rstrip('/')}/{route}/orders/{order_id}/processing"
    if payment.status == "failed":
        target += "?payment=failed"
    elif payment.status == "successful":
        target += "?payment=successful"
    response = redirect(target, code=303)
    response.headers["Cache-Control"] = "no-store"
    return response


@payments_blueprint.post("/<payment_id>/retry")
@active_user_required
@limiter.limit("5 per minute")
def retry(payment_id: str):
    payment = db.session.scalar(
        select(Payment).where(Payment.id == payment_id, Payment.user_id == get_authenticated_user().id)
    )
    if payment is None:
        raise NotFound("Payment was not found.")
    key = _idempotency_key()
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise ValidationError("A JSON object is required.")
    return jsonify(retry_payment(payment, key, body.get("provider")))


@payments_blueprint.get("/history")
@active_user_required
def history():
    items = db.session.scalars(
        select(Payment)
        .where(Payment.user_id == get_authenticated_user().id)
        .order_by(Payment.created_at.desc())
    ).all()
    return jsonify({"items": [serialize_transaction(item) for item in items]})


@payments_blueprint.get("/<payment_id>")
@active_user_required
def get_payment(payment_id: str):
    payment = db.session.scalar(
        select(Payment).where(Payment.id == payment_id, Payment.user_id == get_authenticated_user().id)
    )
    if payment is None:
        raise NotFound("Payment was not found.")
    return jsonify({"payment": serialize_transaction(payment)})


@payments_blueprint.post("/<payment_id>/manual-confirmation")
@active_user_required
@limiter.limit("5 per hour")
def manual_confirmation(payment_id: str):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("A JSON object is required.")
    reference = body.get("reference")
    if not isinstance(reference, str):
        raise ValidationError("Enter the transfer reference from your receipt.", {"reference": "required"})
    payment = db.session.scalar(
        select(Payment).where(
            Payment.id == payment_id,
            Payment.user_id == get_authenticated_user().id,
        ).with_for_update()
    )
    if payment is None:
        raise NotFound("Payment was not found.")
    return jsonify({"payment": submit_manual_payment_reference(
        payment,
        get_authenticated_user().id,
        reference,
    )})


@payments_blueprint.post("/<payment_id>/refund-requests")
@active_user_required
@limiter.limit("5 per hour")
def refund_request(payment_id: str):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("A JSON object is required.")
    try:
        amount = Decimal(str(body.get("amount")))
    except (InvalidOperation, ValueError, TypeError) as failure:
        raise ValidationError("Refund amount must be a valid currency amount.", {"amount": "invalid"}) from failure
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValidationError("Refund amount must have at most two decimal places.", {"amount": "invalid"})
    reason = body.get("reason")
    if reason is not None and (not isinstance(reason, str) or len(reason) > 500):
        raise ValidationError("Refund reason is invalid.", {"reason": "invalid"})
    result = create_refund_request(
        payment_id,
        get_authenticated_user().id,
        amount,
        reason,
        _idempotency_key(),
    )
    return jsonify({"refund": result}), 202


@payments_blueprint.get("/notifications")
@active_user_required
def list_notifications():
    user_id = get_authenticated_user().id
    items = db.session.scalars(
        select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc()).limit(100)
    ).all()
    return jsonify({"items": [{
        "id": item.id,
        "category": item.category,
        "title": item.title,
        "message": item.message,
        "targetUrl": item.target_url,
        "data": item.data,
        "readAt": item.read_at.isoformat() if item.read_at else None,
        "createdAt": item.created_at.isoformat(),
    } for item in items]})


@payments_blueprint.post("/notifications/<notification_id>/read")
@active_user_required
def mark_notification_read(notification_id: str):
    notification = db.session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == get_authenticated_user().id,
        )
    )
    if notification is None:
        raise NotFound("Notification was not found.")
    if notification.read_at is None:
        from datetime import UTC, datetime

        notification.read_at = datetime.now(UTC)
        db.session.commit()
    return jsonify({"id": notification.id, "readAt": notification.read_at.isoformat()})


@payments_blueprint.post("/<payment_id>/refunds")
@roles_required("admin")
@limiter.limit("10 per hour")
def create_refund(payment_id: str):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("A JSON object is required.")
    try:
        amount = Decimal(str(body.get("amount")))
    except (InvalidOperation, ValueError, TypeError) as failure:
        raise ValidationError("Refund amount must be a valid currency amount.", {"amount": "invalid"}) from failure
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValidationError("Refund amount must have at most two decimal places.", {"amount": "invalid"})
    reason = body.get("reason")
    if reason is not None and (not isinstance(reason, str) or len(reason) > 500):
        raise ValidationError("Refund reason is invalid.", {"reason": "invalid"})
    refund = request_refund(payment_id, amount, reason, _idempotency_key())
    return jsonify({"refund": refund}), 202


def _idempotency_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 128:
        raise ValidationError("A valid Idempotency-Key header is required.", {"idempotencyKey": "required"})
    return key
