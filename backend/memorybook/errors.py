from __future__ import annotations

from uuid import uuid4

from flask import Flask, current_app, g, jsonify
from flask_jwt_extended.exceptions import JWTExtendedException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException


class ValidationError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConflictError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ServiceUnavailableError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _error_response(status: int, code: str, message: str, details: dict | None = None):
    body = {
        "error": {
            "code": code,
            "message": message,
        },
        "requestId": g.get("request_id", str(uuid4())),
    }
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ConflictError)
    def handle_conflict_error(error: ConflictError):
        return _error_response(409, "CONFLICT", error.message, error.details)

    @app.errorhandler(ServiceUnavailableError)
    def handle_service_unavailable(error: ServiceUnavailableError):
        return _error_response(503, "SERVICE_UNAVAILABLE", error.message)

    @app.errorhandler(ValidationError)
    def handle_validation_error(error: ValidationError):
        return _error_response(400, "VALIDATION_ERROR", error.message, error.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return _error_response(error.code or 500, error.name.upper().replace(" ", "_"), error.description)

    @app.errorhandler(JWTExtendedException)
    def handle_jwt_error(error: JWTExtendedException):
        return _error_response(401, "AUTHENTICATION_ERROR", str(error))

    @app.errorhandler(IntegrityError)
    def handle_integrity_error(error: IntegrityError):
        current_app.logger.info("Database constraint rejected the request.")
        return _error_response(409, "CONFLICT", "The requested resource conflicts with existing data.")

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error: SQLAlchemyError):
        current_app.logger.exception("Database operation failed.")
        return _error_response(503, "DATABASE_ERROR", "The database could not complete the request.")

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        current_app.logger.exception("Unhandled request failure.")
        return _error_response(500, "INTERNAL_SERVER_ERROR", "An unexpected server error occurred.")
