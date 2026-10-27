from memorybook import create_app

app = create_app()
celery = app.extensions.get("celery")
