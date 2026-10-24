from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select
from werkzeug.exceptions import NotFound

from memorybook.errors import ConflictError, ServiceUnavailableError, ValidationError
from memorybook.extensions import db, limiter
from memorybook.models import PdfJob, PdfOrder
from memorybook.permissions import active_user_required, get_authenticated_user
from memorybook.services.pdf_generation import (
    create_download_link,
    list_user_downloads,
    queue_pdf_generation,
    serialize_pdf_job,
)
from memorybook.services.orders import create_pdf_order, get_user_order, list_user_orders, pdf_offer

pdf_blueprint = Blueprint("pdf_contract", __name__)


@pdf_blueprint.get("/offer")
@active_user_required
def offer():
    project_id = request.args.get("projectId", "").strip()
    if not project_id:
        raise ValidationError("projectId is required.", {"projectId": "required"})
    return jsonify(pdf_offer(project_id, get_authenticated_user().id))


@pdf_blueprint.post("/orders")
@active_user_required
@limiter.limit("10 per minute")
def create_order():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("A JSON object is required.")
    project_id = body.get("projectId")
    if not isinstance(project_id, str) or not project_id:
        raise ValidationError("projectId is required.", {"projectId": "required"})
    key = _idempotency_key()
    order = create_pdf_order(
        project_id,
        get_authenticated_user().id,
        key,
        body.get("provider"),
        body.get("paymentMethod"),
    )
    return jsonify(order), 201


@pdf_blueprint.get("/orders/<order_id>")
@active_user_required
def get_order(order_id: str):
    return jsonify(get_user_order("pdf", order_id, get_authenticated_user().id))


@pdf_blueprint.get("/orders")
@active_user_required
def list_orders():
    return jsonify({"items": list_user_orders("pdf", get_authenticated_user().id)})


@pdf_blueprint.post("/orders/<order_id>/generate")
@active_user_required
@limiter.limit("5 per minute")
def request_generation(order_id: str):
    order = db.session.scalar(select(PdfOrder).where(
        PdfOrder.id == order_id,
        PdfOrder.user_id == get_authenticated_user().id,
    ).with_for_update())
    if order is None:
        raise NotFound("PDF order was not found.")
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise ValidationError("A JSON object is required.")
    profile = body.get("profile", "digital")
    if not isinstance(profile, str):
        raise ValidationError("PDF profile must be digital or print.", {"profile": "invalid"})
    if order.paid_at is None:
        raise ConflictError("PDF generation is available after payment is confirmed.")
    job, dispatch = queue_pdf_generation(order, profile)
    if dispatch:
        try:
            current_app.extensions["celery"].send_task("memorybook.generate_pdf", args=[job.id])
        except Exception as failure:
            db.session.rollback()
            failed_job = db.session.get(PdfJob, job.id)
            if failed_job is not None:
                failed_job.status = "failed"
                failed_job.error_code = "queue_unavailable"
                failed_job.error_message = "The PDF worker could not be reached. Please retry."
                db.session.commit()
            current_app.logger.exception("PDF generation task could not be dispatched.")
            raise ServiceUnavailableError("PDF generation is temporarily unavailable. Please retry.") from failure
    return jsonify({"job": serialize_pdf_job(job)}), 202


@pdf_blueprint.get("/jobs/<job_id>")
@active_user_required
def get_generation_job(job_id: str):
    job = db.session.scalar(
        select(PdfJob)
        .join(PdfOrder, PdfOrder.id == PdfJob.order_id)
        .where(PdfJob.id == job_id, PdfOrder.user_id == get_authenticated_user().id)
    )
    if job is None:
        raise NotFound("PDF generation job was not found.")
    return jsonify({"job": serialize_pdf_job(job)})


@pdf_blueprint.get("/downloads")
@active_user_required
def list_downloads():
    return jsonify({"items": list_user_downloads(get_authenticated_user().id)})


@pdf_blueprint.get("/downloads/<download_id>")
@active_user_required
def get_download(download_id: str):
    download = create_download_link(
        get_authenticated_user().id,
        download_id,
        request.remote_addr,
    )
    download["urlExpiresInSeconds"] = current_app.config["ASSET_S3_PRESIGNED_URL_TTL"]
    return jsonify({"download": download})


def _idempotency_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 128:
        raise ValidationError("A valid Idempotency-Key header is required.", {"idempotencyKey": "required"})
    return key
