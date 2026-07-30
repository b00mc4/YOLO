from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings

settings = get_settings()

_ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
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


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


async def save_detection_image(
    village_id: uuid.UUID,
    camera_id: uuid.UUID,
    event_id: uuid.UUID,
    suffix: str,
    upload: UploadFile,
    extension: str,
) -> str:
    content = await _read_with_size_limit(upload)
    relative_path = Path(str(village_id)) / str(camera_id) / f"{event_id}_{suffix}.{extension}"
    absolute_path = Path(settings.storage_path) / relative_path
    await run_in_threadpool(_write_file, absolute_path, content)
    return str(relative_path)