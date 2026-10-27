from __future__ import annotations

from memorybook.errors import ServiceUnavailableError
from memorybook.tasks.email_delivery import deliver_email_log


def register_notification_task(celery) -> None:
    @celery.task(
        name="memorybook.send_notification_email",
        autoretry_for=(ServiceUnavailableError,),
        retry_backoff=True,
        max_retries=4,
    )
    def send_notification_email(email_log_id: str) -> None:
        deliver_email_log(email_log_id)
