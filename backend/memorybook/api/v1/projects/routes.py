from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from memorybook.errors import ConflictError, ValidationError
from memorybook.extensions import db, limiter
from memorybook.models import ProjectAsset, ProjectPage, ProjectRevision, UserProject
from memorybook.permissions import active_user_required, get_authenticated_user
from memorybook.repositories.catalog_projects import CatalogRepository
from memorybook.schemas.catalog_projects import (
    AssetMetadataSchema,
    ProjectCreateSchema,
    ProjectPageSchema,
    ProjectUpdateSchema,
)
from memorybook.services.catalog_projects import (
    create_project,
    create_revision,
    delete_asset,
    delete_page,
    delete_project,
    duplicate_project,
    get_asset_storage,
    restore_revision,
    save_page,
    serialize_asset,
    serialize_project,
    serialize_revision,
    update_project,
    upload_asset,
)

projects_blueprint = Blueprint("projects", __name__)


def _json_body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("A JSON object is required.")
    return body


def _owned_project(project_id: str, *, lock: bool = False) -> UserProject:
    project = CatalogRepository.owned_project(project_id, get_authenticated_user().id, lock=lock)
    if project is None:
        from werkzeug.exceptions import NotFound

        raise NotFound("Project was not found.")
    return project


def _expected_version(*, required: bool = True) -> int | None:
    value = request.headers.get("If-Match")
    if value is None:
        if required:
            return None
        return None
    value = value.strip().removeprefix("W/").strip('"')
    try:
        version = int(value)
    except ValueError as failure:
        raise ValidationError("If-Match must contain a project version.", {"If-Match": "invalid"}) from failure
    if version < 1:
        raise ValidationError("If-Match must contain a positive project version.", {"If-Match": "invalid"})
    return version


def _require_precondition():
    version = _expected_version()
    if version is None:
        return None, (jsonify({
            "error": {
                "code": "PRECONDITION_REQUIRED",
                "message": "Send the current project version in the If-Match header.",
            }
        }), 428)
    return version, None


def _project_response(project: UserProject, *, include_document: bool = True, status: int = 200):
    payload = serialize_project(project, get_authenticated_user())
    if not include_document:
        payload.pop("document", None)
    response = jsonify({"project": payload})
    response.status_code = status
    response.headers["ETag"] = f'"{project.version}"'
    return response


def _pagination(page: int, per_page: int, total: int) -> dict:
    return {"page": page, "perPage": per_page, "totalItems": total, "totalPages": (total + per_page - 1) // per_page}


@projects_blueprint.post("")
@active_user_required
def create():
    project = create_project(get_authenticated_user(), ProjectCreateSchema.load(_json_body()))
    return _project_response(project, status=201)


@projects_blueprint.get("")
@active_user_required
def list_projects():
    args = request.args
    page, per_page = 1, 24
    try:
        page = int(args.get("page", "1"))
        per_page = int(args.get("perPage", "24"))
    except (TypeError, ValueError) as failure:
        raise ValidationError("Pagination values must be integers.", {"pagination": "invalid"}) from failure
    if page < 1 or per_page < 1 or per_page > 100:
        raise ValidationError("Page must be positive and perPage must be between 1 and 100.", {"pagination": "out_of_range"})
    search = args.get("search", "").strip()[:120]
    sort = args.get("sort", "updated")
    if sort not in {"updated", "created", "title"}:
        raise ValidationError("Unsupported project sort option.", {"sort": "invalid"})
    query = select(UserProject).where(
        UserProject.user_id == get_authenticated_user().id,
        UserProject.status != "deleted",
    )
    if args.get("status"):
        statuses = {part.strip() for part in args["status"].split(",") if part.strip()}
        if not statuses.issubset({"draft", "in_progress", "completed"}):
            raise ValidationError("Project status filter is invalid.", {"status": "invalid"})
        query = query.where(UserProject.status.in_(statuses))
    if search:
        query = query.where(UserProject.title.ilike(f"%{search}%"))
    total = db.session.scalar(select(db.func.count()).select_from(query.order_by(None).subquery())) or 0
    ordering = {
        "updated": (UserProject.updated_at.desc(), UserProject.id),
        "created": (UserProject.created_at.desc(), UserProject.id),
        "title": (UserProject.title.asc(), UserProject.id),
    }[sort]
    projects = db.session.scalars(query.order_by(*ordering).offset((page - 1) * per_page).limit(per_page)).all()
    items = [serialize_project(project, get_authenticated_user()) for project in projects]
    for item in items:
        item.pop("document", None)
    return jsonify({"items": items, "pagination": _pagination(page, per_page, total)})


@projects_blueprint.get("/<string:project_id>")
@active_user_required
def get_project(project_id: str):
    return _project_response(_owned_project(project_id))


@projects_blueprint.post("/<string:project_id>/duplicate")
@active_user_required
def duplicate(project_id: str):
    source = _owned_project(project_id)
    project = duplicate_project(source, get_authenticated_user())
    return _project_response(project, status=201)


@projects_blueprint.patch("/<string:project_id>")
@active_user_required
def patch_project(project_id: str):
    expected, error_response = _require_precondition()
    if error_response:
        return error_response
    project = _owned_project(project_id, lock=True)
    data = ProjectUpdateSchema.load(_json_body())
    return _project_response(update_project(project, data, expected))


@projects_blueprint.delete("/<string:project_id>")
@active_user_required
def remove_project(project_id: str):
    expected, error_response = _require_precondition()
    if error_response:
        return error_response
    project = _owned_project(project_id, lock=True)
    if expected != project.version:
        raise ConflictError(
            "This project changed on another session. Reload the latest project before deleting.",
            {"expectedVersion": expected, "currentVersion": project.version},
        )
    delete_project(project, expected)
    return "", 204


@projects_blueprint.post("/<string:project_id>/pages")
@active_user_required
def create_page(project_id: str):
    expected, error_response = _require_precondition()
    if error_response:
        return error_response
    project = _owned_project(project_id, lock=True)
    page = ProjectPageSchema.load(_json_body())
    if db.session.get(ProjectPage, page["id"]) is not None:
        raise ConflictError("Page ID is already in use.")
    return _project_response(save_page(project, page, expected), status=201)


@projects_blueprint.patch("/<string:project_id>/pages/<string:page_id>")
@active_user_required
def patch_page(project_id: str, page_id: str):
    expected, error_response = _require_precondition()
    if error_response:
        return error_response
    project = _owned_project(project_id, lock=True)
    body = _json_body()
    body["id"] = page_id
    page = ProjectPageSchema.load(body)
    if not project.document or page_id not in project.document.get("pageOrder", []):
        from werkzeug.exceptions import NotFound

        raise NotFound("Page was not found.")
    return _project_response(save_page(project, page, expected))


@projects_blueprint.delete("/<string:project_id>/pages/<string:page_id>")
@active_user_required
def remove_page(project_id: str, page_id: str):
    expected, error_response = _require_precondition()
    if error_response:
        return error_response
    project = _owned_project(project_id, lock=True)
    return _project_response(delete_page(project, page_id, expected))


@projects_blueprint.post("/<string:project_id>/assets")
@limiter.limit("30 per hour")
@active_user_required
def create_asset(project_id: str):
    expected, error_response = _require_precondition()
    if error_response:
        return error_response
    project = _owned_project(project_id, lock=True)
    file = request.files.get("file")
    if file is None:
        raise ValidationError("An image file is required.", {"file": "required"})
    file.stream.seek(0, 2)
    byte_size = file.stream.tell()
    file.stream.seek(0)
    metadata = AssetMetadataSchema.load(file.filename, file.mimetype, byte_size)
    asset_id = request.form.get("assetId")
    if asset_id is not None and (not asset_id.strip() or len(asset_id) > 36):
        raise ValidationError("Asset ID is invalid.", {"assetId": "invalid"})
    asset = upload_asset(project, get_authenticated_user(), file, metadata, asset_id, expected)
    response = jsonify({"asset": serialize_asset(asset), "projectVersion": project.version})
    response.status_code = 201
    response.headers["ETag"] = f'"{project.version}"'
    return response


@projects_blueprint.get("/<string:project_id>/assets")
@active_user_required
def list_assets(project_id: str):
    project = _owned_project(project_id)
    assets = db.session.scalars(
        select(ProjectAsset).where(ProjectAsset.project_id == project.id).order_by(ProjectAsset.created_at)
    ).all()
    return jsonify({"items": [serialize_asset(asset) for asset in assets]})


@projects_blueprint.delete("/<string:project_id>/assets/<string:asset_id>")
@active_user_required
def remove_asset(project_id: str, asset_id: str):
    expected, error_response = _require_precondition()
    if error_response:
        return error_response
    project = _owned_project(project_id, lock=True)
    asset = CatalogRepository.owned_asset(project.id, asset_id)
    if asset is None:
        from werkzeug.exceptions import NotFound

        raise NotFound("Asset was not found.")
    delete_asset(project, asset, expected)
    response = jsonify({"deleted": True, "projectVersion": project.version})
    response.headers["ETag"] = f'"{project.version}"'
    return response


@projects_blueprint.post("/<string:project_id>/revisions")
@active_user_required
def create_project_revision(project_id: str):
    project = _owned_project(project_id, lock=True)
    revision = create_revision(project, _expected_version(required=False))
    return jsonify({"revision": serialize_revision(revision)}), 201


@projects_blueprint.get("/<string:project_id>/revisions/<string:revision_id>")
@active_user_required
def get_project_revision(project_id: str, revision_id: str):
    _owned_project(project_id)
    revision = db.session.scalar(
        select(ProjectRevision).where(
            ProjectRevision.id == revision_id,
            ProjectRevision.project_id == project_id,
        )
    )
    if revision is None:
        from werkzeug.exceptions import NotFound

        raise NotFound("Revision was not found.")
    return jsonify({"revision": serialize_revision(revision)})


@projects_blueprint.post("/<string:project_id>/revisions/<string:revision_id>/restore")
@active_user_required
def restore_project_revision(project_id: str, revision_id: str):
    expected, error_response = _require_precondition()
    if error_response:
        return error_response
    project = _owned_project(project_id, lock=True)
    revision = db.session.scalar(
        select(ProjectRevision).where(
            ProjectRevision.id == revision_id,
            ProjectRevision.project_id == project_id,
        )
    )
    if revision is None:
        from werkzeug.exceptions import NotFound

        raise NotFound("Revision was not found.")
    return _project_response(restore_revision(project, revision, expected))
