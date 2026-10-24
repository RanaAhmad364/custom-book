from __future__ import annotations

from io import BytesIO

from flask import Blueprint, abort, send_file
from flask_jwt_extended import verify_jwt_in_request
from sqlalchemy import select

from memorybook.errors import ServiceUnavailableError
from memorybook.extensions import db
from memorybook.integrations.asset_storage import LocalFilesystemAssetStorage, get_asset_storage
from memorybook.models import ProjectAsset, UserProject
from memorybook.services.auth import AuthService

assets_blueprint = Blueprint("assets", __name__)


@assets_blueprint.get("/<token>")
def retrieve_asset(token: str):
    storage = get_asset_storage()
    if not isinstance(storage, LocalFilesystemAssetStorage):
        raise ServiceUnavailableError("Local asset retrieval is not enabled.")
    try:
        key = storage.download_token(token)
    except ServiceUnavailableError:
        abort(404)

    if key.startswith("projects/"):
        verify_jwt_in_request()
        from flask_jwt_extended import get_jwt_identity

        user = AuthService.get_active_user(get_jwt_identity())
        if user is None:
            abort(404)
        owns_asset = db.session.scalar(
            select(ProjectAsset.id)
            .join(UserProject, UserProject.id == ProjectAsset.project_id)
            .where(
                ProjectAsset.storage_key == key,
                UserProject.user_id == user.id,
                UserProject.status != "deleted",
            )
        )
        if owns_asset is None:
            abort(404)
    elif not key.startswith(("catalog/", "generated/pdf/")):
        abort(404)

    try:
        content = storage.download(key)
    except ServiceUnavailableError:
        abort(404)
    response = send_file(BytesIO(content), mimetype=storage.content_type(key), max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    return response
