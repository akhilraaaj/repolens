"""Build searchable chunks from a stored snapshot."""

from uuid import UUID, uuid4

import psycopg

from app.search.context import context_header
from app.search.text import content_hash, slice_lines

SYMBOL_TYPES = {"function", "class", "method", "value"}
FILE_CHAR_LIMIT = 8000


def rebuild_chunks(connection: psycopg.Connection, version_id: UUID) -> int:
    connection.execute("DELETE FROM code_chunks WHERE repository_version_id = %s", (version_id,))
    files = connection.execute(
        """
        SELECT id, path, content
        FROM files
        WHERE repository_version_id = %s AND disposition = 'stored' AND content IS NOT NULL
        """,
        (version_id,),
    ).fetchall()
    file_text = {row["id"]: row for row in files}
    symbols = connection.execute(
        """
        SELECT id, file_id, entity_type, name, qualified_name, start_line, end_line
        FROM symbols
        WHERE repository_version_id = %s
        """,
        (version_id,),
    ).fetchall()
    imports = _imports_by_file(connection, version_id)
    covered: set[UUID] = set()
    count = 0
    for symbol in symbols:
        if symbol["entity_type"] not in SYMBOL_TYPES:
            continue
        file_row = file_text.get(symbol["file_id"])
        if file_row is None:
            continue
        text = slice_lines(file_row["content"], symbol["start_line"], symbol["end_line"])
        if not text:
            continue
        _insert_chunk(
            connection,
            version_id,
            file_row["id"],
            symbol["id"],
            file_row["path"],
            symbol["start_line"],
            symbol["end_line"],
            symbol["entity_type"],
            text,
            context_header(
                file_row["path"],
                name=symbol["name"],
                entity_type=symbol["entity_type"],
                qualified_name=symbol["qualified_name"],
                imports=imports.get(file_row["path"], []),
            ),
        )
        covered.add(file_row["id"])
        count += 1
    for file_row in files:
        if file_row["id"] in covered:
            continue
        text = file_row["content"][:FILE_CHAR_LIMIT]
        if text.strip() == "":
            continue
        end_line = len(text.splitlines())
        _insert_chunk(
            connection,
            version_id,
            file_row["id"],
            None,
            file_row["path"],
            1,
            end_line,
            "file",
            text,
            context_header(file_row["path"], imports=imports.get(file_row["path"], [])),
        )
        count += 1
    connection.execute(
        "UPDATE repository_versions SET chunk_count = %s WHERE id = %s",
        (count, version_id),
    )
    connection.commit()
    return count


def _insert_chunk(
    connection: psycopg.Connection,
    version_id: UUID,
    file_id: UUID,
    symbol_id: UUID | None,
    path: str,
    start_line: int,
    end_line: int,
    chunk_type: str,
    content: str,
    header: str,
) -> None:
    connection.execute(
        """
        INSERT INTO code_chunks (
            id, repository_version_id, file_id, symbol_id, path,
            start_line, end_line, chunk_type, content, content_sha256, header
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid4(),
            version_id,
            file_id,
            symbol_id,
            path,
            start_line,
            end_line,
            chunk_type,
            content,
            content_hash(content),
            header,
        ),
    )


def _imports_by_file(connection: psycopg.Connection, version_id: UUID) -> dict[str, list[str]]:
    rows = connection.execute(
        """
        SELECT evidence_file, specifier
        FROM relationships
        WHERE repository_version_id = %s
          AND relationship_type = 'imports'
          AND specifier IS NOT NULL
        ORDER BY evidence_file, specifier
        """,
        (version_id,),
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    for row in rows:
        bucket = grouped.setdefault(row["evidence_file"], [])
        if row["specifier"] not in bucket:
            bucket.append(row["specifier"])
    return grouped
