from flask import Blueprint, current_app, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from memorybook.extensions import db

health_blueprint = Blueprint("health", __name__)


@health_blueprint.get("/health/live")
def live():
    return jsonify({"status": "ok", "apiVersion": "v1"})


@health_blueprint.get("/health/ready")
def ready():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        current_app.logger.exception("Readiness check could not reach the database.")
        return jsonify({"status": "not_ready", "dependencies": {"database": "unavailable"}}), 503
    return jsonify({"status": "ready", "dependencies": {"database": "available"}})
