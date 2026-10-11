"""Chat threads stored for one snapshot. Messages are data, not instructions."""

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg


def ensure_thread(connection: psycopg.Connection, version_id: UUID, thread_id: UUID | None, title: str) -> UUID:
    if thread_id is not None:
        row = connection.execute(
            "SELECT id FROM chat_threads WHERE id = %s AND repository_version_id = %s",
            (thread_id, version_id),
        ).fetchone()
        if row is None:
            raise ValueError("That conversation does not belong to this snapshot.")
        return thread_id
    created = uuid4()
    connection.execute(
        """
        INSERT INTO chat_threads (id, repository_version_id, title, created_at)
        VALUES (%s, %s, %s, %s)
        """,
        (created, version_id, title[:80], datetime.now(timezone.utc)),
    )
    return created


def recent_messages(connection: psycopg.Connection, thread_id: UUID) -> list[dict]:
    rows = connection.execute(
        """
        SELECT role, content
        FROM chat_messages
        WHERE thread_id = %s
        ORDER BY created_at DESC
        LIMIT 6
        """,
        (thread_id,),
    ).fetchall()
    return [{"role": row["role"], "content": row["content"][:2000]} for row in reversed(rows)]


def add_message(
    connection: psycopg.Connection,
    thread_id: UUID,
    role: str,
    content: str,
    citations: list,
) -> None:
    connection.execute(
        """
        INSERT INTO chat_messages (id, thread_id, role, content, citations, created_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        """,
        (uuid4(), thread_id, role, content, json.dumps(citations), datetime.now(timezone.utc)),
    )
