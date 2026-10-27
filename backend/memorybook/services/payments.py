from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import NotFound

from memorybook.errors import ConflictError, ServiceUnavailableError, ValidationError
from memorybook.extensions import db
from memorybook.integrations.payment_gateways import (
    JazzCashGateway,
    ManualPaymentGateway,
    StripeGateway,
    available_payment_methods,
    provider_for,
)
from memorybook.models import (
    DownloadEntitlement,
    OrderStatusHistory,
    Payment,
    PaymentAttempt,
    PaymentWebhookEvent,
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
    provider = provider_for(order.currency, provider_name, payment_method)
    payment = db.session.scalar(
        select(Payment).where(
            (Payment.pdf_order_id == order.id) if kind == "pdf" else (Payment.print_order_id == order.id)
        )
    )
    if payment is not None:
        if payment.status == "successful":
            return serialize_order(order, kind)
        if payment.status not in {"failed", "pending"}:
            raise ConflictError("This order already has a completed payment.")
        return serialize_order(order, kind)

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


def submit_manual_payment_reference(payment: Payment, user_id: str, reference: str) -> dict:
    if payment.user_id != user_id:
        raise NotFound("Payment was not found.")
    if payment.provider != "manual" or payment.status != "pending":
        raise ConflictError("This payment is not awaiting manual confirmation.")
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
    if approved and payment.pdf_order_id:
        _queue_pdf_generation(payment)
    return serialize_transaction(payment)


def process_stripe_event(raw_body: bytes, signature: str | None) -> dict:
    event = StripeGateway().verify_event(raw_body, signature)
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
    if refund_event:
        _apply_refund_event(payment, provider_payload)
    elif payment is None:
        raise ValidationError("Payment provider event does not match a pending payment.")
    elif success or failure:
        if amount is None or amount != payment.amount or currency != payment.currency.upper():
            raise ValidationError("Payment provider amount or currency does not match the order.")
        _apply_payment_result(payment, success=success, provider_reference=provider_reference)
    event.processed_at = datetime.now(UTC)
    db.session.commit()
    if success and payment is not None and payment.pdf_order_id:
        _queue_pdf_generation(payment)
    return {"received": True, "processed": True}


def _apply_payment_result(
    payment: Payment,
    *,
    success: bool,
    provider_reference: str | None,
    changed_by_user_id: str | None = None,
) -> None:
    if payment.status in {"refunded", "partially_refunded"}:
        return
    if payment.status == "successful":
        return
    if payment.status == "failed" and not success:
        return
    order = _payment_order(payment)
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
        if attempt:
            attempt.status = "successful"
            attempt.provider_reference = provider_reference or attempt.provider_reference
        db.session.execute(
            update(PaymentAttempt)
            .where(PaymentAttempt.payment_id == payment.id, PaymentAttempt.status == "pending")
            .values(status="cancelled")
        )
        order.paid_at = datetime.now(UTC)
        old_status = order.status
        order.status = "paid" if payment.pdf_order_id else "payment_confirmed"
        verification_note = (
            "Manual transfer reviewed and approved by an administrator."
            if payment.provider == "manual"
            else "Payment verified by payment provider."
        )
        if payment.print_order_id and old_status != order.status:
            db.session.add(OrderStatusHistory(
                print_order_id=order.id,
                status="payment_confirmed",
                note=verification_note,
                changed_by_user_id=changed_by_user_id,
            ))
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
            "Payment confirmed",
            f"Payment for order {order.order_number} has been confirmed.",
            f"/dashboard/orders",
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


def _queue_pdf_generation(payment: Payment) -> None:
    from memorybook.services.pdf_generation import queue_pdf_generation

    order = db.session.get(PdfOrder, payment.pdf_order_id)
    if order is None or order.paid_at is None:
        return
    job, dispatch = queue_pdf_generation(order, "digital")
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
    if payment.provider != "stripe":
        refund.status = "manual_required"
        db.session.commit()
        return serialize_refund(refund)
    gateway = StripeGateway()
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
    if payment.provider != "stripe":
        refund.status = "manual_required"
        db.session.commit()
        return serialize_refund(refund)
    refund.status = "pending"
    db.session.commit()
    provider_reference, status = StripeGateway().refund(payment, refund.amount, f"refund-request-{refund.id}")
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
    if checkout_url is None and payment and payment.status == "pending":
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
        from memorybook.models import PdfJob

        job = db.session.scalar(
            select(PdfJob).where(PdfJob.order_id == order.id, PdfJob.generation_profile == "digital")
        )
        payload.update({
            "pageCount": order.page_count,
            "generationStatus": job.status if job else "not_started",
            "title": _document_title(order.project_revision_id),
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
        payload.update({
            "productionStatus": order.status,
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


def _app():
    from flask import current_app

    return current_app
