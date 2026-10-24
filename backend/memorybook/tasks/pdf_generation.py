from __future__ import annotations

from datetime import UTC, datetime

from flask import current_app

from memorybook.errors import ServiceUnavailableError
from memorybook.extensions import db
from memorybook.models import PdfJob
from memorybook.services.pdf_generation import generate_pdf_job
from memorybook.services.pdf_renderer import PdfRenderError


def register_pdf_generation_task(celery) -> None:
    @celery.task(bind=True, name="memorybook.generate_pdf", max_retries=3)
    def generate_pdf(self, job_id: str) -> dict:
        try:
            return generate_pdf_job(job_id)
        except Exception as failure:
            db.session.rollback()
            job = db.session.get(PdfJob, job_id)
            if job is None:
                current_app.logger.exception("PDF generation failed because the job disappeared.")
                raise
            retryable = not isinstance(failure, PdfRenderError) or failure.retryable
            retry_limit_reached = self.request.retries >= self.max_retries
            job.status = "failed" if not retryable or retry_limit_reached else "queued"
            job.finished_at = datetime.now(UTC) if job.status == "failed" else None
            job.error_code = failure.code if isinstance(failure, PdfRenderError) else (
                "storage_unavailable" if isinstance(failure, ServiceUnavailableError) else "generation_failed"
            )
            job.error_message = (
                str(failure)[:500]
                if isinstance(failure, (PdfRenderError, ServiceUnavailableError))
                else "PDF generation failed unexpectedly. Please retry."
            )
            db.session.commit()
            if retryable and not retry_limit_reached:
                current_app.logger.warning(
                    "PDF generation will retry for job %s (attempt %s).",
                    job_id,
                    self.request.retries + 1,
                )
                raise self.retry(exc=failure, countdown=min(2 ** self.request.retries, 30))
            current_app.logger.exception("PDF generation failed permanently for job %s.", job_id)
            raise
