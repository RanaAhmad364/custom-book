from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any

from sqlalchemy import select
from sqlalchemy import update as sql_update

from memorybook.errors import ConflictError, ValidationError
from memorybook.extensions import db
from memorybook.integrations.asset_storage import get_asset_storage
from memorybook.models import (
    DownloadEntitlement,
    DownloadHistory,
    GeneratedFile,
    Payment,
    PdfJob,
    PdfOrder,
    ProjectAsset,
    ProjectRevision,
    UserProject,
)
from memorybook.services.pdf_renderer import PdfRenderError, render_project_pdf
from memorybook.services.notifications import queue_order_event
from werkzeug.exceptions import NotFound


def queue_pdf_generation(order: PdfOrder, profile: str) -> tuple[PdfJob, bool]:
    if profile not in {"digital", "print"}:
        raise ValidationError("PDF profile must be digital or print.", {"profile": "invalid"})
    if order.paid_at is None:
        raise ConflictError("PDF generation is available after payment is confirmed.")
    payment = db.session.scalar(select(Payment).where(Payment.pdf_order_id == order.id))
    if payment is None or payment.status != "successful":
        raise ConflictError("PDF generation requires a verified successful payment.")
    permitted_profiles = order.price_snapshot.get("pdfProfiles", [])
    if not isinstance(permitted_profiles, list):
        permitted_profiles = []
    if profile == "print" and not (
        order.price_snapshot.get("printPdfIncluded") is True or "print" in permitted_profiles
    ):
        raise ConflictError("This purchase does not include the print-ready PDF profile.")

    job = db.session.scalar(
        select(PdfJob)
        .where(PdfJob.order_id == order.id, PdfJob.generation_profile == profile)
        .with_for_update()
    )
    created = job is None
    retry_requested = bool(job and job.status == "failed")
    if created:
        job = PdfJob(order_id=order.id, generation_profile=profile, status="queued")
        db.session.add(job)
        db.session.flush()
    elif job.status == "failed":
        job.status = "queued"
        job.error_code = None
        job.error_message = None
        job.started_at = None
        job.finished_at = None
    dispatch = created or retry_requested
    db.session.commit()
    return job, dispatch


def serialize_pdf_job(job: PdfJob) -> dict[str, Any]:
    file = db.session.scalar(
        select(GeneratedFile).where(
            GeneratedFile.pdf_order_id == job.order_id,
            GeneratedFile.generation_profile == job.generation_profile,
        )
    )
    return {
        "id": job.id,
        "profile": job.generation_profile,
        "status": job.status,
        "attemptCount": job.attempt_count,
        "error": {"code": job.error_code, "message": job.error_message} if job.error_code else None,
        "file": {
            "id": file.id,
            "sizeBytes": file.byte_size,
            "checksumSha256": file.checksum_sha256,
            "createdAt": file.created_at.isoformat(),
        } if file else None,
        "createdAt": job.created_at.isoformat(),
        "updatedAt": job.updated_at.isoformat(),
    }


def generate_pdf_job(job_id: str) -> dict[str, Any]:
    job = db.session.get(PdfJob, job_id)
    if job is None:
        raise PdfRenderError("job_not_found", "PDF generation job was not found.")
    if job.status == "ready":
        return serialize_pdf_job(job)
    claimed = db.session.execute(
        sql_update(PdfJob)
        .where(PdfJob.id == job_id, PdfJob.status == "queued")
        .values(
            status="generating",
            attempt_count=PdfJob.attempt_count + 1,
            started_at=datetime.now(UTC),
            finished_at=None,
            error_code=None,
            error_message=None,
        )
    )
    if claimed.rowcount != 1:
        db.session.rollback()
        return serialize_pdf_job(db.session.get(PdfJob, job_id))

    order = db.session.get(PdfOrder, job.order_id)
    payment = db.session.scalar(select(Payment).where(Payment.pdf_order_id == order.id)) if order else None
    if order is None or order.paid_at is None or payment is None or payment.status != "successful":
        raise PdfRenderError("payment_not_confirmed", "PDF generation requires confirmed payment.")
    project = db.session.get(UserProject, order.project_id)
    revision = db.session.get(ProjectRevision, order.project_revision_id)
    if project is None or revision is None or revision.project_id != project.id:
        raise PdfRenderError("revision_unavailable", "The purchased project revision is unavailable.")

    db.session.commit()

    document = revision.document
    project_assets = db.session.scalars(
        select(ProjectAsset).where(ProjectAsset.project_id == project.id)
    ).all()
    asset_keys = {asset.id: asset.storage_key for asset in project_assets}
    referenced_assets = _referenced_asset_ids(document)
    if referenced_assets - asset_keys.keys():
        raise PdfRenderError("missing_asset", "A photo in this saved revision is no longer available.")

    storage = get_asset_storage()
    asset_contents: dict[str, bytes] = {}
    for asset_id in referenced_assets:
        asset_contents[asset_id] = storage.download(asset_keys[asset_id])

    profile = job.generation_profile
    saved_specification = order.price_snapshot.get("printSpecification")
    print_specification = dict(saved_specification) if isinstance(saved_specification, dict) else {}
    print_specification.setdefault("bleedInches", _app_config("PDF_PRINT_BLEED_INCHES", 0.125))
    print_specification.setdefault("safeMarginInches", _app_config("PDF_PRINT_SAFE_MARGIN_INCHES", 0.25))
    pdf_bytes, details = render_project_pdf(
        document,
        asset_contents,
        profile,
        print_specification=print_specification,
        minimum_print_dpi=int(_app_config("PDF_MIN_PRINT_DPI", 300)),
        configured_font_directory=_app_config("PDF_FONT_DIR", None),
        maximum_output_bytes=int(_app_config("PDF_MAX_OUTPUT_BYTES", 100 * 1024 * 1024)),
    )
    storage_key = f"generated/pdf/{order.id}/{profile}/{job.id}.pdf"
    storage.upload(storage_key, BytesIO(pdf_bytes), "application/pdf")

    payment = db.session.scalar(
        select(Payment).where(Payment.pdf_order_id == order.id).with_for_update()
    )
    if payment is None or payment.status != "successful":
        raise PdfRenderError("payment_not_confirmed", "PDF generation requires confirmed payment.")

    generated_file = db.session.scalar(
        select(GeneratedFile).where(
            GeneratedFile.pdf_order_id == order.id,
            GeneratedFile.generation_profile == profile,
        )
    )
    if generated_file is None:
        generated_file = GeneratedFile(
            pdf_order_id=order.id,
            generation_profile=profile,
            storage_key=storage_key,
            file_type="application/pdf",
            byte_size=details["byteSize"],
            checksum_sha256=details["checksumSha256"],
        )
        db.session.add(generated_file)
        db.session.flush()
    else:
        generated_file.storage_key = storage_key
        generated_file.file_type = "application/pdf"
        generated_file.byte_size = details["byteSize"]
        generated_file.checksum_sha256 = details["checksumSha256"]

    entitlement = db.session.scalar(
        select(DownloadEntitlement).where(
            DownloadEntitlement.user_id == order.user_id,
            DownloadEntitlement.pdf_order_id == order.id,
            DownloadEntitlement.generated_file_id == generated_file.id,
        )
    )
    if entitlement is None:
        entitlement = DownloadEntitlement(
            user_id=order.user_id,
            pdf_order_id=order.id,
            generated_file_id=generated_file.id,
            max_downloads=int(_app_config("PDF_DOWNLOAD_MAX_COUNT", 5)),
            expires_at=datetime.now(UTC) + timedelta(days=int(_app_config("PDF_DOWNLOAD_TTL_DAYS", 30))),
        )
        db.session.add(entitlement)
    job.status = "ready"
    job.finished_at = datetime.now(UTC)
    job.error_code = None
    job.error_message = None
    queue_order_event(
        order.user_id,
        f"pdf_ready:{order.id}:{profile}",
        "pdf",
        "PDF ready",
        f"Your PDF for order {order.order_number} is ready to download.",
        f"/pdf/orders/{order.id}",
    )
    db.session.commit()
    return {**serialize_pdf_job(job), "output": details}


def create_download_link(user_id: str, download_id: str, ip_address: str | None) -> dict[str, Any]:
    entitlement = db.session.scalar(
        select(DownloadEntitlement)
        .where(DownloadEntitlement.id == download_id, DownloadEntitlement.user_id == user_id)
        .with_for_update()
    )
    if entitlement is None:
        raise NotFound("Download was not found.")
    now = datetime.now(UTC)
    expiry = entitlement.expires_at
    if expiry is not None and (expiry.replace(tzinfo=UTC) if expiry.tzinfo is None else expiry) <= now:
        raise ConflictError("This download entitlement has expired.")
    if entitlement.revoked_at is not None:
        raise ConflictError("This download entitlement has been revoked.")
    payment = db.session.scalar(
        select(Payment).where(Payment.pdf_order_id == entitlement.pdf_order_id)
    )
    if payment is None or payment.status != "successful":
        entitlement.revoked_at = now
        db.session.commit()
        raise ConflictError("This download is unavailable because its payment is no longer active.")
    if entitlement.max_downloads is not None and entitlement.download_count >= entitlement.max_downloads:
        raise ConflictError("This download has reached its download limit.")
    generated_file = db.session.get(GeneratedFile, entitlement.generated_file_id)
    if generated_file is None:
        raise ConflictError("The generated PDF is not ready for download.")
    storage = get_asset_storage()
    url = storage.download_url(generated_file.storage_key)
    entitlement.download_count += 1
    db.session.add(DownloadHistory(
        entitlement_id=entitlement.id,
        generated_file_id=generated_file.id,
        ip_address=ip_address,
    ))
    db.session.commit()
    return {
        "id": entitlement.id,
        "profile": generated_file.generation_profile,
        "url": url,
        "fileName": f"{_safe_filename(db.session.get(PdfOrder, entitlement.pdf_order_id).order_number)}-{generated_file.generation_profile}.pdf",
        "sizeBytes": generated_file.byte_size,
        "checksumSha256": generated_file.checksum_sha256,
        "downloadCount": entitlement.download_count,
        "maxDownloads": entitlement.max_downloads,
        "expiresAt": entitlement.expires_at.isoformat() if entitlement.expires_at else None,
    }


def list_user_downloads(user_id: str) -> list[dict[str, Any]]:
    rows = db.session.execute(
        select(DownloadEntitlement, GeneratedFile, PdfOrder)
        .join(GeneratedFile, GeneratedFile.id == DownloadEntitlement.generated_file_id)
        .join(PdfOrder, PdfOrder.id == DownloadEntitlement.pdf_order_id)
        .where(DownloadEntitlement.user_id == user_id)
        .order_by(DownloadEntitlement.created_at.desc())
    ).all()
    return [
        {
            "id": entitlement.id,
            "orderId": order.id,
            "orderNumber": order.order_number,
            "profile": generated_file.generation_profile,
            "status": "ready" if entitlement.revoked_at is None else "revoked",
            "sizeBytes": generated_file.byte_size,
            "checksumSha256": generated_file.checksum_sha256,
            "downloadCount": entitlement.download_count,
            "maxDownloads": entitlement.max_downloads,
            "createdAt": entitlement.created_at.isoformat(),
            "expiresAt": entitlement.expires_at.isoformat() if entitlement.expires_at else None,
        }
        for entitlement, generated_file, order in rows
    ]


def _referenced_asset_ids(document: dict[str, Any]) -> set[str]:
    found = set()
    for page in document.get("pages", []):
        for element in page.get("elements", []):
            if element.get("type") == "image":
                found.add(element.get("assetId"))
    front = ((document.get("cover") or {}).get("design") or {}).get("front") or {}
    if front.get("photoAssetId"):
        found.add(front["photoAssetId"])
    return found


def _safe_filename(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "-" for character in value)[:60]


def _app_config(key: str, default: Any) -> Any:
    from flask import current_app

    return current_app.config.get(key, default)
