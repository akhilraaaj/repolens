"""Run one ingestion attempt and record its manifest."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import UUID

from app.db.connection import connect
from app.db.store import (
    finish_version,
    replace_files,
    update_phase,
    upsert_repository,
    claim_version,
)
from app.ingestion.archive import (
    ArchiveEntry,
    ArchiveInspection,
    LimitReached,
    UnsafeArchive,
    decide_status,
    inspect_archive,
)
from app.ingestion.github import GithubClient, GithubRequestError
from app.ingestion.limits import IngestionLimits

Schedule = Callable[[Awaitable[None]], Awaitable[None]]


async def execute(version_id: UUID, github: GithubClient, limits: IngestionLimits) -> None:
    connection = connect()
    try:
        version = connection.execute(
            """
            SELECT versions.commit_sha, repositories.owner, repositories.name
            FROM repository_versions AS versions
            JOIN repositories ON repositories.id = versions.repository_id
            WHERE versions.id = %s
            """,
            (version_id,),
        ).fetchone()
        if version is None:
            return
        try:
            update_phase(connection, version_id, "downloading")
            payload = await github.archive(
                version["owner"],
                version["name"],
                version["commit_sha"],
                limits.max_archive_bytes,
            )
            update_phase(connection, version_id, "extracting")
            inspection = inspect_archive(payload, limits)
            if inspection.error_code is not None:
                _record(
                    connection,
                    version_id,
                    inspection,
                    status="failed",
                    error_code=inspection.error_code,
                    error_message=inspection.error_message,
                )
                return
        except LimitReached as exc:
            _fail(connection, version_id, exc.error_code, exc.message)
            return
        except UnsafeArchive as exc:
            _fail(connection, version_id, exc.error_code, exc.message)
            return
        except GithubRequestError as exc:
            _fail(connection, version_id, exc.error_code, exc.message)
            return
        except Exception:
            _fail(
                connection,
                version_id,
                "unexpected_error",
                "Ingestion failed before the snapshot was stored.",
            )
            return

        status, error_code, error_message = decide_status(inspection.entries)
        _record(
            connection,
            version_id,
            inspection,
            status=status,
            error_code=error_code,
            error_message=error_message,
        )
    finally:
        connection.close()


def prepare_version(
    *,
    owner: str,
    name: str,
    canonical_url: str,
    default_branch: str,
    commit_sha: str,
    requested_ref: str,
    limits: IngestionLimits,
) -> tuple[UUID, str]:
    connection = connect()
    try:
        repository_id = upsert_repository(
            connection,
            owner=owner,
            name=name,
            canonical_url=canonical_url,
            default_branch=default_branch,
        )
        return claim_version(
            connection,
            repository_id=repository_id,
            commit_sha=commit_sha,
            requested_ref=requested_ref,
            stale_after=timedelta(seconds=limits.max_duration_seconds),
        )
    finally:
        connection.close()


def _record(
    connection,
    version_id: UUID,
    inspection: ArchiveInspection,
    *,
    status: str,
    error_code: str | None,
    error_message: str | None,
) -> None:
    replace_files(connection, version_id, [_entry_row(entry) for entry in inspection.entries])
    stored = [entry for entry in inspection.entries if entry.disposition == "stored"]
    finish_version(
        connection,
        version_id,
        status=status,
        error_code=error_code,
        error_message=error_message,
        stored_count=len(stored),
        skipped_count=sum(entry.disposition == "skipped" for entry in inspection.entries),
        failed_count=sum(entry.disposition == "failed" for entry in inspection.entries),
        total_bytes=sum(entry.size_bytes or 0 for entry in stored),
        examined=len(inspection.entries),
    )


def _fail(connection, version_id: UUID, error_code: str, message: str) -> None:
    finish_version(
        connection,
        version_id,
        status="failed",
        error_code=error_code,
        error_message=message,
        stored_count=0,
        skipped_count=0,
        failed_count=0,
        total_bytes=0,
        examined=0,
    )


def _entry_row(entry: ArchiveEntry) -> dict:
    return {
        "path": entry.path,
        "disposition": entry.disposition,
        "reason": entry.reason,
        "size_bytes": entry.size_bytes,
        "content_sha256": entry.content_sha256,
        "content": entry.content,
    }
