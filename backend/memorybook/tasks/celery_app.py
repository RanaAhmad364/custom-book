from celery import Celery, Task
from flask import Flask


def create_celery(app: Flask) -> Celery:
    celery = Celery(app.import_name)
    celery.conf.update(app.config["CELERY"])

    class FlaskContextTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = FlaskContextTask
    return celery
