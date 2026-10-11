"""SQL for repository identity, versions, and file manifests."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg
from psycopg.errors import UniqueViolation

ANALYSIS_NOT_STARTED = "not_started"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_COMPLETED_WITH_SKIPS = "completed_with_skips"
STATUS_FAILED = "failed"


def upsert_repository(
    connection: psycopg.Connection,
    *,
    owner: str,
    name: str,
    canonical_url: str,
    default_branch: str,
) -> UUID:
    now = datetime.now(timezone.utc)
    row = connection.execute(
        """
        INSERT INTO repositories (
            id, host, owner, name, canonical_url, default_branch, created_at, updated_at
        )
        VALUES (%s, 'github.com', %s, %s, %s, %s, %s, %s)
        ON CONFLICT (host, owner, name)
        DO UPDATE SET
            canonical_url = EXCLUDED.canonical_url,
            default_branch = EXCLUDED.default_branch,
            updated_at = EXCLUDED.updated_at
        RETURNING id
        """,
        (uuid4(), owner, name, canonical_url, default_branch, now, now),
    ).fetchone()
    assert row is not None
    return row["id"]


def claim_version(
    connection: psycopg.Connection,
    *,
    repository_id: UUID,
    commit_sha: str,
    requested_ref: str,
    stale_after: timedelta,
) -> tuple[UUID, str]:
    """Return the version id and either 'run' or 'return'.

    A fresh running attempt and a finished snapshot are returned as-is.
    A failed or abandoned attempt is reset in place so the commit keeps one row.
    """

    now = datetime.now(timezone.utc)
    try:
        existing = connection.execute(
            """
            SELECT id, status, started_at
            FROM repository_versions
            WHERE repository_id = %s AND commit_sha = %s
            FOR UPDATE
            """,
            (repository_id, commit_sha),
        ).fetchone()
    except Exception:
        connection.rollback()
        raise
    if existing is None:
        version_id = uuid4()
        try:
            connection.execute(
                """
                INSERT INTO repository_versions (
                    id, repository_id, commit_sha, requested_ref, status,
                    analysis_status, phase, started_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'resolving', %s)
                """,
                (
                    version_id,
                    repository_id,
                    commit_sha,
                    requested_ref,
                    STATUS_RUNNING,
                    ANALYSIS_NOT_STARTED,
                    now,
                ),
            )
        except UniqueViolation:
            connection.rollback()
            return claim_version(
                connection,
                repository_id=repository_id,
                commit_sha=commit_sha,
                requested_ref=requested_ref,
                stale_after=stale_after,
            )
        connection.commit()
        return version_id, "run"

    status = existing["status"]
    started_at = existing["started_at"]
    fresh_running = (
        status == STATUS_RUNNING
        and started_at is not None
        and started_at >= now - stale_after
    )
    if status in {STATUS_COMPLETED, STATUS_COMPLETED_WITH_SKIPS} or fresh_running:
        connection.commit()
        return existing["id"], "return"

    connection.execute(
        "DELETE FROM files WHERE repository_version_id = %s",
        (existing["id"],),
    )
    connection.execute(
        """
        UPDATE repository_versions
        SET requested_ref = %s,
            status = %s,
            analysis_status = %s,
            phase = 'resolving',
            progress_completed = 0,
            progress_total = NULL,
            stored_count = 0,
            skipped_count = 0,
            failed_count = 0,
            total_bytes = 0,
            error_code = NULL,
            error_message = NULL,
            started_at = %s,
            finished_at = NULL,
            parser_name = NULL,
            parser_version = NULL,
            symbol_count = 0,
            relationship_count = 0,
            unresolved_count = 0,
            analysis_error_code = NULL,
            analysis_error_message = NULL,
            analysis_started_at = NULL
        WHERE id = %s
        """,
        (requested_ref, STATUS_RUNNING, ANALYSIS_NOT_STARTED, now, existing["id"]),
    )
    connection.commit()
    return existing["id"], "run"


def update_phase(
    connection: psycopg.Connection,
    version_id: UUID,
    phase: str,
    *,
    progress_completed: int | None = None,
) -> None:
    connection.execute(
        """
        UPDATE repository_versions
        SET phase = %s,
            progress_completed = COALESCE(%s, progress_completed)
        WHERE id = %s
        """,
        (phase, progress_completed, version_id),
    )
    connection.commit()


def replace_files(connection: psycopg.Connection, version_id: UUID, entries: list[dict]) -> None:
    connection.execute("DELETE FROM files WHERE repository_version_id = %s", (version_id,))
    for entry in entries:
        connection.execute(
            """
            INSERT INTO files (
                id, repository_version_id, path, disposition, reason,
                size_bytes, content_sha256, content
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                version_id,
                entry["path"],
                entry["disposition"],
                entry["reason"],
                entry["size_bytes"],
                entry["content_sha256"],
                entry["content"],
            ),
        )
    connection.commit()


def finish_version(
    connection: psycopg.Connection,
    version_id: UUID,
    *,
    status: str,
    error_code: str | None,
    error_message: str | None,
    stored_count: int,
    skipped_count: int,
    failed_count: int,
    total_bytes: int,
    examined: int,
) -> None:
    connection.execute(
        """
        UPDATE repository_versions
        SET status = %s,
            phase = 'finalizing',
            error_code = %s,
            error_message = %s,
            stored_count = %s,
            skipped_count = %s,
            failed_count = %s,
            total_bytes = %s,
            progress_completed = %s,
            progress_total = %s,
            finished_at = %s
        WHERE id = %s
        """,
        (
            status,
            error_code,
            error_message,
            stored_count,
            skipped_count,
            failed_count,
            total_bytes,
            examined,
            examined,
            datetime.now(timezone.utc),
            version_id,
        ),
    )
    connection.commit()


def load_ingestion(connection: psycopg.Connection, version_id: UUID) -> dict | None:
    version = connection.execute(
        """
        SELECT
            versions.id,
            versions.status,
            versions.analysis_status,
            versions.phase,
            versions.commit_sha,
            versions.requested_ref,
            versions.stored_count,
            versions.skipped_count,
            versions.failed_count,
            versions.total_bytes,
            versions.progress_completed,
            versions.progress_total,
            versions.error_code,
            versions.error_message,
            versions.parser_name,
            versions.parser_version,
            versions.symbol_count,
            versions.relationship_count,
            versions.unresolved_count,
            versions.analysis_error_code,
            versions.analysis_error_message,
            versions.chunk_count,
            versions.embedding_status,
            versions.embedding_error,
            repositories.owner,
            repositories.name,
            repositories.canonical_url
        FROM repository_versions AS versions
        JOIN repositories ON repositories.id = versions.repository_id
        WHERE versions.id = %s
        """,
        (version_id,),
    ).fetchone()
    if version is None:
        return None
    file_rows = connection.execute(
        """
        SELECT path, disposition, reason, size_bytes, parse_status, parse_error
        FROM files
        WHERE repository_version_id = %s
        ORDER BY path
        """,
        (version_id,),
    ).fetchall()
    return ingestion_payload(version, file_rows)


def ingestion_payload(version: dict, file_rows: list[dict]) -> dict:
    return {
        "id": str(version["id"]),
        "status": version["status"],
        "analysis_status": version["analysis_status"],
        "phase": version["phase"],
        "owner": version["owner"],
        "name": version["name"],
        "canonical_url": version["canonical_url"],
        "commit_sha": version["commit_sha"],
        "requested_ref": version["requested_ref"],
        "stored_count": version["stored_count"],
        "skipped_count": version["skipped_count"],
        "failed_count": version["failed_count"],
        "total_bytes": version["total_bytes"],
        "progress_completed": version["progress_completed"],
        "progress_total": version["progress_total"],
        "error_code": version["error_code"],
        "error_message": version["error_message"],
        "parser_name": version["parser_name"],
        "parser_version": version["parser_version"],
        "symbol_count": version["symbol_count"],
        "relationship_count": version["relationship_count"],
        "unresolved_count": version["unresolved_count"],
        "analysis_error_code": version["analysis_error_code"],
        "analysis_error_message": version["analysis_error_message"],
        "chunk_count": version["chunk_count"],
        "embedding_status": version["embedding_status"],
        "embedding_error": version["embedding_error"],
        "files": [
            {
                "path": row["path"],
                "disposition": row["disposition"],
                "reason": row["reason"],
                "size_bytes": row["size_bytes"],
                "parse_status": row["parse_status"],
                "parse_error": row["parse_error"],
            }
            for row in file_rows
        ],
    }
