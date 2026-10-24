from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import quote
from typing import BinaryIO

import boto3
from flask import current_app
from botocore.exceptions import BotoCoreError, ClientError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.utils import safe_join

from memorybook.errors import ServiceUnavailableError


class LocalFilesystemAssetStorage:
    def __init__(self):
        self.root = Path(current_app.config["ASSET_LOCAL_DIRECTORY"]).expanduser().resolve()
        self.url_ttl = current_app.config["ASSET_S3_PRESIGNED_URL_TTL"]
        self.signer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="memorybook-local-assets")

    def _path(self, key: str) -> Path:
        if not isinstance(key, str) or not key or "\\" in key or "\x00" in key:
            raise ServiceUnavailableError("The requested photo is unavailable.")
        relative = PurePosixPath(key)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ServiceUnavailableError("The requested photo is unavailable.")
        target = Path(safe_join(str(self.root), *relative.parts)).resolve()
        if not target.is_relative_to(self.root):
            raise ServiceUnavailableError("The requested photo is unavailable.")
        return target

    def _content_type_path(self, key: str) -> Path:
        target = self._path(key)
        return target.with_name(f".{target.name}.content-type")

    def upload(self, key: str, stream: BinaryIO, mime_type: str) -> None:
        target = self._path(key)
        temporary = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.upload")
            with temporary.open("wb") as output:
                while block := stream.read(1024 * 1024):
                    output.write(block)
            temporary.replace(target)
            self._content_type_path(key).write_text(mime_type, encoding="ascii")
        except OSError as failure:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            current_app.logger.exception("Local project asset could not be stored.")
            raise ServiceUnavailableError("The photo could not be stored. Please retry the upload.") from failure

    def download_url(self, key: str) -> str:
        self._path(key)
        token = quote(self.signer.dumps(key), safe="")
        return f"/api/v1/assets/{token}"

    def download(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as failure:
            current_app.logger.exception("Local project asset could not be read.")
            raise ServiceUnavailableError("The photo is temporarily unavailable.") from failure

    def content_type(self, key: str) -> str:
        try:
            return self._content_type_path(key).read_text(encoding="ascii")
        except OSError:
            return "application/octet-stream"

    def download_token(self, token: str) -> str:
        try:
            key = self.signer.loads(token, max_age=self.url_ttl)
            self._path(key)
            return key
        except (BadSignature, SignatureExpired, ServiceUnavailableError) as failure:
            raise ServiceUnavailableError("The requested photo is unavailable or its link has expired.") from failure

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
            self._content_type_path(key).unlink(missing_ok=True)
        except OSError as failure:
            current_app.logger.exception("Local project asset could not be deleted.")
            raise ServiceUnavailableError("The photo could not be deleted. Please retry.") from failure

    def copy(self, source_key: str, target_key: str) -> None:
        try:
            source = self._path(source_key)
            target = self._path(target_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            self._content_type_path(target_key).write_text(self.content_type(source_key), encoding="ascii")
        except OSError as failure:
            current_app.logger.exception("Local project asset could not be copied.")
            raise ServiceUnavailableError("The project could not be duplicated. Please retry.") from failure


class S3AssetStorage:
    def __init__(self):
        config = current_app.config
        if not config.get("ASSET_S3_BUCKET"):
            raise ServiceUnavailableError("Project photo storage is not configured.")
        self.bucket = config["ASSET_S3_BUCKET"]
        self.client = boto3.client(
            "s3",
            region_name=config["ASSET_S3_REGION"],
            endpoint_url=config.get("ASSET_S3_ENDPOINT_URL"),
            aws_access_key_id=config.get("ASSET_S3_ACCESS_KEY_ID") or None,
            aws_secret_access_key=config.get("ASSET_S3_SECRET_ACCESS_KEY") or None,
        )
        self.url_ttl = config["ASSET_S3_PRESIGNED_URL_TTL"]

    def upload(self, key: str, stream: BinaryIO, mime_type: str) -> None:
        try:
            self.client.upload_fileobj(
                stream,
                self.bucket,
                key,
                ExtraArgs={"ContentType": mime_type},
            )
        except (BotoCoreError, ClientError) as failure:
            current_app.logger.exception("Project asset upload failed.")
            raise ServiceUnavailableError("The photo could not be stored. Please retry the upload.") from failure

    def download_url(self, key: str) -> str:
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=self.url_ttl,
            )
        except (BotoCoreError, ClientError) as failure:
            current_app.logger.exception("Project asset download URL could not be created.")
            raise ServiceUnavailableError("The photo is temporarily unavailable.") from failure

    def download(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            with response["Body"] as body:
                return body.read()
        except (BotoCoreError, ClientError) as failure:
            current_app.logger.exception("Project asset download failed.")
            raise ServiceUnavailableError("A photo needed for this book is temporarily unavailable.") from failure

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as failure:
            current_app.logger.exception("Project asset deletion failed.")
            raise ServiceUnavailableError("The photo could not be deleted. Please retry.") from failure

    def copy(self, source_key: str, target_key: str) -> None:
        try:
            self.client.copy_object(
                Bucket=self.bucket,
                Key=target_key,
                CopySource={"Bucket": self.bucket, "Key": source_key},
            )
        except (BotoCoreError, ClientError) as failure:
            current_app.logger.exception("Project asset could not be copied.")
            raise ServiceUnavailableError("The project could not be duplicated. Please retry.") from failure


def get_asset_storage() -> LocalFilesystemAssetStorage | S3AssetStorage:
    configured = current_app.extensions.get("asset_storage")
    if configured is not None:
        return configured
    backend = current_app.config.get("ASSET_STORAGE_BACKEND", "s3")
    if backend == "filesystem" and current_app.config.get("ENVIRONMENT") in {"development", "testing"}:
        return LocalFilesystemAssetStorage()
    if backend != "s3":
        raise ServiceUnavailableError("The configured asset storage backend is unavailable.")
    return S3AssetStorage()
