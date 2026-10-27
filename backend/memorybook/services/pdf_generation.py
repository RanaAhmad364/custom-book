from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
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
    PrintOrder,
    OrderStatusHistory,
    ProjectAsset,
    ProjectRevision,
    UserProject,
)
from memorybook.services.catalog_projects import create_revision
from memorybook.services.pdf_renderer import PdfRenderError, render_project_pdf
from memorybook.services.notifications import queue_order_event
from werkzeug.exceptions import NotFound


def queue_pdf_generation(
    order: PdfOrder,
    profile: str,
    *,
    refresh_current_document: bool = False,
) -> tuple[PdfJob, bool]:
    if profile not in {"digital", "print"}:
        raise ValidationError("PDF profile must be digital or print.", {"profile": "invalid"})
    if order.paid_at is None:
        payment = db.session.scalar(select(Payment).where(Payment.pdf_order_id == order.id))
        if payment and payment.status == "pending":
            raise ConflictError("PDF payment is still pending.", error_code="PDF_PAYMENT_PENDING")
        raise ConflictError("This PDF has not been purchased.", error_code="PDF_NOT_PURCHASED")
    payment = db.session.scalar(select(Payment).where(Payment.pdf_order_id == order.id))
    if payment is None or payment.status != "successful":
        if payment and payment.status == "pending":
            raise ConflictError("PDF payment is still pending.", error_code="PDF_PAYMENT_PENDING")
        raise ConflictError("This PDF has not been purchased.", error_code="PDF_NOT_PURCHASED")
    revision_refreshed = False
    if refresh_current_document:
        project = db.session.scalar(
            select(UserProject).where(UserProject.id == order.project_id).with_for_update()
        )
        if project is None or not project.document:
            raise ConflictError("The purchased project is no longer available for PDF generation.")
        revision = db.session.get(ProjectRevision, order.project_revision_id)
        if revision is None or revision.document_version != project.version:
            revision = create_revision(project, project.version)
            order.project_revision_id = revision.id
            order.page_count = int(project.page_count)
            revision_refreshed = True
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
    elif job.status == "ready" and revision_refreshed:
        job.status = "queued"
        job.error_code = None
        job.error_message = None
        job.started_at = None
        job.finished_at = None
    dispatch = created or retry_requested
    if job.status == "queued" and revision_refreshed:
        dispatch = True
    db.session.commit()
    return job, dispatch


def project_pdf_access(project_id: str, user_id: str) -> dict[str, Any]:
    project = db.session.scalar(
        select(UserProject).where(
            UserProject.id == project_id,
            UserProject.user_id == user_id,
            UserProject.status != "deleted",
        )
    )
    if project is None:
        raise NotFound("Project was not found.")

    order = db.session.scalar(
        select(PdfOrder)
        .join(Payment, Payment.pdf_order_id == PdfOrder.id)
        .where(
            PdfOrder.project_id == project.id,
            PdfOrder.user_id == user_id,
            Payment.status == "successful",
        )
        .order_by(PdfOrder.created_at.desc())
        .limit(1)
    )
    if order is None:
        order = db.session.scalar(
            select(PdfOrder)
            .where(PdfOrder.project_id == project.id, PdfOrder.user_id == user_id)
            .order_by(PdfOrder.created_at.desc())
            .limit(1)
        )
    if order is None:
        return {"projectId": project.id, "state": "not_purchased"}

    payment = db.session.scalar(select(Payment).where(Payment.pdf_order_id == order.id))
    result: dict[str, Any] = {
        "projectId": project.id,
        "orderId": order.id,
        "paymentId": payment.id if payment else None,
        "paymentStatus": payment.status if payment else "pending",
        "state": "payment_pending",
    }
    if payment is None or payment.status != "successful" or order.paid_at is None:
        return result

    job = db.session.scalar(
        select(PdfJob).where(PdfJob.order_id == order.id, PdfJob.generation_profile == "digital")
    )
    result.update({
        "state": "generating",
        "generationStatus": job.status if job else "not_started",
    })
    if job and job.status == "failed":
        result["generationError"] = {
            "code": job.error_code,
            "message": job.error_message or "PDF generation failed. Please retry.",
        }
    if job and job.status == "ready":
        entitlement_id = db.session.scalar(
            select(DownloadEntitlement.id)
            .where(
                DownloadEntitlement.user_id == user_id,
                DownloadEntitlement.pdf_order_id == order.id,
                DownloadEntitlement.revoked_at.is_(None),
            )
            .order_by(DownloadEntitlement.created_at.desc())
        )
        if entitlement_id:
            result.update({"state": "ready", "downloadId": entitlement_id})
    return result


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


def retry_print_order_pdf(order_id: str, user_id: str) -> dict[str, Any]:
    print_order = db.session.scalar(
        select(PrintOrder).where(PrintOrder.id == order_id, PrintOrder.user_id == user_id).with_for_update()
    )
    if print_order is None:
        raise NotFound("Print order was not found.")
    if print_order.paid_at is None or print_order.status not in {"payment_confirmed", "processing"}:
        raise ConflictError("The print PDF can be retried only for a paid order that has not been printed.")
    pdf_order = db.session.scalar(
        select(PdfOrder).where(PdfOrder.idempotency_key == f"print-free:{print_order.id}").with_for_update()
    )
    if pdf_order is None:
        raise ConflictError("The complimentary PDF for this print order is not available.")
    job = db.session.scalar(
        select(PdfJob).where(
            PdfJob.order_id == pdf_order.id,
            PdfJob.generation_profile == "print",
        )
    )
    if job is None or job.status != "failed":
        raise ConflictError("The print PDF is not in a failed state.")
    project = db.session.get(UserProject, print_order.project_id)
    revision = db.session.get(ProjectRevision, print_order.project_revision_id)
    if project is None or revision is None:
        raise ConflictError("The print order's saved project revision is unavailable.")
    replacement_ids = _photo_replacements_only(revision.document, project.document)
    if not replacement_ids:
        raise ConflictError("Replace the low-resolution photo before retrying the print PDF.")
    available_replacements = set(db.session.scalars(
        select(ProjectAsset.id).where(
            ProjectAsset.project_id == project.id,
            ProjectAsset.id.in_(replacement_ids),
        )
    ).all())
    if available_replacements != replacement_ids:
        raise ConflictError("A replacement photo is not available in this project.")
    job, dispatch = queue_pdf_generation(pdf_order, "print", refresh_current_document=True)
    if print_order.project_revision_id != pdf_order.project_revision_id:
        print_order.project_revision_id = pdf_order.project_revision_id
        db.session.add(OrderStatusHistory(
            print_order_id=print_order.id,
            status=print_order.status,
            note="Customer replaced a photo and requested a print PDF retry; only the photo asset changed.",
        ))
        db.session.commit()
    if dispatch:
        try:
            from memorybook.tasks.dispatch import dispatch_pdf_generation

            dispatch_pdf_generation(job.id)
        except Exception as failure:
            db.session.rollback()
            failed_job = db.session.get(PdfJob, job.id)
            if failed_job is not None:
                failed_job.status = "failed"
                failed_job.error_code = "queue_unavailable"
                failed_job.error_message = "The PDF worker could not be reached. Please retry."
                db.session.commit()
            from memorybook.errors import ServiceUnavailableError

            raise ServiceUnavailableError("PDF generation is temporarily unavailable. Please retry.") from failure
    return serialize_pdf_job(job)


def _photo_replacements_only(saved_document: dict, current_document: dict) -> set[str]:
    saved = deepcopy(saved_document)
    current = deepcopy(current_document)
    saved.pop("assets", None)
    current.pop("assets", None)
    changed_asset_ids: set[str] = set()
    saved_pages = {page.get("id"): page for page in saved.get("pages", []) if isinstance(page, dict)}
    current_pages = {page.get("id"): page for page in current.get("pages", []) if isinstance(page, dict)}
    if saved_pages.keys() != current_pages.keys():
        return set()
    for page_id, saved_page in saved_pages.items():
        current_page = current_pages[page_id]
        saved_elements = {item.get("id"): item for item in saved_page.get("elements", []) if isinstance(item, dict)}
        current_elements = {item.get("id"): item for item in current_page.get("elements", []) if isinstance(item, dict)}
        if saved_elements.keys() != current_elements.keys():
            return set()
        for element_id, saved_element in saved_elements.items():
            current_element = current_elements[element_id]
            old_asset = saved_element.get("assetId")
            new_asset = current_element.get("assetId")
            if saved_element.get("type") == current_element.get("type") == "image" and old_asset != new_asset:
                if not isinstance(new_asset, str) or not new_asset:
                    return set()
                changed_asset_ids.add(new_asset)
                current_element["assetId"] = old_asset
    saved_front = ((saved.get("cover") or {}).get("design") or {}).get("front")
    current_front = ((current.get("cover") or {}).get("design") or {}).get("front")
    if isinstance(saved_front, dict) and isinstance(current_front, dict):
        old_asset = saved_front.get("photoAssetId")
        new_asset = current_front.get("photoAssetId")
        if old_asset != new_asset:
            if not isinstance(new_asset, str) or not new_asset:
                return set()
            changed_asset_ids.add(new_asset)
            current_front["photoAssetId"] = old_asset
    return changed_asset_ids if changed_asset_ids and saved == current else set()


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
    assets_by_id = {asset.id: asset for asset in project_assets}
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
    try:
        pdf_bytes, details = render_project_pdf(
            document,
            asset_contents,
            profile,
            print_specification=print_specification,
            minimum_print_dpi=int(_app_config("PDF_MIN_PRINT_DPI", 300)),
            configured_font_directory=_app_config("PDF_FONT_DIR", None),
            maximum_output_bytes=int(_app_config("PDF_MAX_OUTPUT_BYTES", 100 * 1024 * 1024)),
        )
    except PdfRenderError as failure:
        if failure.code == "low_resolution_image":
            asset = assets_by_id.get(failure.asset_id) if failure.asset_id else None
            photo_name = asset.original_filename if asset and asset.original_filename else "selected photo"
            page_label = failure.page_label or "the selected page"
            raise PdfRenderError(
                failure.code,
                f'Photo "{photo_name}" on page "{page_label}" is below the required '
                f'{int(_app_config("PDF_MIN_PRINT_DPI", 300))} DPI for print. Replace the photo and retry.',
                retryable=failure.retryable,
                asset_id=failure.asset_id,
                page_label=failure.page_label,
            ) from failure
        raise
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
            max_downloads=None,
            expires_at=None,
        )
        db.session.add(entitlement)
    else:
        entitlement.max_downloads = None
        entitlement.expires_at = None
    job.status = "ready"
    job.finished_at = datetime.now(UTC)
    job.error_code = None
    job.error_message = None
    if profile == "digital":
        queue_order_event(
            order.user_id,
            f"pdf_ready:{order.id}:{profile}",
            "pdf",
            "Your PDF is ready to download",
            "Your PDF is ready to download.",
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
    if entitlement.revoked_at is not None:
        raise ConflictError("This download entitlement has been revoked.")
    payment = db.session.scalar(
        select(Payment).where(Payment.pdf_order_id == entitlement.pdf_order_id)
    )
    if payment is None or payment.status != "successful":
        if payment and payment.status == "pending":
            raise ConflictError(
                "PDF payment is still pending.",
                error_code="PDF_PAYMENT_PENDING",
            )
        raise ConflictError(
            "This PDF has not been purchased.",
            error_code="PDF_NOT_PURCHASED",
        )
    order = db.session.get(PdfOrder, entitlement.pdf_order_id)
    if order is None or order.paid_at is None:
        raise ConflictError(
            "This PDF has not been purchased.",
            error_code="PDF_NOT_PURCHASED",
        )
    entitlement.max_downloads = None
    entitlement.expires_at = None
    generated_file = (
        db.session.get(GeneratedFile, entitlement.generated_file_id)
        if entitlement.generated_file_id
        else None
    )
    if generated_file is None:
        job = db.session.scalar(
            select(PdfJob).where(
                PdfJob.order_id == entitlement.pdf_order_id,
                PdfJob.generation_profile == "digital",
            )
        )
        if job is None or job.status != "ready":
            raise ConflictError(
                "The PDF is being generated and is not ready for download.",
                error_code="PDF_GENERATING",
            )
        raise ConflictError("The generated PDF is not ready for download.", error_code="PDF_GENERATING")
    storage = get_asset_storage()
    url = storage.private_download_url(generated_file.storage_key)
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
        "fileName": f"{_safe_filename(order.order_number)}-{generated_file.generation_profile}.pdf",
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
