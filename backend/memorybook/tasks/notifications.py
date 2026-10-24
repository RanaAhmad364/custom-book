from __future__ import annotations

from datetime import UTC, datetime

from memorybook.errors import ServiceUnavailableError
from memorybook.extensions import db
from memorybook.integrations.email import send_email
from memorybook.models import EmailLog


def register_notification_task(celery) -> None:
    @celery.task(
        bind=True,
        name="memorybook.send_notification_email",
        max_retries=4,
    )
    def send_notification_email(self, email_log_id: str, subject: str, body: str) -> None:
        email_log = db.session.get(EmailLog, email_log_id)
        if email_log is None:
            raise LookupError("Notification email log was not found.")
        try:
            send_email(email_log.recipient_email, subject, body)
        except ServiceUnavailableError as failure:
            email_log.status = "failed"
            email_log.error_message = str(failure)[:1000]
            db.session.commit()
            if self.request.retries < self.max_retries:
                raise self.retry(exc=failure, countdown=min(2 ** self.request.retries, 60))
            raise
        email_log.status = "sent"
        email_log.sent_at = datetime.now(UTC)
        email_log.error_message = None
        db.session.commit()
