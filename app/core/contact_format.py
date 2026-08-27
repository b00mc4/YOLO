from __future__ import annotations
import re
from app.models.contact import ContactType
from app.core.error_messages import ContactErrors

_PHONE_PATTERN = re.compile(r"^[0-9-]{12}$")
_LINE_PATTERN = re.compile(r"^[a-z0-9._-]{4,20}$")
_INSTAGRAM_PATTERN = re.compile(r"^[a-z0-9._]{1,30}$")

_FACEBOOK_MAX_LENGTH = 50


def _validate_phone(value: str) -> str:
    if not _PHONE_PATTERN.fullmatch(value):
        raise ValueError(ContactErrors.INVALID_PHONE_FORMAT)
    return value


def _validate_line(value: str) -> str:
    if not _LINE_PATTERN.fullmatch(value):
        raise ValueError(ContactErrors.INVALID_LINE_FORMAT)
    return value


def _validate_facebook(value: str) -> str:
    if not value or len(value) > _FACEBOOK_MAX_LENGTH:
        raise ValueError(ContactErrors.INVALID_FACEBOOK_FORMAT)
    return value


def _validate_instagram(value: str) -> str:
    normalized = value.lower()
    if not _INSTAGRAM_PATTERN.fullmatch(normalized):
        raise ValueError(ContactErrors.INVALID_INSTAGRAM_FORMAT)
    return normalized


def normalize_and_validate_contact_value(content_type: ContactType, value: str) -> str:
    stripped = value.strip()

    if content_type == ContactType.PHONE:
        return _validate_phone(stripped)
    if content_type == ContactType.LINE:
        return _validate_line(stripped)
    if content_type == ContactType.FACEBOOK:
        return _validate_facebook(stripped)
    if content_type == ContactType.INSTAGRAM:
        return _validate_instagram(stripped)
    if content_type == ContactType.EMAIL:
        return stripped.lower()
    return stripped