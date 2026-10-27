from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO

from flask import Blueprint, abort, send_file
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from sqlalchemy import or_, select

from memorybook.errors import ServiceUnavailableError
from memorybook.extensions import db
from memorybook.integrations.asset_storage import get_asset_storage
from memorybook.models import (
    BookTemplate,
    DownloadEntitlement,
    GeneratedFile,
    Payment,
    PdfOrder,
    ProjectAsset,
    Role,
    UserProject,
    UserRole,
)
from memorybook.repositories.catalog_projects import CatalogRepository
from memorybook.services.auth import AuthService

assets_blueprint = Blueprint("assets", __name__)


def _send_asset(storage, key: str, *, public: bool = False):
    try:
        content = storage.download(key)
        content_type = storage.content_type(key)
    except ServiceUnavailableError:
        abort(404)
    response = send_file(BytesIO(content), mimetype=content_type, max_age=300 if public else 0)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = (
        "public, max-age=300, stale-while-revalidate=600" if public else "private, no-store"
    )
    if key.startswith("generated/pdf/"):
        response.headers["Content-Disposition"] = "attachment; filename=memorybook.pdf"
    return response


@assets_blueprint.get("/public/<path:key>")
def retrieve_public_asset(key: str):
    if not key.startswith("catalog/"):
        abort(404)
    return _send_asset(get_asset_storage(), key, public=True)


@assets_blueprint.get("/private/<token>")
def retrieve_private_asset(token: str):
    storage = get_asset_storage()
    try:
        key = storage.download_token(token)
    except ServiceUnavailableError:
        abort(404)

    verify_jwt_in_request()
    user = AuthService.get_active_user(get_jwt_identity())
    if user is None:
        abort(404)

    authorized = False
    if key.startswith("projects/"):
        authorized = db.session.scalar(
            select(ProjectAsset.id)
            .join(UserProject, UserProject.id == ProjectAsset.project_id)
            .where(
                ProjectAsset.storage_key == key,
                ProjectAsset.original_deleted_at.is_(None),
                UserProject.user_id == user.id,
                UserProject.status != "deleted",
            )
        ) is not None
    elif key.startswith("admin-design/"):
        key_parts = key.split("/", 2)
        is_admin = db.session.scalar(
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user.id, Role.name == "admin")
        ) is not None
        authorized = len(key_parts) == 3 and key_parts[1] == user.id and is_admin
        if not authorized:
            published_designs = db.session.execute(
                CatalogRepository.templates_query().with_only_columns(
                    BookTemplate.published_design_document
                )
                .where(BookTemplate.published_design_document.is_not(None))
            ).scalars()
            authorized = any(
                isinstance(design, dict)
                and any(
                    isinstance(asset, dict) and asset.get("assetKey") == key
                    for asset in design.get("assets", [])
                )
                for design in published_designs
            )
    elif key.startswith("generated/pdf/"):
        now = datetime.now(UTC)
        authorized = db.session.scalar(
            select(DownloadEntitlement.id)
            .join(GeneratedFile, GeneratedFile.id == DownloadEntitlement.generated_file_id)
            .join(PdfOrder, PdfOrder.id == GeneratedFile.pdf_order_id)
            .join(Payment, Payment.pdf_order_id == PdfOrder.id)
            .where(
                DownloadEntitlement.user_id == user.id,
                PdfOrder.user_id == user.id,
                Payment.user_id == user.id,
                GeneratedFile.storage_key == key,
                DownloadEntitlement.revoked_at.is_(None),
                or_(DownloadEntitlement.expires_at.is_(None), DownloadEntitlement.expires_at > now),
                PdfOrder.paid_at.is_not(None),
                Payment.status == "successful",
            )
        ) is not None

    if not authorized:
        abort(404)
    return _send_asset(storage, key)


@assets_blueprint.get("/<token>")
def retrieve_legacy_asset(token: str):
    storage = get_asset_storage()
    try:
        key = storage.download_token(token)
    except ServiceUnavailableError:
        abort(404)
    if not key.startswith("catalog/"):
        abort(404)
    return _send_asset(storage, key, public=True)
