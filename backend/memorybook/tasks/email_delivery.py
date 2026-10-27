from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from memorybook.extensions import db
from memorybook.integrations.email import email_delivery_is_configured, send_email
from memorybook.models import EmailLog, Notification


def deliver_email_log(email_log_id: str) -> None:
    email_log = db.session.get(EmailLog, email_log_id)
    if email_log is None:
        raise LookupError("Queued email log was not found.")
    notification = db.session.scalar(
        select(Notification).where(Notification.event_key == email_log.event_key)
    )
    if notification is None:
        raise LookupError("The notification for this queued email was not found.")
    if not email_delivery_is_configured():
        email_log.status = "failed"
        email_log.error_message = "Email delivery is not configured."
        db.session.commit()
        return
    email_log.status = "sending"
    db.session.commit()
    try:
        send_email(email_log.recipient_email, notification.title, notification.message)
    except Exception as failure:
        db.session.rollback()
        email_log = db.session.get(EmailLog, email_log_id)
        if email_log is not None:
            email_log.status = "failed"
            email_log.error_message = str(failure)[:1000] or type(failure).__name__
            db.session.commit()
        raise
    email_log = db.session.get(EmailLog, email_log_id)
    if email_log is not None:
        email_log.status = "sent"
        email_log.sent_at = datetime.now(UTC)
        email_log.error_message = None
        db.session.commit()
