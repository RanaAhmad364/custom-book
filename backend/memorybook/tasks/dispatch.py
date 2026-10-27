from __future__ import annotations

from flask import current_app


def dispatch_pdf_generation(pdf_job_id: str) -> None:
    if current_app.config["BACKGROUND_JOB_BACKEND"] == "celery":
        current_app.extensions["celery"].send_task("memorybook.generate_pdf", args=[pdf_job_id])
        return
    current_app.extensions["background_jobs"].enqueue("generate_pdf", pdf_job_id, max_attempts=3)


def dispatch_email_log(email_log_id: str, *, admin: bool) -> None:
    if current_app.config["BACKGROUND_JOB_BACKEND"] == "celery":
        task_name = "memorybook.send_admin_event_email" if admin else "memorybook.send_notification_email"
        current_app.extensions["celery"].send_task(task_name, args=[email_log_id])
        return
    job_type = "send_admin_email" if admin else "send_notification_email"
    current_app.extensions["background_jobs"].enqueue(
        job_type,
        email_log_id,
        max_attempts=3 if admin else 4,
    )
