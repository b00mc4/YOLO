from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

_ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
}

_EXTENSION_TO_CONTENT_TYPE = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}

_MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
_READ_CHUNK_SIZE_BYTES = 1024 * 1024


def validate_image_content_type(upload: UploadFile) -> str:
    extension = _ALLOWED_CONTENT_TYPES.get(upload.content_type)
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image content type: {upload.content_type}",
        )
    return extension


async def _read_with_size_limit(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total_size = 0

    while chunk := await upload.read(_READ_CHUNK_SIZE_BYTES):
        total_size += len(chunk)
        if total_size > _MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Image exceeds maximum size of {_MAX_IMAGE_SIZE_BYTES // (1024 * 1024)}MB",
            )
        chunks.append(chunk)

    return b"".join(chunks)


async def read_and_validate_image(upload: UploadFile) -> tuple[bytes, str]:
    extension = validate_image_content_type(upload)
    content = await _read_with_size_limit(upload)
    return content, extension


def build_detection_image_path(
    village_id: uuid.UUID,
    camera_id: uuid.UUID,
    event_id: uuid.UUID,
    suffix: str,
    extension: str,
) -> str:
    relative_path = Path(str(village_id)) / str(camera_id) / f"{event_id}_{suffix}.{extension}"
    return str(relative_path)


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


async def write_detection_image(relative_path: str, content: bytes) -> None:
    absolute_path = Path(settings.storage_path) / relative_path
    await run_in_threadpool(_write_file, absolute_path, content)


def _delete_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Failed to delete orphaned detection image: %s", path)


async def delete_detection_image(relative_path: str) -> None:
    absolute_path = Path(settings.storage_path) / relative_path
    await run_in_threadpool(_delete_file, absolute_path)


def resolve_storage_path(relative_path: str) -> Path:
    return Path(settings.storage_path) / relative_path


def guess_media_type(path: Path) -> str:
    extension = path.suffix.lstrip(".").lower()
    return _EXTENSION_TO_CONTENT_TYPE.get(extension, "application/octet-stream")