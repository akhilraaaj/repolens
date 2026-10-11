"""Read a GitHub tar archive without executing anything inside it."""

import hashlib
import io
import tarfile
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.ingestion.filters import skip_reason_for_path
from app.ingestion.limits import IngestionLimits


class UnsafeArchive(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "invalid_archive"
        self.message = message


class LimitReached(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "limit_exceeded"
        self.message = message


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    disposition: str
    reason: str | None
    size_bytes: int | None
    content_sha256: str | None
    content: str | None


@dataclass(frozen=True)
class ArchiveInspection:
    entries: list[ArchiveEntry]
    error_code: str | None = None
    error_message: str | None = None


def inspect_archive(
    payload: bytes,
    limits: IngestionLimits,
    *,
    now: Callable[[], float] = time.monotonic,
    started_at: float | None = None,
) -> ArchiveInspection:
    """Classify archive members into stored, skipped, and failed files."""

    start = now() if started_at is None else started_at
    deadline = start + limits.max_duration_seconds
    try:
        archive = tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz")
    except tarfile.TarError as exc:
        raise UnsafeArchive("The downloaded archive could not be read.") from exc

    with archive:
        members = [member for member in archive.getmembers() if member.name]
        prefix = _shared_prefix(member.name for member in members)
        entries: list[ArchiveEntry] = []
        examined = 0
        stored = 0
        total_bytes = 0
        try:
            for member in members:
                _check_deadline(now, deadline)
                if member.isdir():
                    continue
                path = _safe_relative_path(member.name, prefix)
                if member.issym() or member.islnk():
                    examined += 1
                    _check_entry_limit(examined, limits)
                    entries.append(_skipped(path, "symlink", member.size))
                    continue
                if not member.isfile():
                    continue
                examined += 1
                _check_entry_limit(examined, limits)
                path_reason = skip_reason_for_path(path)
                if path_reason is not None:
                    entries.append(_skipped(path, path_reason, member.size))
                    continue
                if member.size > limits.max_file_bytes:
                    entries.append(_skipped(path, "file_too_large", member.size))
                    continue
                extracted = archive.extractfile(member)
                data = b"" if extracted is None else extracted.read(limits.max_file_bytes + 1)
                if len(data) > limits.max_file_bytes:
                    entries.append(_skipped(path, "file_too_large", len(data)))
                    continue
                if b"\x00" in data[:8192]:
                    entries.append(_skipped(path, "binary", len(data)))
                    continue
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    entries.append(
                        ArchiveEntry(path, "failed", "not_utf8", len(data), None, None)
                    )
                    continue
                if stored + 1 > limits.max_stored_files:
                    raise LimitReached(
                        f"The repository exceeds the stored file limit of {limits.max_stored_files}."
                    )
                if total_bytes + len(data) > limits.max_total_bytes:
                    raise LimitReached(
                        f"The repository exceeds the stored text limit of {limits.max_total_bytes} bytes."
                    )
                stored += 1
                total_bytes += len(data)
                entries.append(
                    ArchiveEntry(
                        path=path,
                        disposition="stored",
                        reason=None,
                        size_bytes=len(data),
                        content_sha256=hashlib.sha256(data).hexdigest(),
                        content=text,
                    )
                )
        except LimitReached as exc:
            return ArchiveInspection(
                entries=entries,
                error_code=exc.error_code,
                error_message=exc.message,
            )
    return ArchiveInspection(entries=entries)


def decide_status(entries: list[ArchiveEntry]) -> tuple[str, str | None, str | None]:
    stored = sum(1 for entry in entries if entry.disposition == "stored")
    failed = sum(1 for entry in entries if entry.disposition == "failed")
    skipped = sum(1 for entry in entries if entry.disposition == "skipped")
    if failed:
        return (
            "failed",
            "partial_failure",
            f"{failed} file{'s' if failed != 1 else ''} could not be read. The snapshot was not marked complete.",
        )
    if stored == 0:
        return (
            "failed",
            "no_source_files",
            "Every file was filtered out. The manifest lists the skip reasons.",
        )
    if skipped:
        return "completed_with_skips", None, None
    return "completed", None, None


def _skipped(path: str, reason: str, size: int | None) -> ArchiveEntry:
    return ArchiveEntry(path, "skipped", reason, size if size and size >= 0 else None, None, None)


def _check_deadline(now: Callable[[], float], deadline: float) -> None:
    if now() >= deadline:
        raise LimitReached("Ingestion exceeded the time limit.")


def _check_entry_limit(examined: int, limits: IngestionLimits) -> None:
    if examined > limits.max_entries:
        raise LimitReached(f"The archive exceeds the entry limit of {limits.max_entries}.")


def _shared_prefix(names: object) -> str | None:
    prefixes: set[str] = set()
    for name in names:  # type: ignore[union-attr]
        normalized = str(name).replace("\\", "/").lstrip("/")
        if "/" not in normalized:
            continue
        first, _separator, _rest = normalized.partition("/")
        if first in {"", ".", ".."}:
            return None
        prefixes.add(first)
        if len(prefixes) > 1:
            return None
    if len(prefixes) != 1:
        return None
    return f"{next(iter(prefixes))}/"


def _safe_relative_path(name: str, prefix: str | None) -> str:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or normalized[1:2] == ":":
        raise UnsafeArchive("The archive contains an absolute path.")
    if prefix and normalized.startswith(prefix):
        normalized = normalized[len(prefix) :]
    parts: list[str] = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise UnsafeArchive("The archive contains a path that escapes the repository.")
        parts.append(part)
    if not parts:
        raise UnsafeArchive("The archive contains an empty file path.")
    return "/".join(parts)
