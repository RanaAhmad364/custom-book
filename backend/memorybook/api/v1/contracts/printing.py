from flask import Blueprint, jsonify, request
from sqlalchemy import select
from werkzeug.exceptions import NotFound

from memorybook.errors import ValidationError
from memorybook.extensions import db, limiter
from memorybook.models import Payment, PrintOrder
from memorybook.permissions import active_user_required, get_authenticated_user
from memorybook.services.orders import (
    create_print_order,
    create_print_quote,
    get_user_order,
    list_user_orders,
    request_order_cancellation,
)
from memorybook.services.payments import serialize_transaction

print_blueprint = Blueprint("printing_contract", __name__)


@print_blueprint.post("/quotes")
@active_user_required
@limiter.limit("30 per minute")
def quote():
    body = _body()
    project_id = _required_string(body.get("projectId"), "projectId", 36)
    result = create_print_quote(
        project_id,
        get_authenticated_user().id,
        body.get("configuration"),
        body.get("shippingAddress"),
    )
    return jsonify(result)


@print_blueprint.post("/orders")
@active_user_required
@limiter.limit("10 per minute")
def create_order():
    body = _body()
    project_id = _required_string(body.get("projectId"), "projectId", 36)
    quote_id = _required_string(body.get("quoteId"), "quoteId", 36)
    key = _idempotency_key()
    result = create_print_order(
        project_id,
        get_authenticated_user().id,
        body.get("configuration"),
        body.get("shippingAddress"),
        quote_id,
        key,
        body.get("provider"),
        body.get("paymentMethod"),
    )
    return jsonify(result), 201


@print_blueprint.get("/orders")
@active_user_required
def list_orders():
    return jsonify({"items": list_user_orders("print", get_authenticated_user().id)})


@print_blueprint.get("/orders/<order_id>")
@active_user_required
def get_order(order_id: str):
    result = get_user_order("print", order_id, get_authenticated_user().id)
    payment = db.session.scalar(
        select(Payment).where(Payment.print_order_id == order_id, Payment.user_id == get_authenticated_user().id)
    )
    if payment:
        result["payment"] = serialize_transaction(payment)
    return jsonify(result)


@print_blueprint.post("/orders/<order_id>/cancellation-requests")
@active_user_required
@limiter.limit("5 per minute")
def request_cancellation(order_id: str):
    body = _body()
    reason = _required_string(body.get("reason"), "reason", 500)
    if len(reason.strip()) < 5:
        raise ValidationError("Add a short reason for the cancellation request.", {"reason": "too_short"})
    return jsonify(request_order_cancellation(order_id, get_authenticated_user().id, reason))


def _body() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("A JSON object is required.")
    return payload


def _required_string(value, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValidationError(f"{field} is required.", {field: "invalid"})
    return value.strip()


def _idempotency_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 128:
        raise ValidationError("A valid Idempotency-Key header is required.", {"idempotencyKey": "required"})
    return key
