from __future__ import annotations

from sqlalchemy import select

from memorybook.extensions import db
from memorybook.models import EmailLog, Notification


def queue_order_event(
    user_id: str,
    event_key: str,
    category: str,
    title: str,
    message: str,
    target_url: str | None = None,
) -> None:
    recipient_key = f"{event_key}:user:{user_id}"
    existing = db.session.scalar(select(Notification.id).where(Notification.event_key == recipient_key))
    if existing:
        return
    notification = Notification(
        user_id=user_id,
        category=category,
        title=title,
        message=message,
        target_url=target_url,
        data={"event": event_key},
        event_key=recipient_key,
    )
    email = EmailLog(
        user_id=user_id,
        recipient_email="",
        template_key=event_key.split(":", 1)[0],
        status="queued",
        event_key=recipient_key,
    )
    from memorybook.models import User

    email.recipient_email = db.session.scalar(select(User.email).where(User.id == user_id)) or ""
    db.session.add_all([notification, email])
    db.session.info.setdefault("memorybook_notification_email_jobs", []).append((email, title, message))
