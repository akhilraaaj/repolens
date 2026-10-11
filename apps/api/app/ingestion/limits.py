"""Configurable ingestion bounds."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionLimits:
    max_archive_bytes: int = 100 * 1024 * 1024
    max_entries: int = 20000
    max_stored_files: int = 10000
    max_file_bytes: int = 512 * 1024
    max_total_bytes: int = 64 * 1024 * 1024
    max_duration_seconds: float = 180


class InvalidIngestionConfiguration(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def limits_from_env() -> IngestionLimits:
    return IngestionLimits(
        max_archive_bytes=_positive_int("REPOLENS_MAX_ARCHIVE_BYTES", 100 * 1024 * 1024),
        max_entries=_positive_int("REPOLENS_MAX_ENTRIES", 20000),
        max_stored_files=_positive_int("REPOLENS_MAX_STORED_FILES", 10000),
        max_file_bytes=_positive_int("REPOLENS_MAX_FILE_BYTES", 512 * 1024),
        max_total_bytes=_positive_int("REPOLENS_MAX_TOTAL_BYTES", 64 * 1024 * 1024),
        max_duration_seconds=float(_positive_int("REPOLENS_MAX_DURATION_SECONDS", 180)),
    )


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise InvalidIngestionConfiguration(f"{name} must be an integer.") from exc
    if value <= 0:
        raise InvalidIngestionConfiguration(f"{name} must be positive.")
    return value
