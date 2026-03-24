"""Input validation utilities — centralised sanitisation for resource identifiers."""

from src.exceptions import ValidationError

_MAX_ID_LENGTH = 256


def safe_resource_id(value, field: str = "identifier") -> str:
    """Sanitise a resource identifier (projectId, sectorName, jobId, entryId).

    Prevents path traversal, null byte injection, and oversized inputs.
    Raises ValidationError if the value is empty or contains forbidden characters.
    """
    if value is None:
        value = ""
    sanitized = str(value).strip()
    if not sanitized:
        raise ValidationError(f"Missing required field: {field}", field=field)
    if len(sanitized) > _MAX_ID_LENGTH:
        raise ValidationError(f"Invalid {field}: exceeds maximum length", field=field)
    if (
        ".." in sanitized
        or "/" in sanitized
        or "\\" in sanitized
        or "\x00" in sanitized
    ):
        raise ValidationError(
            f"Invalid {field}: contains forbidden characters", field=field
        )
    return sanitized
