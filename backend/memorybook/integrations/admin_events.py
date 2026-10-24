from __future__ import annotations

from flask import current_app, has_app_context
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from memorybook.models import (
    EmailLog,
    Notification,
    OrderStatusHistory,
    Payment,
    PdfOrder,
    PrintOrder,
    Role,
    Refund,
    SupportTicket,
    User,
    UserRole,
)


def _queue_admin_event(session: Session, event_key: str, title: str, message: str) -> None:
    seen = session.info.setdefault("memorybook_admin_event_keys", set())
    if event_key in seen:
        return
    seen.add(event_key)
    admin_ids = session.scalars(
        select(UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.name == "admin")
    ).all()
    email_jobs = session.info.setdefault("memorybook_admin_email_jobs", [])
    for admin_id in admin_ids:
        recipient_event_key = f"{event_key}:admin:{admin_id}"
        session.add(Notification(
            user_id=admin_id,
            category="admin_event",
            title=title,
            message=message,
            data={"event": event_key},
            event_key=recipient_event_key,
        ))
        email = EmailLog(
            user_id=admin_id,
            recipient_email=session.scalar(select(User.email).where(User.id == admin_id)),
            template_key=event_key.split(":", 1)[0],
            status="queued",
            event_key=recipient_event_key,
        )
        session.add(email)
        email_jobs.append((email, title, message))


def _before_flush(session: Session, *_args) -> None:
    if not has_app_context():
        return
    for row in tuple(session.new):
        if isinstance(row, PrintOrder):
            _queue_admin_event(session, f"print_order_placed:{row.id}", "Print order placed", f"Print order {row.order_number} has been placed.")
        elif isinstance(row, PdfOrder) and row.paid_at is not None:
            _queue_admin_event(session, f"pdf_purchased:{row.id}", "PDF purchased", f"PDF order {row.order_number} has been paid.")
        elif isinstance(row, SupportTicket):
            _queue_admin_event(session, f"support_ticket:{row.id}", "New support ticket", f"Ticket {row.ticket_number}: {row.subject}")
        elif isinstance(row, Payment):
            _payment_event(session, row)
        elif isinstance(row, Refund) and row.status == "requested":
            _queue_admin_event(
                session,
                f"refund_requested:{row.id}",
                "Refund request received",
                f"A customer requested a refund for payment {row.payment_id}.",
            )
        elif isinstance(row, OrderStatusHistory) and row.status == "cancellation_requested":
            order_number = row.pdf_order_id or row.print_order_id
            _queue_admin_event(session, f"cancellation_requested:{order_number}", "Cancellation requested", f"Cancellation requested for order {order_number}.")
    for row in tuple(session.dirty):
        if isinstance(row, Payment) and inspect(row).attrs.status.history.has_changes():
            _payment_event(session, row)


def _payment_event(session: Session, payment: Payment) -> None:
    status = (payment.status or "").lower()
    order_id = payment.pdf_order_id or payment.print_order_id or payment.id
    if status in {"paid", "succeeded", "successful", "confirmed"}:
        _queue_admin_event(session, f"payment_confirmed:{payment.id}", "Payment confirmed", f"Payment for order {order_id} was confirmed.")
        if payment.pdf_order_id:
            _queue_admin_event(session, f"pdf_purchased:{payment.pdf_order_id}", "PDF purchased", f"PDF order {payment.pdf_order_id} was paid.")
    elif status in {"failed", "declined"}:
        _queue_admin_event(session, f"payment_failed:{payment.id}", "Payment failed", f"Payment for order {order_id} failed.")


def _after_commit(session: Session) -> None:
    jobs = session.info.pop("memorybook_admin_email_jobs", [])
    user_jobs = session.info.pop("memorybook_notification_email_jobs", [])
    session.info.pop("memorybook_admin_event_keys", None)
    if not jobs and not user_jobs or not has_app_context():
        return
    celery = current_app.extensions.get("celery")
    if celery is None:
        current_app.logger.error("Event emails could not be queued because Celery is unavailable.")
        return
    for email_id, subject, body in jobs:
        try:
            celery.send_task(
                "memorybook.send_admin_event_email",
                args=[email_id, subject, body],
            )
        except Exception:
            current_app.logger.exception("Could not queue an admin event email.")
    for email_id, subject, body in user_jobs:
        try:
            celery.send_task(
                "memorybook.send_notification_email",
                args=[email_id, subject, body],
            )
        except Exception:
            current_app.logger.exception("Could not queue a user notification email.")


def _after_flush_postexec(session: Session, *_args) -> None:
    for job_key in ("memorybook_admin_email_jobs", "memorybook_notification_email_jobs"):
        jobs = session.info.get(job_key)
        if jobs:
            session.info[job_key] = [
                (email.id, subject, body) if isinstance(email, EmailLog) else (email, subject, body)
                for email, subject, body in jobs
            ]


def _after_rollback(session: Session) -> None:
    session.info.pop("memorybook_admin_email_jobs", None)
    session.info.pop("memorybook_notification_email_jobs", None)
    session.info.pop("memorybook_admin_event_keys", None)


def register_admin_event_listeners() -> None:
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
    if not event.contains(Session, "after_commit", _after_commit):
        event.listen(Session, "after_commit", _after_commit)
    if not event.contains(Session, "after_flush_postexec", _after_flush_postexec):
        event.listen(Session, "after_flush_postexec", _after_flush_postexec)
    if not event.contains(Session, "after_rollback", _after_rollback):
        event.listen(Session, "after_rollback", _after_rollback)
