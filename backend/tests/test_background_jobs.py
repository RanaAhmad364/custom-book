from datetime import UTC, datetime, timedelta

from memorybook.models import BackgroundJob


def test_local_job_enqueue_persists_status_without_celery(app):
    runner = app.extensions["background_jobs"]

    job = runner.enqueue("cleanup_expired_auth", "test-run", max_attempts=1)

    assert job.status == "queued"
    assert job.job_type == "cleanup_expired_auth"
    with app.app_context():
        persisted = BackgroundJob.query.filter_by(id=job.id).one()
        assert persisted.reference_id == "test-run"
        assert persisted.attempt_count == 0


def test_failed_local_jobs_can_be_retried(app):
    runner = app.extensions["background_jobs"]
    with app.app_context():
        job = BackgroundJob(
            job_type="cleanup_expired_auth",
            reference_id="failed-run",
            status="failed",
            attempt_count=1,
            max_attempts=1,
            run_after=datetime.now(UTC) - timedelta(minutes=1),
            finished_at=datetime.now(UTC),
            error_message="temporary database issue",
        )
        from memorybook.extensions import db

        db.session.add(job)
        db.session.commit()
        job_id = job.id

    assert runner.retry_failed(limit=10) == 1
    with app.app_context():
        retried = BackgroundJob.query.filter_by(id=job_id).one()
        assert retried.status == "queued"
        assert retried.attempt_count == 0
        assert retried.error_message is None


def test_job_failure_is_recorded_and_a_later_attempt_can_complete(app):
    runner = app.extensions["background_jobs"]
    job = runner.enqueue("cleanup_expired_auth", "retry-run", max_attempts=2)

    def fail_once(_reference_id, _attempt, _maximum):
        raise RuntimeError("temporary failure")

    runner._handlers["cleanup_expired_auth"] = fail_once
    runner._run_job(job.id)
    with app.app_context():
        failed_attempt = BackgroundJob.query.filter_by(id=job.id).one()
        assert failed_attempt.status == "queued"
        assert failed_attempt.attempt_count == 1
        assert failed_attempt.error_message == "temporary failure"
        failed_attempt.run_after = datetime.now(UTC) - timedelta(seconds=1)
        from memorybook.extensions import db

        db.session.commit()

    runner._handlers["cleanup_expired_auth"] = lambda *_args: None
    runner._run_job(job.id)
    with app.app_context():
        completed = BackgroundJob.query.filter_by(id=job.id).one()
        assert completed.status == "completed"
        assert completed.attempt_count == 2
        assert completed.error_message is None
