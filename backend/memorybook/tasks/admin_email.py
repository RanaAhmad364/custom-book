from __future__ import annotations

from datetime import UTC, datetime

from memorybook.errors import ServiceUnavailableError
from memorybook.extensions import db
from memorybook.integrations.email import send_email
from memorybook.models import EmailLog


def register_admin_email_task(celery) -> None:
    @celery.task(
        name="memorybook.send_admin_event_email",
        autoretry_for=(ServiceUnavailableError,),
        retry_backoff=True,
        max_retries=3,
    )
    def send_admin_event_email(email_log_id: str, subject: str, body: str) -> None:
        email_log = db.session.get(EmailLog, email_log_id)
        if email_log is None:
            raise LookupError("Admin event email log was not found.")
        try:
            send_email(email_log.recipient_email, subject, body)
        except ServiceUnavailableError as failure:
            email_log.status = "failed"
            email_log.error_message = str(failure)[:1000]
            db.session.commit()
            raise
        email_log.status = "sent"
        email_log.sent_at = datetime.now(UTC)
        email_log.error_message = None
        db.session.commit()
