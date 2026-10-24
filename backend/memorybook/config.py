from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

BASE_DIRECTORY = Path(__file__).resolve().parent.parent


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "15")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_TOKEN_DAYS", "30")))
    JWT_TOKEN_LOCATION = ["cookies", "headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_METHODS = ["POST", "PUT", "PATCH", "DELETE"]
    JWT_ACCESS_COOKIE_PATH = "/api/"
    JWT_REFRESH_COOKIE_PATH = "/api/v1/auth/refresh"
    JWT_ACCESS_CSRF_COOKIE_PATH = "/"
    JWT_REFRESH_CSRF_COOKIE_PATH = "/"
    JWT_COOKIE_SECURE = os.getenv("JWT_COOKIE_SECURE", "false").lower() == "true"
    JWT_COOKIE_SAMESITE = os.getenv("JWT_COOKIE_SAMESITE", "Lax")
    JWT_COOKIE_DOMAIN = os.getenv("JWT_COOKIE_DOMAIN") or None
    AUTH_OTP_TTL_MINUTES = int(os.getenv("AUTH_OTP_TTL_MINUTES", "10"))
    AUTH_RESET_TTL_MINUTES = int(os.getenv("AUTH_RESET_TTL_MINUTES", "30"))
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    AUTH_EMAIL_MODE = os.getenv("AUTH_EMAIL_MODE", "smtp").strip().lower()
    PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:5173")
    PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "")
    PAYMENT_DEFAULT_CURRENCY = os.getenv("PAYMENT_DEFAULT_CURRENCY", "PKR").upper()
    PAYMENT_PRIMARY_GATEWAY = os.getenv("PAYMENT_PRIMARY_GATEWAY", "payfast").strip().lower()
    PAYFAST_ENABLED = os.getenv("PAYFAST_ENABLED", "false").lower() == "true"
    PAYFAST_MODE = os.getenv("PAYFAST_MODE", "sandbox").strip().lower()
    PAYFAST_MERCHANT_ID = os.getenv("PAYFAST_MERCHANT_ID")
    PAYFAST_MERCHANT_SECRET = os.getenv("PAYFAST_MERCHANT_SECRET")
    PAYFAST_API_BASE_URL = os.getenv("PAYFAST_API_BASE_URL")
    PAYFAST_CONTRACT_VERIFIED = os.getenv("PAYFAST_CONTRACT_VERIFIED", "false").lower() == "true"
    PAYFAST_PAYMENT_METHODS = os.getenv("PAYFAST_PAYMENT_METHODS", "")
    JAZZCASH_ENABLED = os.getenv("JAZZCASH_ENABLED", "false").lower() == "true"
    JAZZCASH_MODE = os.getenv("JAZZCASH_MODE", "sandbox").strip().lower()
    JAZZCASH_CHECKOUT_CONTRACT_VERIFIED = (
        os.getenv("JAZZCASH_CHECKOUT_CONTRACT_VERIFIED", "false").lower() == "true"
    )
    JAZZCASH_CALLBACK_CONTRACT_VERIFIED = (
        os.getenv("JAZZCASH_CALLBACK_CONTRACT_VERIFIED", "false").lower() == "true"
    )
    JAZZCASH_SERVER_INQUIRY_IMPLEMENTED = False
    JAZZCASH_PAYMENT_METHODS = os.getenv("JAZZCASH_PAYMENT_METHODS", "")
    EASYPAISA_ENABLED = os.getenv("EASYPAISA_ENABLED", "false").lower() == "true"
    EASYPAISA_MODE = os.getenv("EASYPAISA_MODE", "sandbox").strip().lower()
    EASYPAISA_STORE_ID = os.getenv("EASYPAISA_STORE_ID")
    EASYPAISA_MERCHANT_SECRET = os.getenv("EASYPAISA_MERCHANT_SECRET")
    STRIPE_ENABLED = os.getenv("STRIPE_ENABLED", "true").lower() == "true"
    STRIPE_PAYMENT_METHODS = os.getenv("STRIPE_PAYMENT_METHODS", "card")
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
    PAYMENT_WEBHOOK_TOLERANCE_SECONDS = int(os.getenv("PAYMENT_WEBHOOK_TOLERANCE_SECONDS", "300"))
    JAZZCASH_API_URL = os.getenv("JAZZCASH_API_URL")
    JAZZCASH_MERCHANT_ID = os.getenv("JAZZCASH_MERCHANT_ID")
    JAZZCASH_PASSWORD = os.getenv("JAZZCASH_PASSWORD")
    JAZZCASH_INTEGRITY_SALT = os.getenv("JAZZCASH_INTEGRITY_SALT")
    JAZZCASH_API_VERSION = os.getenv("JAZZCASH_API_VERSION", "2.0")
    JAZZCASH_TXN_TYPE = os.getenv("JAZZCASH_TXN_TYPE", "MPAY")
    JAZZCASH_REDIRECT_HOSTS = os.getenv(
        "JAZZCASH_REDIRECT_HOSTS",
        "sandbox.jazzcash.com.pk,jazzcash.com.pk",
    )
    PAYMENT_RETURN_URL = os.getenv("PAYMENT_RETURN_URL")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY = {
        "broker_url": REDIS_URL,
        "result_backend": REDIS_URL,
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "task_acks_late": True,
        "worker_prefetch_multiplier": 1,
        "broker_connection_retry_on_startup": True,
    }
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if origin.strip()
    ]
    RATE_LIMIT_STORAGE_URI = os.getenv(
        "RATE_LIMIT_STORAGE_URI",
        os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    )
    RATELIMIT_STORAGE_URI = RATE_LIMIT_STORAGE_URI
    RATELIMIT_DEFAULT = "200 per day; 60 per hour"
    RATELIMIT_HEADERS_ENABLED = True
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ASSET_STORAGE_BACKEND = os.getenv(
        "ASSET_STORAGE_BACKEND",
        "filesystem" if os.getenv("FLASK_ENV", "development").lower() == "development" else "s3",
    ).strip().lower()
    ASSET_LOCAL_DIRECTORY = os.getenv(
        "ASSET_LOCAL_DIRECTORY",
        str(Path.home() / ".memorybook" / "assets"),
    )
    ASSET_S3_ENDPOINT_URL = os.getenv("ASSET_S3_ENDPOINT_URL") or None
    ASSET_S3_REGION = os.getenv("ASSET_S3_REGION", "us-east-1")
    ASSET_S3_BUCKET = os.getenv("ASSET_S3_BUCKET")
    ASSET_S3_ACCESS_KEY_ID = os.getenv("ASSET_S3_ACCESS_KEY_ID")
    ASSET_S3_SECRET_ACCESS_KEY = os.getenv("ASSET_S3_SECRET_ACCESS_KEY")
    ASSET_S3_PRESIGNED_URL_TTL = int(os.getenv("ASSET_S3_PRESIGNED_URL_TTL", "3600"))
    PDF_FONT_DIR = os.getenv("PDF_FONT_DIR") or None
    PDF_MAX_OUTPUT_BYTES = int(os.getenv("PDF_MAX_OUTPUT_BYTES", str(100 * 1024 * 1024)))
    PDF_MIN_PRINT_DPI = int(os.getenv("PDF_MIN_PRINT_DPI", "300"))
    PDF_PRINT_BLEED_INCHES = float(os.getenv("PDF_PRINT_BLEED_INCHES", "0.125"))
    PDF_PRINT_SAFE_MARGIN_INCHES = float(os.getenv("PDF_PRINT_SAFE_MARGIN_INCHES", "0.25"))
    PDF_DOWNLOAD_MAX_COUNT = int(os.getenv("PDF_DOWNLOAD_MAX_COUNT", "5"))
    PDF_DOWNLOAD_TTL_DAYS = int(os.getenv("PDF_DOWNLOAD_TTL_DAYS", "30"))
    ENVIRONMENT = os.getenv("FLASK_ENV", "development").lower()
    MIGRATIONS_DIRECTORY = str(BASE_DIRECTORY / "migrations")


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-only-secret-key-that-is-not-used-outside-testing"
    JWT_SECRET_KEY = "test-only-jwt-secret-that-is-not-used-outside-testing"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    RATE_LIMIT_STORAGE_URI = "memory://"
    RATELIMIT_ENABLED = False
    ENVIRONMENT = "testing"


class ProductionConfig(BaseConfig):
    DEBUG = False
    ENVIRONMENT = "production"
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    JWT_COOKIE_SECURE = True


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def config_for_environment(environment: str | None = None) -> type[BaseConfig]:
    selected = (environment or os.getenv("FLASK_ENV", "development")).lower()
    try:
        return CONFIGS[selected]
    except KeyError as failure:
        raise RuntimeError(f"Unsupported FLASK_ENV: {selected}") from failure
