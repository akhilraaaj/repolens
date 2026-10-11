"""Read-only investigation tools scoped to one repository version."""

from uuid import UUID

import psycopg

from app.search.retrieve import search_version
from app.search.text import safe_relative_path, slice_lines

MAX_DEPTH = 3
MAX_BYTES = 8000


def search_code(connection: psycopg.Connection, version_id: UUID, query: str) -> list[dict]:
    return search_version(connection, version_id, query, limit=8)


def get_file(
    connection: psycopg.Connection,
    version_id: UUID,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    *,
    limit: int = MAX_BYTES,
) -> dict | None:
    relative = safe_relative_path(path)
    row = connection.execute(
        """
        SELECT path, content
        FROM files
        WHERE repository_version_id = %s AND path = %s AND disposition = 'stored'
        """,
        (version_id, relative),
    ).fetchone()
    if row is None or not isinstance(row["content"], str):
        return None
    lines = row["content"].splitlines()
    start = 1 if start_line is None else start_line
    end = len(lines) if end_line is None else end_line
    end = min(end, len(lines))
    snippet = slice_lines(row["content"], start, end, limit=limit)
    if snippet is None:
        return None
    full = "\n".join(lines[start - 1 : end])
    return {
        "path": row["path"],
        "start_line": start,
        "end_line": end,
        "content": snippet,
        "truncated": len(full) > len(snippet),
    }


def find_symbol(connection: psycopg.Connection, version_id: UUID, name: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT symbols.id, symbols.name, symbols.qualified_name, symbols.entity_type,
               symbols.start_line, symbols.end_line, files.path
        FROM symbols
        JOIN files ON files.id = symbols.file_id
        WHERE symbols.repository_version_id = %s AND symbols.name ILIKE %s
        ORDER BY symbols.name, files.path
        LIMIT 10
        """,
        (version_id, name),
    ).fetchall()
    return [_symbol_row(row) for row in rows]


def neighbors(
    connection: psycopg.Connection,
    version_id: UUID,
    symbol_id: UUID,
    *,
    incoming: bool,
    depth: int,
) -> list[dict]:
    depth = min(max(depth, 1), MAX_DEPTH)
    origin = connection.execute("SELECT name FROM symbols WHERE id = %s", (symbol_id,)).fetchone()
    names = {symbol_id: origin["name"] if origin else None}
    seen = {symbol_id}
    frontier = [symbol_id]
    found: list[dict] = []
    for distance in range(1, depth + 1):
        if not frontier:
            break
        column = "target_symbol_id" if incoming else "source_symbol_id"
        other = "source_symbol_id" if incoming else "target_symbol_id"
        rows = connection.execute(
            f"""
            SELECT relationships.relationship_type, relationships.resolution_status,
                   relationships.{column} AS via_id,
                   other.id, other.name, other.qualified_name, other.entity_type,
                   other.start_line, other.end_line, files.path
            FROM relationships
            JOIN symbols AS other ON other.id = relationships.{other}
            JOIN files ON files.id = other.file_id
            WHERE relationships.repository_version_id = %s
              AND relationships.{column} = ANY(%s)
            """,
            (version_id, frontier),
        ).fetchall()
        frontier = []
        for row in rows:
            names.setdefault(row["id"], row["name"])
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            frontier.append(row["id"])
            item = _symbol_row(row)
            item["distance"] = distance
            item["relationship_type"] = row["relationship_type"]
            item["resolution_status"] = row["resolution_status"]
            item["via"] = names.get(row["via_id"])
            found.append(item)
    return found


def related_tests(affected: list[dict]) -> list[dict]:
    return [item for item in affected if _looks_like_test(item["path"])]


def _looks_like_test(path: str) -> bool:
    lowered = path.lower()
    return "/test" in f"/{lowered}" or ".test." in lowered or ".spec." in lowered


def _symbol_row(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "qualified_name": row["qualified_name"],
        "entity_type": row["entity_type"],
        "path": row["path"],
        "start_line": row["start_line"],
        "end_line": row["end_line"],
    }
