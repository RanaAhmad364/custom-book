from __future__ import annotations

from flask import Blueprint, jsonify, request

from memorybook.errors import ValidationError
from memorybook.extensions import limiter
from memorybook.models import BookCategory, BookCollection
from memorybook.permissions import get_authenticated_user, roles_required
from memorybook.services import admin
from memorybook.services.payments import (
    approve_refund_request,
    complete_manual_refund,
    reject_refund_request,
)

admin_blueprint = Blueprint("admin", __name__)


def _body() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("A JSON object is required.")
    return payload


@admin_blueprint.get("/dashboard")
@roles_required("admin")
def dashboard():
    return jsonify(admin.dashboard_metrics())


@admin_blueprint.post("/assets")
@limiter.limit("30 per hour")
@roles_required("admin")
def upload_catalog_asset():
    file = request.files.get("file")
    if file is None:
        raise ValidationError("An image file is required.", {"file": "required"})
    return jsonify({"asset": admin.upload_catalog_asset(file, get_authenticated_user())}), 201


@admin_blueprint.post("/design-assets")
@limiter.limit("30 per hour")
@roles_required("admin")
def upload_admin_design_asset():
    file = request.files.get("file")
    if file is None:
        raise ValidationError("An image file is required.", {"file": "required"})
    return jsonify({"asset": admin.upload_admin_design_asset(file, get_authenticated_user())}), 201


def _design_version():
    value = request.headers.get("If-Match")
    if value is None:
        return None, (jsonify({
            "error": {
                "code": "PRECONDITION_REQUIRED",
                "message": "Send the current book design version in the If-Match header.",
            }
        }), 428)
    try:
        version = int(value.strip().removeprefix("W/").strip('"'))
    except ValueError as failure:
        raise ValidationError("If-Match must contain a design version.", {"If-Match": "invalid"}) from failure
    if version < 1:
        raise ValidationError("If-Match must contain a positive design version.", {"If-Match": "invalid"})
    return version, None


@admin_blueprint.post("/books/<string:product_id>/design")
@roles_required("admin")
def ensure_book_design(product_id: str):
    result = admin.ensure_book_design(product_id)
    response = jsonify(result)
    response.headers["ETag"] = f'"{result["template"]["version"]}"'
    return response


@admin_blueprint.put("/books/<string:product_id>/design")
@roles_required("admin")
def save_book_design(product_id: str):
    version, error_response = _design_version()
    if error_response:
        return error_response
    body = _body()
    result = admin.save_book_design(product_id, body.get("document"), version)
    response = jsonify(result)
    response.headers["ETag"] = f'"{result["template"]["version"]}"'
    return response


@admin_blueprint.post("/books/<string:product_id>/design/publish")
@roles_required("admin")
def publish_book_design(product_id: str):
    version, error_response = _design_version()
    if error_response:
        return error_response
    result = admin.publish_book_design(product_id, version)
    response = jsonify(result)
    response.headers["ETag"] = f'"{result["template"]["version"]}"'
    return response


@admin_blueprint.post("/books/<string:product_id>/design/unpublish")
@roles_required("admin")
def unpublish_book_design(product_id: str):
    return jsonify(admin.unpublish_book_design(product_id))


@admin_blueprint.get("/users")
@roles_required("admin")
def users():
    return jsonify(admin.list_users(request.args))


@admin_blueprint.patch("/users/<string:user_id>")
@roles_required("admin")
def update_user(user_id: str):
    return jsonify({"user": admin.set_user_status(user_id, _body())})


@admin_blueprint.get("/books")
@roles_required("admin")
def books():
    return jsonify(admin.list_products(request.args))


@admin_blueprint.post("/books")
@roles_required("admin")
def create_book():
    return jsonify({"book": admin.save_product(_body())}), 201


@admin_blueprint.patch("/books/<string:book_id>")
@roles_required("admin")
def update_book(book_id: str):
    return jsonify({"book": admin.save_product(_body(), book_id)})


@admin_blueprint.delete("/books/<string:book_id>")
@roles_required("admin")
def delete_book(book_id: str):
    admin.delete_product(book_id)
    return "", 204


@admin_blueprint.post("/books/<string:book_id>/publish")
@roles_required("admin")
def publish_book(book_id: str):
    return jsonify({"book": admin.set_product_published(book_id, True)})


@admin_blueprint.post("/books/<string:book_id>/unpublish")
@roles_required("admin")
def unpublish_book(book_id: str):
    return jsonify({"book": admin.set_product_published(book_id, False)})


@admin_blueprint.get("/categories")
@roles_required("admin")
def categories():
    return jsonify(admin.list_simple_catalog(BookCategory, "category", request.args))


@admin_blueprint.post("/categories")
@roles_required("admin")
def create_category():
    return jsonify({"category": admin.save_simple_catalog(BookCategory, "category", _body())}), 201


@admin_blueprint.patch("/categories/<string:category_id>")
@roles_required("admin")
def update_category(category_id: str):
    return jsonify({"category": admin.save_simple_catalog(BookCategory, "category", _body(), category_id)})


@admin_blueprint.delete("/categories/<string:category_id>")
@roles_required("admin")
def delete_category(category_id: str):
    admin.delete_simple_catalog(BookCategory, "category", category_id)
    return "", 204


@admin_blueprint.get("/collections")
@roles_required("admin")
def collections():
    return jsonify(admin.list_simple_catalog(BookCollection, "collection", request.args))


@admin_blueprint.post("/collections")
@roles_required("admin")
def create_collection():
    return jsonify({"collection": admin.save_simple_catalog(BookCollection, "collection", _body())}), 201


@admin_blueprint.patch("/collections/<string:collection_id>")
@roles_required("admin")
def update_collection(collection_id: str):
    return jsonify({"collection": admin.save_simple_catalog(BookCollection, "collection", _body(), collection_id)})


@admin_blueprint.delete("/collections/<string:collection_id>")
@roles_required("admin")
def delete_collection(collection_id: str):
    admin.delete_simple_catalog(BookCollection, "collection", collection_id)
    return "", 204


@admin_blueprint.get("/templates")
@roles_required("admin")
def templates():
    return jsonify(admin.list_templates_admin(request.args))


@admin_blueprint.post("/templates")
@roles_required("admin")
def create_template():
    return jsonify({"template": admin.save_template(_body())}), 201


@admin_blueprint.patch("/templates/<string:template_id>")
@roles_required("admin")
def update_template(template_id: str):
    return jsonify({"template": admin.save_template(_body(), template_id)})


@admin_blueprint.delete("/templates/<string:template_id>")
@roles_required("admin")
def delete_template(template_id: str):
    admin.delete_template(template_id)
    return "", 204


@admin_blueprint.post("/templates/<string:template_id>/publish")
@roles_required("admin")
def publish_template(template_id: str):
    return jsonify({"template": admin.publish_template(template_id, True)})


@admin_blueprint.post("/templates/<string:template_id>/unpublish")
@roles_required("admin")
def unpublish_template(template_id: str):
    return jsonify({"template": admin.publish_template(template_id, False)})


@admin_blueprint.get("/templates/<string:template_id>/versions")
@roles_required("admin")
def template_versions(template_id: str):
    return jsonify({"items": admin.get_template_versions(template_id)})


@admin_blueprint.get("/orders")
@roles_required("admin")
def orders():
    return jsonify(admin.list_orders(request.args))


@admin_blueprint.patch("/orders/<string:kind>/<string:order_id>")
@roles_required("admin")
def update_order(kind: str, order_id: str):
    return jsonify({"order": admin.update_order(order_id, kind, _body(), get_authenticated_user().id)})


@admin_blueprint.get("/payments")
@roles_required("admin")
def payments():
    return jsonify(admin.list_payments(request.args))


@admin_blueprint.get("/refunds")
@roles_required("admin")
def refunds():
    return jsonify(admin.list_payments(request.args, refunds=True))


@admin_blueprint.patch("/refunds/<string:refund_id>")
@roles_required("admin")
def update_refund(refund_id: str):
    payload = _body()
    status = payload.get("status")
    if status not in {"approved", "rejected", "processing", "succeeded", "failed"}:
        raise ValidationError("Refund status is invalid.", {"status": "invalid"})
    reference = payload.get("providerReference")
    if reference is not None and (not isinstance(reference, str) or len(reference) > 160):
        raise ValidationError("Provider refund reference is invalid.", {"providerReference": "invalid"})
    verified = payload.get("verified", False)
    if not isinstance(verified, bool):
        raise ValidationError("verified must be a boolean.", {"verified": "invalid"})
    if status == "approved":
        result = approve_refund_request(refund_id)
    elif status == "rejected":
        result = reject_refund_request(refund_id)
    else:
        result = complete_manual_refund(refund_id, status, reference, verified=verified)
    admin.record_manual_refund_action(
        refund_id,
        {"status": status, "providerReference": reference, "verified": verified},
    )
    return jsonify({"refund": result})


@admin_blueprint.get("/pricing")
@roles_required("admin")
def pricing():
    return jsonify(admin.list_pricing())


@admin_blueprint.patch("/pricing/<string:kind>/<string:item_id>")
@roles_required("admin")
def update_pricing(kind: str, item_id: str):
    return jsonify({"item": admin.update_pricing(kind, item_id, _body())})


@admin_blueprint.post("/pricing/<string:kind>")
@roles_required("admin")
def create_pricing(kind: str):
    return jsonify({"item": admin.create_pricing(kind, _body())}), 201


@admin_blueprint.delete("/pricing/<string:kind>/<string:item_id>")
@roles_required("admin")
def delete_pricing(kind: str, item_id: str):
    admin.delete_pricing(kind, item_id)
    return "", 204


@admin_blueprint.post("/pricing/variants")
@roles_required("admin")
def create_pricing_variant():
    return jsonify({"variant": admin.create_variant(_body())}), 201


@admin_blueprint.get("/support")
@roles_required("admin")
def support():
    return jsonify(admin.list_support(request.args))


@admin_blueprint.patch("/support/<string:ticket_id>")
@roles_required("admin")
def update_support(ticket_id: str):
    return jsonify({"ticket": admin.update_support(ticket_id, _body(), get_authenticated_user().id)})


@admin_blueprint.get("/notifications")
@roles_required("admin")
def notifications():
    return jsonify(admin.list_notifications(request.args, admin_user_id=get_authenticated_user().id))


@admin_blueprint.get("/settings")
@roles_required("admin")
def settings():
    return jsonify({"items": admin.list_settings()})


@admin_blueprint.post("/settings")
@roles_required("admin")
def create_setting():
    return jsonify({"setting": admin.save_setting(_body())}), 201


@admin_blueprint.patch("/settings/<string:setting_id>")
@roles_required("admin")
def update_setting(setting_id: str):
    return jsonify({"setting": admin.save_setting(_body(), setting_id)})


@admin_blueprint.get("/reports")
@roles_required("admin")
def reports():
    return jsonify(admin.reports_summary())


@admin_blueprint.get("/activity")
@roles_required("admin")
def activity():
    return jsonify(admin.list_activity(request.args))


@admin_blueprint.get("/discount-codes")
@roles_required("admin")
def discount_codes():
    return jsonify({"items": admin.list_discount_codes()})


@admin_blueprint.post("/discount-codes")
@roles_required("admin")
def create_discount_code():
    return jsonify({"discountCode": admin.create_discount_code(_body())}), 201


@admin_blueprint.post("/emails")
@roles_required("admin")
def send_email():
    return jsonify({"email": admin.send_transactional_email(_body())}), 202
