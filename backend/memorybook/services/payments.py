from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import NotFound

from memorybook.errors import ConflictError, ServiceUnavailableError, ValidationError
from memorybook.extensions import db
from memorybook.integrations.payment_gateways import (
    JazzCashGateway,
    ManualPaymentGateway,
    PayPalGateway,
    StripeGateway,
    available_payment_methods,
    pkr_amount_to_usd,
    pkr_to_usd_rate,
    provider_for,
)
from memorybook.models import (
    DownloadEntitlement,
    Invoice,
    OrderStatusHistory,
    Payment,
    PaymentAttempt,
    PaymentWebhookEvent,
    PdfJob,
    PdfOrder,
    PrintOrder,
    Refund,
)
from memorybook.services.notifications import queue_order_event


def create_payment(
    order: PdfOrder | PrintOrder,
    kind: str,
    provider_name: str | None,
    idempotency_key: str,
    payment_method: str | None = None,
) -> dict:
    payment = db.session.scalar(
        select(Payment).where(
            (Payment.pdf_order_id == order.id) if kind == "pdf" else (Payment.print_order_id == order.id)
        )
    )
    if payment is not None and payment.status == "successful":
        return serialize_order(order, kind)
    if isinstance(order, PrintOrder):
        if order.status not in {"pending_payment", "order_placed"}:
            raise ConflictError("This print order is no longer awaiting payment.")
        if _print_order_payment_expired(order):
            raise ConflictError("This print order has expired and can no longer be paid.")
    provider = provider_for(order.currency, provider_name, payment_method)
    if payment is not None:
        if payment.status not in {"failed", "pending"}:
            raise ConflictError("This order already has a completed payment.")
        return serialize_order(order, kind)

    pkr_amount = order.total_amount if order.currency.upper() == "PKR" else None
    rate = pkr_to_usd_rate() if provider.name == "paypal" and order.currency.upper() == "PKR" else None
    usd_amount = (
        pkr_amount_to_usd(order.total_amount, rate)
        if rate is not None
        else order.total_amount if provider.name == "paypal" and order.currency.upper() == "USD"
        else None
    )
    payment = Payment(
        user_id=order.user_id,
        pdf_order_id=order.id if kind == "pdf" else None,
        print_order_id=order.id if kind == "print" else None,
        purpose="pdf_purchase" if kind == "pdf" else "print_order",
        provider=provider.name,
        payment_method=(payment_method.strip().lower() if payment_method else None) or next(
            option["method"]
            for option in available_payment_methods(order.currency)
            if option["provider"] == provider.name
        ),
        status="pending",
        amount=order.total_amount,
        currency=order.currency,
        pkr_amount=pkr_amount,
        usd_amount=usd_amount,
        exchange_rate=rate,
        idempotency_key=idempotency_key,
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
    db.session.commit()
    return _start_provider_checkout(payment, attempt, order, kind, provider)


def retry_payment(payment: Payment, idempotency_key: str, provider_name: str | None = None) -> dict:
    if provider_name is not None and not isinstance(provider_name, str):
        raise ValidationError("Payment provider must be a string.", {"provider": "invalid"})
    if payment.print_order_id:
        order = db.session.get(PrintOrder, payment.print_order_id)
        if order is None or order.status not in {"pending_payment", "order_placed"}:
            raise ConflictError("This print order is no longer awaiting payment.")
        if _print_order_payment_expired(order):
            raise ConflictError("This print order has expired and can no longer be paid.")
    previous = db.session.scalar(
        select(PaymentAttempt).where(
            PaymentAttempt.payment_id == payment.id,
            PaymentAttempt.idempotency_key == idempotency_key,
        )
    )
    if previous:
        return serialize_order(_payment_order(payment), "pdf" if payment.pdf_order_id else "print")
    if payment.status == "successful":
        raise ConflictError("A confirmed payment cannot be retried.")
    if payment.status != "failed":
        raise ConflictError("This payment cannot be retried.")
    if provider_name and provider_name.strip().lower() != payment.provider:
        raise ValidationError("Retry must use the payment provider selected for this order.", {"provider": "mismatch"})
    provider = provider_for(payment.currency, payment.provider)
    payment.status = "pending"
    attempts = db.session.scalar(
        select(func.max(PaymentAttempt.attempt_number)).where(PaymentAttempt.payment_id == payment.id)
    ) or 0
    attempt = PaymentAttempt(
        payment_id=payment.id,
        attempt_number=attempts + 1,
        status="pending",
        amount=payment.amount,
        idempotency_key=idempotency_key,
    )
    db.session.add(attempt)
    db.session.commit()
    order = _payment_order(payment)
    kind = "pdf" if payment.pdf_order_id else "print"
    return _start_provider_checkout(payment, attempt, order, kind, provider)


def _start_provider_checkout(payment, attempt, order, kind, provider) -> dict:
    if provider.name == "paypal":
        return serialize_order(order, kind)
    title = _order_title(order, kind)
    try:
        checkout = provider.create_checkout(
            payment,
            title,
            f"{payment.id}:{attempt.idempotency_key or attempt.id}",
        )
    except Exception as failure:
        db.session.rollback()
        current = db.session.get(Payment, payment.id)
        current_attempt = db.session.get(PaymentAttempt, attempt.id)
        current.status = "failed"
        current_attempt.status = "failed"
        current_attempt.failure_code = "checkout_initialization_failed"
        current_attempt.failure_message = (
            str(failure)[:500] if isinstance(failure, (ServiceUnavailableError, ValidationError))
            else "The payment provider could not start checkout."
        )
        db.session.commit()
        raise
    payment.provider_payment_id = checkout.reference
    if provider.name != "manual":
        attempt.provider_reference = checkout.reference
    attempt.checkout_url = checkout.url
    db.session.commit()
    return serialize_order(
        order,
        kind,
        checkout_url=checkout.url,
        payment_instructions=checkout.instructions,
    )


def create_paypal_order(payment: Payment) -> dict:
    if payment.provider != "paypal" or payment.status != "pending":
        raise ConflictError("This payment is not awaiting PayPal checkout.")
    if payment.usd_amount is None or payment.exchange_rate is None:
        raise ValidationError("This payment is missing its PayPal currency snapshot.")
    attempt = db.session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.payment_id == payment.id, PaymentAttempt.status == "pending")
        .order_by(PaymentAttempt.attempt_number.desc())
        .with_for_update()
    )
    if attempt is None:
        raise ConflictError("This payment has no active checkout attempt.")
    if attempt.provider_reference:
        return {
            "paypalOrderId": attempt.provider_reference,
            "chargedAmountUsd": str(payment.usd_amount),
            "rate": str(payment.exchange_rate),
        }

    order = _payment_order(payment)
    if isinstance(order, PrintOrder) and (
        order.status not in {"pending_payment", "order_placed"} or _print_order_payment_expired(order)
    ):
        raise ConflictError("This print order is no longer awaiting payment.")
    paypal_order_id = PayPalGateway().create_smart_order(
        payment,
        order.order_number,
        attempt.idempotency_key or attempt.id,
    )
    payment.provider_payment_id = paypal_order_id
    attempt.provider_reference = paypal_order_id
    db.session.commit()
    return {
        "paypalOrderId": paypal_order_id,
        "chargedAmountUsd": str(payment.usd_amount),
        "rate": str(payment.exchange_rate),
    }


def capture_paypal_order(payment: Payment, paypal_order_id: str) -> dict:
    if payment.provider != "paypal":
        raise ValidationError("This payment does not use PayPal.")
    order = _payment_order(payment)
    kind = "pdf" if payment.pdf_order_id else "print"
    if payment.status == "successful":
        if payment.provider_payment_id != paypal_order_id or not payment.provider_capture_id:
            raise ConflictError("This payment was already completed with a different PayPal order.")
        return {
            "status": "successful",
            "payment": serialize_transaction(payment),
            "order": serialize_order(order, kind),
        }
    if payment.status != "pending":
        raise ConflictError("This payment is no longer awaiting PayPal capture.")
    if payment.usd_amount is None or payment.exchange_rate is None:
        raise ValidationError("This payment is missing its PayPal currency snapshot.")
    attempt = db.session.scalar(
        select(PaymentAttempt)
        .where(
            PaymentAttempt.payment_id == payment.id,
            PaymentAttempt.status == "pending",
            PaymentAttempt.provider_reference == paypal_order_id,
        )
        .order_by(PaymentAttempt.attempt_number.desc())
        .with_for_update()
    )
    if attempt is None or payment.provider_payment_id != paypal_order_id:
        raise ValidationError("The PayPal order does not match the active payment attempt.")

    captured = PayPalGateway().capture_order(
        paypal_order_id,
        f"{payment.id}:attempt:{attempt.attempt_number}",
    )
    if captured.get("id") != paypal_order_id:
        raise ValidationError("PayPal capture response does not match the requested order.")
    purchase_units = captured.get("purchase_units")
    purchase_unit = (
        purchase_units[0]
        if isinstance(purchase_units, list) and purchase_units and isinstance(purchase_units[0], dict)
        else None
    )
    capture = (
        purchase_unit.get("payments", {}).get("captures", [None])[0]
        if purchase_unit and isinstance(purchase_unit.get("payments"), dict)
        else None
    )
    if captured.get("status") != "COMPLETED" or not isinstance(capture, dict) or capture.get("status") != "COMPLETED":
        _process_verified_event(
            provider="paypal",
            event_id=f"sdk-capture-failed:{paypal_order_id}",
            event_type="PAYMENT.CAPTURE.DENIED",
            safe_payload={"orderId": paypal_order_id, "paymentId": payment.id},
            payment_id=payment.id,
            provider_reference=paypal_order_id,
            success=False,
            failure=True,
            refund_event=False,
            amount=None,
            currency="USD",
            provider_payload={},
        )
        return {
            "status": "failed",
            "payment": serialize_transaction(payment),
            "order": serialize_order(order, kind),
        }

    if purchase_unit.get("reference_id") != order.order_number:
        raise ValidationError("PayPal order reference does not match this payment.")
    amount, currency = _paypal_capture_amount(capture)
    capture_id = capture.get("id")
    if amount != payment.usd_amount or currency != "USD":
        raise ValidationError("PayPal capture amount or currency does not match the payment.")
    if not isinstance(capture_id, str) or not capture_id:
        raise ValidationError("PayPal capture response is missing its capture reference.")

    _process_verified_event(
        provider="paypal",
        event_id=f"sdk-capture:{capture_id}",
        event_type="PAYMENT.CAPTURE.COMPLETED",
        safe_payload={"captureId": capture_id, "orderId": paypal_order_id, "paymentId": payment.id},
        payment_id=payment.id,
        provider_reference=paypal_order_id,
        success=True,
        failure=False,
        refund_event=False,
        amount=amount,
        currency=currency,
        provider_payload={},
        capture_reference=capture_id,
    )
    return {
        "status": "successful",
        "payment": serialize_transaction(payment),
        "order": serialize_order(order, kind),
    }


def submit_manual_payment_reference(payment: Payment, user_id: str, reference: str) -> dict:
    if not _app().config.get("MANUAL_PAYMENTS_ENABLED", False):
        raise ServiceUnavailableError("Manual payments are disabled for this deployment.")
    if payment.user_id != user_id:
        raise NotFound("Payment was not found.")
    if payment.provider != "manual" or payment.status != "pending":
        raise ConflictError("This payment is not awaiting manual confirmation.")
    if payment.print_order_id:
        order = db.session.get(PrintOrder, payment.print_order_id)
        if order is None or order.status not in {"pending_payment", "order_placed"}:
            raise ConflictError("This print order is no longer awaiting payment.")
        if _print_order_payment_expired(order):
            raise ConflictError("This print order has expired and can no longer be paid.")
    normalized = reference.strip()
    if not normalized or len(normalized) > 160:
        raise ValidationError("Enter a valid transfer reference.", {"reference": "invalid"})
    attempt = db.session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.payment_id == payment.id)
        .order_by(PaymentAttempt.attempt_number.desc())
        .with_for_update()
    )
    if attempt is None or attempt.status != "pending":
        raise ConflictError("This payment attempt is not accepting a transfer reference.")
    attempt.provider_reference = normalized
    attempt.status = "submitted"
    db.session.commit()
    return serialize_transaction(payment)


def review_manual_payment(payment_id: str, *, approved: bool, actor_id: str) -> dict:
    if not _app().config.get("MANUAL_PAYMENTS_ENABLED", False):
        raise ServiceUnavailableError("Manual payments are disabled for this deployment.")
    payment = db.session.scalar(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    if payment is None:
        raise NotFound("Payment was not found.")
    if payment.provider != "manual":
        raise ConflictError("Only manual payments can be reviewed by an administrator.")
    if payment.status != "pending":
        raise ConflictError("This payment has already been reviewed.")
    attempt = db.session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.payment_id == payment.id)
        .order_by(PaymentAttempt.attempt_number.desc())
        .with_for_update()
    )
    if attempt is None or attempt.status != "submitted" or not attempt.provider_reference:
        raise ConflictError("The customer must submit a transfer reference before review.")
    if approved:
        _apply_payment_result(
            payment,
            success=True,
            provider_reference=attempt.provider_reference,
            changed_by_user_id=actor_id,
        )
    else:
        _apply_payment_result(
            payment,
            success=False,
            provider_reference=attempt.provider_reference,
            changed_by_user_id=actor_id,
        )
        attempt.failure_code = "manual_payment_rejected"
        attempt.failure_message = "The administrator could not verify the submitted transfer."
    db.session.commit()
    if approved:
        if payment.pdf_order_id:
            _queue_pdf_generation(payment)
        elif payment.print_order_id:
            _handle_confirmed_print_payment(payment)
    return serialize_transaction(payment)


def process_stripe_event(raw_body: bytes, signature: str | None) -> dict:
    event = StripeGateway().handle_webhook(raw_body, {"Stripe-Signature": signature or ""})
    event_data = event.get("data")
    obj = event_data.get("object") if isinstance(event_data, dict) else None
    if not isinstance(obj, dict):
        raise ValidationError("Stripe webhook event does not contain a payment object.")
    kind = event["type"]
    reference = obj.get("payment_intent") or obj.get("id")
    metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
    payment_id = metadata.get("payment_id") or obj.get("client_reference_id")
    success = kind == "checkout.session.async_payment_succeeded" or (
        kind == "checkout.session.completed" and obj.get("payment_status") == "paid"
    )
    failure = kind in {"checkout.session.async_payment_failed", "payment_intent.payment_failed"}
    refund_event = kind in {"refund.created", "refund.updated"}
    if not (success or failure or refund_event):
        return {"received": True, "ignored": True}
    currency = str(obj.get("currency") or "").upper()
    amount = _stripe_amount(obj.get("amount_total") or obj.get("amount"), currency)
    return _process_verified_event(
        provider="stripe",
        event_id=event["id"],
        event_type=kind,
        safe_payload={"id": event["id"], "type": kind, "paymentId": payment_id, "reference": reference},
        payment_id=payment_id if isinstance(payment_id, str) else None,
        provider_reference=reference if isinstance(reference, str) else None,
        success=success,
        failure=failure,
        refund_event=refund_event,
        amount=amount,
        currency=currency,
        provider_payload=obj,
    )


def process_paypal_event(raw_body: bytes, headers: dict[str, str]) -> dict:
    gateway = PayPalGateway()
    event = gateway.handle_webhook(raw_body, headers)
    event_type = event["event_type"]
    if _webhook_event_processed("paypal", event["id"]):
        return {"received": True, "duplicate": True}
    resource = event.get("resource")
    if not isinstance(resource, dict):
        raise ValidationError("PayPal webhook event does not contain a payment resource.")

    order_id = resource.get("id")
    if event_type.startswith("PAYMENT.CAPTURE."):
        related = (resource.get("supplementary_data") or {}).get("related_ids", {})
        order_id = related.get("order_id") if isinstance(related, dict) else None
    if not isinstance(order_id, str):
        raise ValidationError("PayPal webhook event does not identify a checkout order.")

    payment = _find_payment("paypal", None, order_id)
    if payment is None:
        raise ValidationError("PayPal webhook event does not match a pending payment.")
    if event_type == "CHECKOUT.ORDER.APPROVED":
        attempt = db.session.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment.id, PaymentAttempt.provider_reference == order_id)
            .order_by(PaymentAttempt.attempt_number.desc())
            .with_for_update()
        )
        if payment.status == "successful" or attempt is None or attempt.status != "pending":
            return {"received": True, "ignored": True}
        custom_id = _paypal_payment_id(resource)
        if custom_id and custom_id != payment.id:
            raise ValidationError("PayPal checkout order reference does not match the payment.")
        purchase_units = resource.get("purchase_units")
        purchase_unit = (
            purchase_units[0]
            if isinstance(purchase_units, list) and purchase_units and isinstance(purchase_units[0], dict)
            else None
        )
        order = _payment_order(payment)
        if not purchase_unit or purchase_unit.get("reference_id") != order.order_number:
            raise ValidationError("PayPal checkout order reference does not match the order number.")
        captured = gateway.capture_order(
            order_id,
            f"{payment.id}:attempt:{attempt.attempt_number}",
        )
        purchase_units = captured.get("purchase_units")
        capture = (
            purchase_units[0].get("payments", {}).get("captures", [None])[0]
            if isinstance(purchase_units, list) and purchase_units and isinstance(purchase_units[0], dict)
            else None
        )
        if not isinstance(capture, dict):
            raise ValidationError("PayPal capture response is missing capture details.")
        capture_amount, capture_currency = _paypal_capture_amount(capture)
        if captured.get("status") != "COMPLETED" or not capture_amount or not capture_currency:
            raise ValidationError("PayPal did not complete the payment capture.")
        capture_id = capture.get("id")
        if not isinstance(capture_id, str):
            raise ValidationError("PayPal capture response is missing its reference.")
        return _process_verified_event(
            provider="paypal",
            event_id=event["id"],
            event_type=event_type,
            safe_payload={"id": event["id"], "type": event_type, "orderId": order_id},
            payment_id=payment.id,
            provider_reference=order_id,
            success=True,
            failure=False,
            refund_event=False,
            amount=capture_amount,
            currency=capture_currency,
            provider_payload={},
            capture_reference=capture_id,
        )

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        amount, currency = _paypal_capture_amount(resource)
        capture_id = resource.get("id")
        if not isinstance(capture_id, str):
            raise ValidationError("PayPal capture webhook is missing its reference.")
        return _process_verified_event(
            provider="paypal",
            event_id=event["id"],
            event_type=event_type,
            safe_payload={"id": event["id"], "type": event_type, "orderId": order_id},
            payment_id=payment.id,
            provider_reference=order_id,
            success=True,
            failure=False,
            refund_event=False,
            amount=amount,
            currency=currency,
            provider_payload={},
            capture_reference=capture_id,
        )

    failed_events = {
        "CHECKOUT.ORDER.VOIDED",
        "CHECKOUT.ORDER.EXPIRED",
        "PAYMENT.CAPTURE.DENIED",
    }
    if event_type in failed_events:
        return _process_verified_event(
            provider="paypal",
            event_id=event["id"],
            event_type=event_type,
            safe_payload={"id": event["id"], "type": event_type, "orderId": order_id},
            payment_id=payment.id,
            provider_reference=order_id,
            success=False,
            failure=True,
            refund_event=False,
            amount=None,
            currency="USD",
            provider_payload={},
        )
    if event_type in {"PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"}:
        return _process_verified_event(
            provider="paypal",
            event_id=event["id"],
            event_type=event_type,
            safe_payload={"id": event["id"], "type": event_type, "orderId": order_id},
            payment_id=payment.id,
            provider_reference=order_id,
            success=False,
            failure=False,
            refund_event=True,
            amount=None,
            currency="USD",
            provider_payload=resource,
        )
    return {"received": True, "ignored": True}


def _webhook_event_processed(provider: str, event_id: str) -> bool:
    return db.session.scalar(
        select(PaymentWebhookEvent.id).where(
            PaymentWebhookEvent.provider == provider,
            PaymentWebhookEvent.provider_event_id == event_id,
            PaymentWebhookEvent.processed_at.is_not(None),
        )
    ) is not None


def process_jazzcash_callback(payload: dict[str, str]) -> dict:
    gateway = JazzCashGateway()
    verified = gateway.verify_event(payload)
    txn_ref = verified["pp_TxnRefNo"]
    response_code = verified["pp_ResponseCode"]
    event_id = hashlib.sha256(
        json.dumps({key: value for key, value in sorted(verified.items()) if key != "pp_SecureHash"}).encode()
    ).hexdigest()
    amount = _minor_to_decimal(verified.get("pp_Amount"))
    return _process_verified_event(
        provider="jazzcash",
        event_id=event_id,
        event_type="payment.callback",
        safe_payload={"txnRef": txn_ref, "responseCode": response_code},
        payment_id=None,
        provider_reference=txn_ref,
        success=response_code == "000",
        failure=response_code != "000",
        refund_event=False,
        amount=amount,
        currency=str(verified.get("pp_TxnCurrency") or "").upper(),
        provider_payload=verified,
    )


def _process_verified_event(
    *,
    provider: str,
    event_id: str,
    event_type: str,
    safe_payload: dict,
    payment_id: str | None,
    provider_reference: str | None,
    success: bool,
    failure: bool,
    refund_event: bool,
    amount: Decimal | None,
    currency: str,
    provider_payload: dict,
    capture_reference: str | None = None,
) -> dict:
    if len(event_id) > 200:
        raise ValidationError("Payment event identifier is invalid.")
    event = db.session.scalar(
        select(PaymentWebhookEvent)
        .where(PaymentWebhookEvent.provider == provider, PaymentWebhookEvent.provider_event_id == event_id)
        .with_for_update()
    )
    if event is not None and event.processed_at is not None:
        return {"received": True, "duplicate": True}
    if event is None:
        event = PaymentWebhookEvent(
            provider=provider,
            provider_event_id=event_id,
            event_type=event_type,
            payload=safe_payload,
            signature_verified=True,
        )
        db.session.add(event)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            return {"received": True, "duplicate": True}
    payment = _find_payment(provider, payment_id, provider_reference)
    was_successful = payment.status == "successful" if payment is not None else False
    if refund_event:
        _apply_refund_event(payment, provider_payload)
    elif payment is None:
        raise ValidationError("Payment provider event does not match a pending payment.")
    elif success or failure:
        expected_amount = payment.usd_amount if provider == "paypal" else payment.amount
        expected_currency = "USD" if provider == "paypal" else payment.currency.upper()
        if success and (amount is None or amount != expected_amount or currency != expected_currency):
            raise ValidationError("Payment provider amount or currency does not match the order.")
        _apply_payment_result(
            payment,
            success=success,
            provider_reference=provider_reference,
            capture_reference=capture_reference,
        )
    event.processed_at = datetime.now(UTC)
    db.session.commit()
    if success and payment is not None and not was_successful:
        if payment.pdf_order_id:
            _queue_pdf_generation(payment)
        elif payment.print_order_id:
            _handle_confirmed_print_payment(payment)
    return {"received": True, "processed": True}


def _apply_payment_result(
    payment: Payment,
    *,
    success: bool,
    provider_reference: str | None,
    changed_by_user_id: str | None = None,
    capture_reference: str | None = None,
) -> None:
    if payment.status in {"refunded", "partially_refunded"}:
        return
    if payment.status == "successful":
        return
    if payment.status == "failed" and not success:
        return
    order = _payment_order(payment)
    late_print_payment = bool(
        success
        and payment.print_order_id
        and (
            order.status not in {"pending_payment", "order_placed"}
            or _print_order_payment_expired(order)
        )
    )
    attempt_query = select(PaymentAttempt).where(PaymentAttempt.payment_id == payment.id)
    if provider_reference:
        attempt_query = attempt_query.where(PaymentAttempt.provider_reference == provider_reference)
    attempt = db.session.scalar(attempt_query.order_by(PaymentAttempt.attempt_number.desc()).with_for_update())
    if attempt is None:
        attempt = db.session.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment.id)
            .order_by(PaymentAttempt.attempt_number.desc())
            .with_for_update()
        )
    if success:
        payment.status = "successful"
        if provider_reference:
            payment.provider_payment_id = provider_reference
        if capture_reference:
            payment.provider_capture_id = capture_reference
        if attempt:
            attempt.status = "successful"
            attempt.provider_reference = provider_reference or attempt.provider_reference
        db.session.execute(
            update(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment.id, PaymentAttempt.status == "pending")
            .values(status="cancelled")
        )
        if late_print_payment:
            if order.status not in {"cancelled", "refunded"}:
                order.status = "cancelled"
                db.session.add(OrderStatusHistory(
                    print_order_id=order.id,
                    status="cancelled",
                    note="A verified payment arrived after this print order had expired.",
                    changed_by_user_id=changed_by_user_id,
                ))
            db.session.add(OrderStatusHistory(
                print_order_id=order.id,
                status="payment_after_cancellation",
                note="A verified payment was captured after the order could no longer be fulfilled; a refund was requested.",
                changed_by_user_id=changed_by_user_id,
            ))
            queue_order_event(
                order.user_id,
                f"late_print_payment:{payment.id}",
                "payment",
                "Refund requested for late payment",
                f"Payment for cancelled print order {order.order_number} arrived after its payment window. A refund is being processed.",
                "/dashboard/orders",
            )
            return
        _issue_invoice(payment, order)
        order.paid_at = datetime.now(UTC)
        old_status = order.status
        order.status = "paid" if payment.pdf_order_id else "payment_confirmed"
        verification_note = (
            "Manual transfer reviewed and approved by an administrator."
            if payment.provider == "manual"
            else "Payment verified by payment provider."
        )
        if payment.print_order_id:
            if old_status != order.status:
                db.session.add(OrderStatusHistory(
                    print_order_id=order.id,
                    status="payment_confirmed",
                    note=verification_note,
                    changed_by_user_id=changed_by_user_id,
                ))
            _create_print_pdf_entitlement(order)
        elif payment.pdf_order_id and old_status != order.status:
            db.session.add(OrderStatusHistory(
                pdf_order_id=order.id,
                status="paid",
                note=verification_note,
                changed_by_user_id=changed_by_user_id,
            ))
        queue_order_event(
            order.user_id,
            f"payment_confirmed:{payment.id}",
            "payment",
            "Payment received",
            f"We received your payment for order {order.order_number}.",
            "/dashboard/orders",
        )
        if payment.pdf_order_id:
            queue_order_event(
                order.user_id,
                f"pdf_purchased:{order.id}",
                "pdf",
                "PDF purchased",
                f"Your PDF order {order.order_number} is ready for generation.",
                f"/pdf/orders/{order.id}",
            )
    else:
        if attempt:
            attempt.status = "failed"
            attempt.failure_code = "provider_declined"
            attempt.failure_message = str(
                provider_reference or "Payment was declined by the provider."
            )[:500]
        another_pending_attempt = db.session.scalar(
            select(PaymentAttempt.id).where(
                PaymentAttempt.payment_id == payment.id,
                PaymentAttempt.status == "pending",
            ).limit(1)
        )
        if another_pending_attempt:
            return
        payment.status = "failed"
        db.session.add(OrderStatusHistory(
            pdf_order_id=order.id if payment.pdf_order_id else None,
            print_order_id=order.id if payment.print_order_id else None,
            status="payment_failed",
            note=(
                "Manual payment was not verified by an administrator."
                if payment.provider == "manual"
                else "Payment was declined by the payment provider."
            ),
            changed_by_user_id=changed_by_user_id,
        ))
        queue_order_event(
            order.user_id,
            f"payment_failed:{payment.id}:{attempt.attempt_number if attempt else 1}",
            "payment",
            "Payment failed",
            f"Payment for order {order.order_number} was not completed. You can retry checkout.",
            "/dashboard/orders",
        )


def _issue_invoice(payment: Payment, order: PdfOrder | PrintOrder) -> Invoice:
    invoice = db.session.scalar(select(Invoice).where(Invoice.payment_id == payment.id))
    if invoice is not None:
        return invoice
    invoice = Invoice(
        invoice_number=f"INV-{order.order_number}"[:50],
        payment_id=payment.id,
        pdf_order_id=payment.pdf_order_id,
        print_order_id=payment.print_order_id,
        amount=payment.amount,
        currency=payment.currency,
    )
    db.session.add(invoice)
    return invoice


def _queue_pdf_generation(payment: Payment) -> None:
    from memorybook.services.pdf_generation import queue_pdf_generation

    order = db.session.get(PdfOrder, payment.pdf_order_id)
    if order is None or order.paid_at is None:
        return
    job, dispatch = queue_pdf_generation(order, "digital", refresh_current_document=True)
    if dispatch:
        current_app = _app()
        try:
            from memorybook.tasks.dispatch import dispatch_pdf_generation

            dispatch_pdf_generation(job.id)
        except Exception:
            current_app.logger.exception("Paid PDF generation could not be dispatched.")
            db.session.rollback()
            job = db.session.get(type(job), job.id)
            if job:
                job.status = "failed"
                job.error_code = "queue_unavailable"
                job.error_message = "The PDF worker could not be reached. Please retry."
                db.session.commit()


def _create_print_pdf_entitlement(print_order: PrintOrder) -> PdfOrder:
    order = db.session.scalar(
        select(PdfOrder).where(
            PdfOrder.user_id == print_order.user_id,
            PdfOrder.project_id == print_order.project_id,
            PdfOrder.idempotency_key == f"print-free:{print_order.id}",
        )
    )
    if order is not None:
        return order
    snapshot = print_order.price_snapshot or {}
    paid_at = print_order.paid_at or datetime.now(UTC)
    order = PdfOrder(
        order_number=f"FREE-{print_order.order_number}",
        user_id=print_order.user_id,
        project_id=print_order.project_id,
        project_revision_id=print_order.project_revision_id,
        status="paid",
        currency=print_order.currency,
        service_price=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("0.00"),
        price_snapshot={
            "description": "Included with print order",
            "pdfProfiles": ["digital", "print"],
            "printPdfIncluded": True,
            "printSpecification": {
                "bleedInches": _app().config.get("PDF_PRINT_BLEED_INCHES", 0.125),
                "safeMarginInches": _app().config.get("PDF_PRINT_SAFE_MARGIN_INCHES", 0.25),
                "tier": snapshot.get("tierId"),
                "size": snapshot.get("sizeName"),
                "cover": snapshot.get("coverName"),
                "paper": snapshot.get("paperName"),
            },
            "printOrderId": print_order.id,
            "projectRevisionId": print_order.project_revision_id,
            "taxApplicable": False,
        },
        page_count=int(snapshot.get("pageCount", 0)),
        paid_at=paid_at,
        idempotency_key=f"print-free:{print_order.id}",
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(Payment(
        user_id=print_order.user_id,
        pdf_order_id=order.id,
        purpose="print_order_pdf",
        provider="complimentary",
        status="successful",
        amount=Decimal("0.00"),
        currency=print_order.currency,
        idempotency_key=f"print-free:{print_order.id}",
    ))
    db.session.add(OrderStatusHistory(
        pdf_order_id=order.id,
        status="paid",
        note=f"Complimentary PDF included with print order {print_order.order_number}.",
    ))
    return order


def _queue_print_order_pdfs(payment: Payment) -> None:
    from memorybook.services.pdf_generation import queue_pdf_generation
    from memorybook.tasks.dispatch import dispatch_pdf_generation

    print_order = db.session.get(PrintOrder, payment.print_order_id)
    if print_order is None or print_order.paid_at is None:
        return
    pdf_order = db.session.scalar(
        select(PdfOrder).where(PdfOrder.idempotency_key == f"print-free:{print_order.id}")
    )
    if pdf_order is None:
        raise RuntimeError("The complimentary PDF entitlement was not created for the paid print order.")
    for profile in ("digital", "print"):
        job, dispatch = queue_pdf_generation(pdf_order, profile)
        if dispatch:
            try:
                dispatch_pdf_generation(job.id)
            except Exception:
                _app().logger.exception(
                    "Paid print order PDF generation could not be dispatched for %s profile.",
                    profile,
                )


def _handle_confirmed_print_payment(payment: Payment) -> None:
    order = db.session.get(PrintOrder, payment.print_order_id)
    if order is None:
        return
    if order.status in {"cancelled", "refunded"}:
        try:
            request_refund(
                payment.id,
                payment.amount,
                "Verified payment arrived after the print order expired or was cancelled.",
                f"late-print-order:{payment.id}",
            )
        except Exception:
            _app().logger.exception(
                "Automatic refund could not be completed for late print payment %s.",
                payment.id,
            )
        return
    if order.status == "payment_confirmed":
        _queue_print_order_pdfs(payment)


def _print_order_payment_expired(order: PrintOrder) -> bool:
    expiry_hours = int(_app().config.get("PRINT_ORDER_PAYMENT_EXPIRY_HOURS", 24))
    created_at = order.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return datetime.now(UTC) >= created_at + timedelta(hours=expiry_hours)


def request_refund(payment_id: str, amount: Decimal, reason: str | None, key: str) -> dict:
    payment = db.session.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
    if payment is None:
        raise NotFound("Payment was not found.")
    existing = db.session.scalar(select(Refund).where(Refund.idempotency_key == key))
    if payment.status not in {"successful", "partially_refunded"}:
        raise ConflictError("Only a successfully paid transaction can be refunded.")
    if amount <= 0:
        raise ValidationError("Refund amount must be greater than zero.")
    if existing:
        if existing.payment_id != payment.id or existing.amount != amount:
            raise ConflictError("This idempotency key was already used for a different refund.")
        if existing.status not in {"pending", "manual_required"}:
            return serialize_refund(existing)
        refund = existing
    else:
        refund = None
    refund_query = select(func.coalesce(func.sum(Refund.amount), 0)).where(
        Refund.payment_id == payment.id,
        Refund.status.in_(("requested", "pending", "manual_required", "processing", "succeeded")),
    )
    if existing:
        refund_query = refund_query.where(Refund.id != existing.id)
    refunded = db.session.scalar(refund_query) or Decimal("0")
    if amount + refunded > payment.amount:
        raise ConflictError("Refund amount exceeds the unrefunded payment balance.")
    if refund is None:
        refund = Refund(
            payment_id=payment.id,
            amount=amount,
            currency=payment.currency,
            reason=(reason or "")[:500] or None,
            idempotency_key=key,
            status="pending",
        )
        db.session.add(refund)
        db.session.commit()
    if payment.provider not in {"stripe", "paypal"}:
        refund.status = "manual_required"
        db.session.commit()
        return serialize_refund(refund)
    gateway = StripeGateway() if payment.provider == "stripe" else PayPalGateway()
    refund_id, status = gateway.refund(payment, amount, f"{payment.id}:{key}")
    refund.provider_refund_id = refund_id or None
    refund.status = status
    if status == "succeeded":
        _sync_refund_payment_status(payment, refund)
    db.session.commit()
    return serialize_refund(refund)


def create_refund_request(
    payment_id: str,
    user_id: str,
    amount: Decimal,
    reason: str | None,
    key: str,
) -> dict:
    payment = db.session.scalar(
        select(Payment).where(Payment.id == payment_id, Payment.user_id == user_id).with_for_update()
    )
    if payment is None:
        raise NotFound("Payment was not found.")
    existing = db.session.scalar(select(Refund).where(Refund.idempotency_key == key))
    if existing:
        if existing.payment_id != payment.id or existing.amount != amount:
            raise ConflictError("This idempotency key has already been used for a different refund request.")
        return serialize_refund(existing)
    if payment.status not in {"successful", "partially_refunded"}:
        raise ConflictError("Only a successfully paid transaction can have a refund request.")
    if amount <= 0:
        raise ValidationError("Refund amount must be greater than zero.")
    reserved = db.session.scalar(
        select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.payment_id == payment.id,
            Refund.status.in_(("requested", "pending", "manual_required", "processing", "succeeded")),
        )
    ) or Decimal("0")
    if amount + reserved > payment.amount:
        raise ConflictError("Refund amount exceeds the unrefunded payment balance.")
    refund = Refund(
        payment_id=payment.id,
        amount=amount,
        currency=payment.currency,
        reason=(reason or "")[:500] or None,
        idempotency_key=key,
        status="requested",
    )
    db.session.add(refund)
    db.session.commit()
    return serialize_refund(refund)


def approve_refund_request(refund_id: str) -> dict:
    refund = db.session.scalar(select(Refund).where(Refund.id == refund_id).with_for_update())
    if refund is None:
        raise NotFound("Refund was not found.")
    if refund.status not in {"requested", "pending"}:
        raise ConflictError("Only a pending or retryable customer refund request can be approved.")
    payment = db.session.get(Payment, refund.payment_id)
    if payment is None:
        raise NotFound("Payment was not found.")
    if payment.provider not in {"stripe", "paypal"}:
        refund.status = "manual_required"
        db.session.commit()
        return serialize_refund(refund)
    refund.status = "pending"
    db.session.commit()
    gateway = StripeGateway() if payment.provider == "stripe" else PayPalGateway()
    provider_reference, status = gateway.refund(payment, refund.amount, f"refund-request-{refund.id}")
    refund.provider_refund_id = provider_reference
    refund.status = status
    if status == "succeeded":
        _sync_refund_payment_status(payment, refund)
    db.session.commit()
    return serialize_refund(refund)


def reject_refund_request(refund_id: str) -> dict:
    refund = db.session.scalar(select(Refund).where(Refund.id == refund_id).with_for_update())
    if refund is None:
        raise NotFound("Refund was not found.")
    if refund.status != "requested":
        raise ConflictError("Only a pending customer refund request can be rejected.")
    refund.status = "rejected"
    db.session.commit()
    return serialize_refund(refund)


def complete_manual_refund(
    refund_id: str,
    status: str,
    provider_reference: str | None = None,
    *,
    verified: bool = False,
) -> dict:
    refund = db.session.scalar(select(Refund).where(Refund.id == refund_id).with_for_update())
    if refund is None:
        raise NotFound("Refund was not found.")
    if refund.status not in {"manual_required", "processing"}:
        raise ConflictError("This refund is not awaiting manual processing.")
    if status == "processing":
        refund.status = status
    elif status in {"succeeded", "failed"}:
        if status == "succeeded":
            if not verified:
                raise ValidationError("Manual completion requires verified provider confirmation.", {"verified": "required"})
            if not isinstance(provider_reference, str) or not provider_reference.strip():
                raise ValidationError("A confirmed provider refund reference is required.", {"providerReference": "required"})
            normalized_reference = provider_reference.strip()[:160]
            duplicate = db.session.scalar(
                select(Refund).where(
                    Refund.provider_refund_id == normalized_reference,
                    Refund.id != refund.id,
                )
            )
            if duplicate:
                raise ConflictError("This provider refund reference is already assigned to another refund.")
            refund.provider_refund_id = normalized_reference
            refund.status = status
            payment = db.session.get(Payment, refund.payment_id)
            if payment is None:
                raise NotFound("Payment was not found.")
            _sync_refund_payment_status(payment, refund)
        else:
            refund.status = status
    else:
        raise ValidationError("Refund status must be processing, succeeded, or failed.", {"status": "invalid"})
    db.session.commit()
    return serialize_refund(refund)


def _apply_refund_event(payment: Payment | None, payload: dict) -> None:
    refund_id = payload.get("id")
    if not isinstance(refund_id, str):
        return
    refund = db.session.scalar(
        select(Refund).where(Refund.provider_refund_id == refund_id).with_for_update()
    )
    if refund is None:
        return
    currency = str(payload.get("currency") or "").upper()
    if payment and payment.provider == "paypal":
        amount = _paypal_capture_amount(payload)[0]
        if amount is not None and payment.exchange_rate:
            amount = (amount / Decimal(payment.exchange_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        currency = "PKR"
    else:
        amount = _stripe_amount(payload.get("amount"), currency)
    if amount != refund.amount or currency != refund.currency.upper():
        raise ValidationError("Payment provider refund amount or currency does not match the refund.")
    status = payload.get("status")
    if status in {"pending", "succeeded", "failed", "canceled"}:
        previous_status = refund.status
        refund.status = "failed" if status == "canceled" else status
        if refund.status == "succeeded" and previous_status != "succeeded":
            related_payment = payment or db.session.get(Payment, refund.payment_id)
            if related_payment:
                _sync_refund_payment_status(related_payment, refund)


def _sync_refund_payment_status(payment: Payment, refund: Refund) -> None:
    total = db.session.scalar(
        select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.payment_id == payment.id,
            Refund.status == "succeeded",
        )
    ) or Decimal("0")
    payment.status = "refunded" if total >= payment.amount else "partially_refunded"
    order = _payment_order(payment)
    if payment.status == "refunded":
        order.status = "refunded"
    if payment.pdf_order_id:
        for entitlement in db.session.scalars(
            select(DownloadEntitlement).where(
                DownloadEntitlement.pdf_order_id == payment.pdf_order_id,
                DownloadEntitlement.revoked_at.is_(None),
            )
        ):
            entitlement.revoked_at = datetime.now(UTC)
    db.session.add(OrderStatusHistory(
        pdf_order_id=order.id if payment.pdf_order_id else None,
        print_order_id=order.id if payment.print_order_id else None,
        status=payment.status,
        note=f"Refund {refund.id} was processed.",
    ))
    queue_order_event(
        payment.user_id,
        f"refund_succeeded:{refund.id}",
        "payment",
        "Refund processed",
        f"A refund for order {order.order_number} has been processed.",
        "/dashboard/orders",
    )


def _find_payment(provider: str, payment_id: str | None, reference: str | None) -> Payment | None:
    if payment_id:
        payment = db.session.scalar(
            select(Payment).where(Payment.id == payment_id, Payment.provider == provider).with_for_update()
        )
        if payment:
            return payment
    if reference:
        payment = db.session.scalar(
            select(Payment).where(Payment.provider == provider, Payment.provider_payment_id == reference).with_for_update()
        )
        if payment:
            return payment
        return db.session.scalar(
            select(Payment)
            .join(PaymentAttempt, PaymentAttempt.payment_id == Payment.id)
            .where(Payment.provider == provider, PaymentAttempt.provider_reference == reference)
            .with_for_update()
        )
    return None


def _payment_order(payment: Payment):
    order = db.session.get(PdfOrder if payment.pdf_order_id else PrintOrder, payment.pdf_order_id or payment.print_order_id)
    if order is None:
        raise NotFound("Payment order was not found.")
    return order


def _order_title(order, kind: str) -> str:
    return f"{'PDF download' if kind == 'pdf' else 'Printed MemoryBook'} — {order.order_number}"


def serialize_order(
    order,
    kind: str,
    *,
    checkout_url: str | None = None,
    payment_instructions: dict[str, str] | None = None,
) -> dict:
    payment = db.session.scalar(
        select(Payment).where(
            (Payment.pdf_order_id == order.id) if kind == "pdf" else (Payment.print_order_id == order.id)
        )
    )
    if checkout_url is None and payment and payment.status == "pending" and payment.provider != "paypal":
        current_attempt = db.session.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment.id, PaymentAttempt.status == "pending")
            .order_by(PaymentAttempt.attempt_number.desc())
        )
        checkout_url = current_attempt.checkout_url if current_attempt else None
    payload = {
        "id": order.id,
        "projectId": order.project_id,
        "orderNumber": order.order_number,
        "paymentStatus": _frontend_payment_status(payment.status if payment else "pending"),
        "paymentId": payment.id if payment else None,
        "paymentProvider": payment.provider if payment else None,
        "paymentMethod": payment.payment_method if payment else None,
        "paymentReference": payment.provider_payment_id if payment and payment.provider == "manual" else None,
        "paymentInstructions": payment_instructions if payment_instructions is not None else (
            ManualPaymentGateway().create_checkout(payment, "", "").instructions
            if payment and payment.provider == "manual" else None
        ),
        "checkoutUrl": checkout_url,
        "amount": str(order.total_amount),
        "currency": order.currency,
        "pkrAmount": str(payment.pkr_amount) if payment and payment.pkr_amount is not None else None,
        "usdAmount": str(payment.usd_amount) if payment and payment.usd_amount is not None else None,
        "exchangeRate": str(payment.exchange_rate) if payment and payment.exchange_rate is not None else None,
        "status": order.status,
        "paidAt": order.paid_at.isoformat() if order.paid_at else None,
        "createdAt": order.created_at.isoformat(),
    }
    if payment is not None:
        latest_attempt = db.session.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment.id)
            .order_by(PaymentAttempt.attempt_number.desc())
        )
        payload["manualReferenceStatus"] = (
            latest_attempt.status if payment.provider == "manual" and latest_attempt else None
        )
        payload["submittedPaymentReference"] = (
            latest_attempt.provider_reference
            if payment.provider == "manual" and latest_attempt and latest_attempt.status == "submitted"
            else None
        )
    if kind == "pdf":
        job = db.session.scalar(
            select(PdfJob).where(PdfJob.order_id == order.id, PdfJob.generation_profile == "digital")
        )
        payload.update({
            "pageCount": order.page_count,
            "generationStatus": job.status if job else "not_started",
            "title": _document_title(order.project_revision_id),
            "generationError": {
                "code": job.error_code,
                "message": job.error_message,
            } if job and job.status == "failed" else None,
        })
        if job and job.status == "ready" and payment and payment.status == "successful":
            entitlement_id = db.session.scalar(
                select(DownloadEntitlement.id)
                .where(
                    DownloadEntitlement.pdf_order_id == order.id,
                    DownloadEntitlement.user_id == order.user_id,
                    DownloadEntitlement.revoked_at.is_(None),
                )
                .order_by(DownloadEntitlement.created_at.desc())
            )
            if entitlement_id:
                payload["downloadId"] = entitlement_id
    else:
        snapshot = order.price_snapshot or {}
        expires_at = order.created_at + timedelta(
            hours=int(_app().config.get("PRINT_ORDER_PAYMENT_EXPIRY_HOURS", 24))
        )
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        print_pdf_order = db.session.scalar(
            select(PdfOrder).where(PdfOrder.idempotency_key == f"print-free:{order.id}")
        )
        print_pdf_jobs = {}
        if print_pdf_order:
            payload["printPdfOrderId"] = print_pdf_order.id
            for profile in ("digital", "print"):
                job = db.session.scalar(
                    select(PdfJob).where(
                        PdfJob.order_id == print_pdf_order.id,
                        PdfJob.generation_profile == profile,
                    )
                )
                print_pdf_jobs[profile] = {
                    "status": job.status if job else "not_started",
                    "error": {
                        "code": job.error_code,
                        "message": job.error_message,
                    } if job and job.status == "failed" else None,
                }
        payload.update({
            "productionStatus": order.status,
            "pageCount": snapshot.get("pageCount"),
            "paymentExpiresAt": expires_at.isoformat(),
            "paymentExpired": (
                payment is not None
                and payment.status == "pending"
                and datetime.now(UTC) >= expires_at
            ),
            "printPdf": print_pdf_jobs,
            "quote": {
                "id": snapshot.get("quoteId", ""),
                "bookPrice": str(order.book_amount),
                "printingCharge": str(order.printing_amount),
                "additionalPages": str(order.additional_pages_amount),
                "shipping": str(order.shipping_amount),
                "discount": str(order.discount_amount),
                "tax": str(order.tax_amount),
                "taxApplicable": bool(snapshot.get("taxApplicable", False)),
                "total": str(order.total_amount),
                "currency": order.currency,
                "productionEstimate": snapshot.get("productionEstimate"),
                "deliveryEstimate": snapshot.get("deliveryEstimate"),
            },
            "productionEstimate": snapshot.get("productionEstimate"),
            "deliveryEstimate": snapshot.get("deliveryEstimate"),
            "shippingAddress": order.shipping_address_snapshot,
            "quantity": snapshot.get("quantity"),
            "trackingNumber": snapshot.get("trackingNumber"),
        })
    return payload


def serialize_refund(refund: Refund) -> dict:
    return {
        "id": refund.id,
        "paymentId": refund.payment_id,
        "providerRefundId": refund.provider_refund_id,
        "status": refund.status,
        "amount": str(refund.amount),
        "currency": refund.currency,
        "reason": refund.reason,
        "createdAt": refund.created_at.isoformat(),
    }


def serialize_transaction(payment: Payment) -> dict:
    attempts = db.session.scalars(
        select(PaymentAttempt).where(PaymentAttempt.payment_id == payment.id)
        .order_by(PaymentAttempt.attempt_number)
    ).all()
    refunds = db.session.scalars(select(Refund).where(Refund.payment_id == payment.id).order_by(Refund.created_at)).all()
    return {
        "id": payment.id,
        "provider": payment.provider,
        "purpose": payment.purpose,
        "paymentMethod": payment.payment_method,
        "providerPaymentId": payment.provider_payment_id,
        "status": payment.status,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "pkrAmount": str(payment.pkr_amount) if payment.pkr_amount is not None else None,
        "usdAmount": str(payment.usd_amount) if payment.usd_amount is not None else None,
        "exchangeRate": str(payment.exchange_rate) if payment.exchange_rate is not None else None,
        "providerCaptureId": payment.provider_capture_id,
        "orderId": payment.pdf_order_id or payment.print_order_id,
        "attempts": [{
            "number": item.attempt_number,
            "status": item.status,
            "reference": item.provider_reference,
            "failureCode": item.failure_code,
            "failureMessage": item.failure_message,
            "createdAt": item.created_at.isoformat(),
        } for item in attempts],
        "refunds": [serialize_refund(item) for item in refunds],
        "createdAt": payment.created_at.isoformat(),
    }


def _document_title(revision_id: str) -> str | None:
    from memorybook.models import ProjectRevision

    revision = db.session.get(ProjectRevision, revision_id)
    return (revision.document.get("metadata") or {}).get("title") if revision else None


def _frontend_payment_status(status: str) -> str:
    return status


def _stripe_amount(value, currency: str) -> Decimal | None:
    try:
        zero_decimal = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}
        return Decimal(str(value)) / (Decimal(1) if currency.upper() in zero_decimal else Decimal(100))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _minor_to_decimal(value) -> Decimal | None:
    try:
        return (Decimal(str(value)) / Decimal(100)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _paypal_payment_id(resource: dict) -> str | None:
    purchase_units = resource.get("purchase_units")
    if not isinstance(purchase_units, list) or not purchase_units or not isinstance(purchase_units[0], dict):
        return None
    custom_id = purchase_units[0].get("custom_id")
    return custom_id if isinstance(custom_id, str) else None


def _paypal_capture_amount(resource: dict) -> tuple[Decimal | None, str]:
    amount = resource.get("amount")
    if not isinstance(amount, dict):
        return None, ""
    try:
        parsed = Decimal(str(amount.get("value")))
    except (InvalidOperation, ValueError, TypeError):
        return None, ""
    if not parsed.is_finite() or parsed < 0:
        return None, ""
    return parsed.quantize(Decimal("0.01")), str(amount.get("currency_code") or "").upper()


def _app():
    from flask import current_app

    return current_app
