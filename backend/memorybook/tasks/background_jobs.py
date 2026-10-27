from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from typing import Callable

from flask import Flask
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from memorybook.extensions import db
from memorybook.models import BackgroundJob

JobHandler = Callable[[str, int, int], object]


class PermanentJobError(Exception):
    """Signals that retrying a background task cannot succeed."""


class BackgroundJobRunner:
    def __init__(self, app: Flask) -> None:
        self.app = app
        self._handlers: dict[str, JobHandler] = {
            "send_admin_email": self._send_admin_email,
            "send_notification_email": self._send_notification_email,
            "generate_pdf": self._generate_pdf,
            "cleanup_expired_auth": self._cleanup_expired_auth,
        }
        self._executor: ThreadPoolExecutor | None = None
        self._poll_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._submitted: set[str] = set()

    def start(self) -> None:
        if self.app.testing:
            return
        with self._lock:
            if self._poll_thread and self._poll_thread.is_alive():
                return
            self._executor = ThreadPoolExecutor(
                max_workers=int(self.app.config["BACKGROUND_JOB_WORKERS"]),
                thread_name_prefix="memorybook-job",
            )
            self._stop.clear()
            self._poll_thread = threading.Thread(
                target=self._poll,
                name="memorybook-job-poller",
                daemon=True,
            )
            self._poll_thread.start()

    def enqueue(
        self,
        job_type: str,
        reference_id: str,
        *,
        max_attempts: int = 3,
        run_after: datetime | None = None,
    ) -> BackgroundJob:
        if job_type not in self._handlers:
            raise ValueError(f"Unsupported in-process job type: {job_type}")
        with self.app.app_context():
            with Session(db.engine) as session:
                job = session.scalar(
                    select(BackgroundJob).where(
                        BackgroundJob.job_type == job_type,
                        BackgroundJob.reference_id == reference_id,
                    )
                )
                if job is None:
                    job = BackgroundJob(
                        job_type=job_type,
                        reference_id=reference_id,
                        status="queued",
                        max_attempts=max_attempts,
                        run_after=run_after or datetime.now(UTC),
                    )
                    session.add(job)
                    try:
                        session.commit()
                    except IntegrityError:
                        session.rollback()
                        job = session.scalar(
                            select(BackgroundJob).where(
                                BackgroundJob.job_type == job_type,
                                BackgroundJob.reference_id == reference_id,
                            )
                        )
                        if job is None:
                            raise
                elif job.status == "failed" or (job_type == "generate_pdf" and job.status == "completed"):
                    job.status = "queued"
                    job.attempt_count = 0
                    job.max_attempts = max_attempts
                    job.run_after = run_after or datetime.now(UTC)
                    job.started_at = None
                    job.finished_at = None
                    job.error_message = None
                    session.commit()
                session.refresh(job)
                session.expunge(job)
        self.start()
        self._wake.set()
        return job

    def retry_failed(self, *, limit: int = 100) -> int:
        now = datetime.now(UTC)
        with self.app.app_context():
            with Session(db.engine) as session:
                jobs = session.scalars(
                    select(BackgroundJob)
                    .where(BackgroundJob.status == "failed")
                    .order_by(BackgroundJob.updated_at)
                    .limit(limit)
                ).all()
                for job in jobs:
                    job.status = "queued"
                    job.attempt_count = 0
                    job.run_after = now
                    job.started_at = None
                    job.finished_at = None
                    job.error_message = None
                    if job.job_type == "generate_pdf":
                        from memorybook.models import PdfJob

                        pdf_job = session.get(PdfJob, job.reference_id)
                        if pdf_job is not None:
                            pdf_job.status = "queued"
                            pdf_job.error_code = None
                            pdf_job.error_message = None
                            pdf_job.started_at = None
                            pdf_job.finished_at = None
                    elif job.job_type in {"send_admin_email", "send_notification_email"}:
                        from memorybook.models import EmailLog

                        email_log = session.get(EmailLog, job.reference_id)
                        if email_log is not None:
                            email_log.status = "queued"
                            email_log.error_message = None
                count = len(jobs)
                session.commit()
        if count:
            self.start()
            self._wake.set()
        return count

    def _poll(self) -> None:
        while not self._stop.is_set():
            try:
                self._schedule_daily_cleanup()
                self._submit_ready_jobs()
            except Exception:
                self.app.logger.exception("Background job polling failed.")
            self._wake.wait(timeout=1)
            self._wake.clear()

    def _schedule_daily_cleanup(self) -> None:
        today = date.today().isoformat()
        try:
            self._insert_scheduled_job("cleanup_expired_auth", today, datetime.now(UTC))
        except Exception:
            self.app.logger.exception("Could not schedule daily expired-auth cleanup.")

    def _insert_scheduled_job(self, job_type: str, reference_id: str, run_after: datetime) -> None:
        with self.app.app_context():
            with Session(db.engine) as session:
                exists = session.scalar(
                    select(BackgroundJob.id).where(
                        BackgroundJob.job_type == job_type,
                        BackgroundJob.reference_id == reference_id,
                    )
                )
                if exists:
                    return
                session.add(BackgroundJob(
                    job_type=job_type,
                    reference_id=reference_id,
                    run_after=run_after,
                    max_attempts=1,
                ))
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()

    def _submit_ready_jobs(self) -> None:
        with self.app.app_context():
            with Session(db.engine) as session:
                job_ids = session.scalars(
                    select(BackgroundJob.id)
                    .where(
                        BackgroundJob.status == "queued",
                        BackgroundJob.run_after <= datetime.now(UTC),
                    )
                    .order_by(BackgroundJob.created_at)
                    .limit(100)
                ).all()
        for job_id in job_ids:
            with self._lock:
                if job_id in self._submitted or self._executor is None:
                    continue
                self._submitted.add(job_id)
                executor = self._executor
            executor.submit(self._run_job, job_id)

    def _run_job(self, job_id: str) -> None:
        try:
            with self.app.app_context():
                job = self._claim(job_id)
                if job is None:
                    return
                try:
                    self._handlers[job.job_type](job.reference_id, job.attempt_count, job.max_attempts)
                except PermanentJobError as failure:
                    self._finish(job_id, status="failed", error=str(failure))
                except Exception as failure:
                    retry = job.attempt_count < job.max_attempts
                    run_after = datetime.now(UTC) + timedelta(seconds=min(2 ** job.attempt_count, 60))
                    self._finish(
                        job_id,
                        status="queued" if retry else "failed",
                        error=str(failure)[:1000] or type(failure).__name__,
                        run_after=run_after if retry else None,
                    )
                    if retry:
                        self.app.logger.warning(
                            "Background job %s failed on attempt %s; retry scheduled.",
                            job_id,
                            job.attempt_count,
                            exc_info=True,
                        )
                    else:
                        self.app.logger.exception("Background job %s failed permanently.", job_id)
                else:
                    self._finish(job_id, status="completed")
        except Exception:
            self.app.logger.exception("Background job worker failed for job %s.", job_id)
        finally:
            with self._lock:
                self._submitted.discard(job_id)
            self._wake.set()

    def _claim(self, job_id: str) -> BackgroundJob | None:
        with Session(db.engine) as session:
            result = session.execute(
                update(BackgroundJob)
                .where(BackgroundJob.id == job_id, BackgroundJob.status == "queued")
                .values(
                    status="running",
                    attempt_count=BackgroundJob.attempt_count + 1,
                    started_at=datetime.now(UTC),
                    finished_at=None,
                    error_message=None,
                )
            )
            if result.rowcount != 1:
                session.rollback()
                return None
            session.commit()
            job = session.get(BackgroundJob, job_id)
            if job is not None:
                session.expunge(job)
            return job

    def _finish(
        self,
        job_id: str,
        *,
        status: str,
        error: str | None = None,
        run_after: datetime | None = None,
    ) -> None:
        with Session(db.engine) as session:
            job = session.get(BackgroundJob, job_id)
            if job is None:
                return
            job.status = status
            job.error_message = error
            job.run_after = run_after or job.run_after
            job.finished_at = datetime.now(UTC) if status in {"completed", "failed"} else None
            session.commit()

    @staticmethod
    def _send_admin_email(reference_id: str, *_attempts: int) -> None:
        from memorybook.tasks.email_delivery import deliver_email_log

        deliver_email_log(reference_id)

    @staticmethod
    def _send_notification_email(reference_id: str, *_attempts: int) -> None:
        from memorybook.tasks.email_delivery import deliver_email_log

        deliver_email_log(reference_id)

    @staticmethod
    def _generate_pdf(reference_id: str, attempt: int, maximum: int) -> None:
        from memorybook.tasks.pdf_generation import generate_pdf_in_process

        generate_pdf_in_process(reference_id, attempt, maximum)

    @staticmethod
    def _cleanup_expired_auth(*_job_details: str | int) -> None:
        from memorybook.models import EmailVerification, PasswordResetToken

        cutoff = datetime.now(UTC) - timedelta(days=30)
        with Session(db.engine) as session:
            session.query(EmailVerification).filter(
                EmailVerification.expires_at < cutoff,
            ).delete(synchronize_session=False)
            session.query(PasswordResetToken).filter(
                PasswordResetToken.expires_at < cutoff,
            ).delete(synchronize_session=False)
            session.commit()
