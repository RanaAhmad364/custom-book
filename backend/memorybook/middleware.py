from __future__ import annotations

import uuid
import re

from flask import Flask, g, request


def register_middleware(app: Flask) -> None:
    @app.before_request
    def assign_request_id() -> None:
        supplied = request.headers.get("X-Request-ID", "").strip()
        g.request_id = supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", supplied) else str(uuid.uuid4())
        request.request_id = g.request_id

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if app.config["ENVIRONMENT"] == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers["X-Request-ID"] = g.get("request_id", "")
        return response
