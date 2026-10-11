"""Persist symbols and relationships for one repository version."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import psycopg

from app.analysis.parser import ParseResult

ANALYSIS_RUNNING = "running"
ANALYSIS_COMPLETED = "completed"
ANALYSIS_COMPLETED_WITH_ERRORS = "completed_with_errors"
ANALYSIS_FAILED = "failed"
READY_INGESTION = {"completed", "completed_with_skips"}


def claim_analysis(
    connection: psycopg.Connection,
    version_id: UUID,
    *,
    stale_after: timedelta,
) -> str:
    """Return 'run', 'return', or 'rejected'."""

    now = datetime.now(timezone.utc)
    version = connection.execute(
        """
        SELECT status, analysis_status, analysis_started_at
        FROM repository_versions
        WHERE id = %s
        FOR UPDATE
        """,
        (version_id,),
    ).fetchone()
    if version is None:
        connection.rollback()
        return "missing"
    if version["status"] not in READY_INGESTION:
        connection.rollback()
        return "rejected"
    started_at = version["analysis_started_at"]
    fresh_running = (
        version["analysis_status"] == ANALYSIS_RUNNING
        and started_at is not None
        and started_at >= now - stale_after
    )
    if fresh_running:
        connection.commit()
        return "return"
    connection.execute(
        """
        UPDATE repository_versions
        SET analysis_status = %s,
            analysis_started_at = %s,
            analysis_error_code = NULL,
            analysis_error_message = NULL
        WHERE id = %s
        """,
        (ANALYSIS_RUNNING, now, version_id),
    )
    connection.commit()
    return "run"


def load_source_files(connection: psycopg.Connection, version_id: UUID) -> list[dict]:
    return connection.execute(
        """
        SELECT id, path, disposition, content
        FROM files
        WHERE repository_version_id = %s
        ORDER BY path
        """,
        (version_id,),
    ).fetchall()


def mark_analysis_failed(
    connection: psycopg.Connection,
    version_id: UUID,
    error_code: str,
    message: str,
) -> None:
    connection.execute(
        """
        UPDATE repository_versions
        SET analysis_status = %s,
            analysis_error_code = %s,
            analysis_error_message = %s
        WHERE id = %s
        """,
        (ANALYSIS_FAILED, error_code, message, version_id),
    )
    connection.commit()


def replace_graph(
    connection: psycopg.Connection,
    version_id: UUID,
    result: ParseResult,
    *,
    skipped_paths: list[str],
) -> None:
    """Replace the graph in one transaction so a crash keeps the previous result."""

    file_rows = connection.execute(
        """
        SELECT id, path
        FROM files
        WHERE repository_version_id = %s
        """,
        (version_id,),
    ).fetchall()
    file_ids = {row["path"]: row["id"] for row in file_rows}
    connection.execute("DELETE FROM relationships WHERE repository_version_id = %s", (version_id,))
    connection.execute("DELETE FROM symbols WHERE repository_version_id = %s", (version_id,))
    for path in skipped_paths:
        if path in file_ids:
            connection.execute(
                """
                UPDATE files
                SET parse_status = 'skipped', parse_error = NULL
                WHERE id = %s
                """,
                (file_ids[path],),
            )
    for parsed in result.files:
        if parsed.path not in file_ids:
            continue
        connection.execute(
            """
            UPDATE files
            SET parse_status = %s, parse_error = %s
            WHERE id = %s
            """,
            (parsed.parse_status, parsed.parse_error, file_ids[parsed.path]),
        )
    symbol_ids: dict[str, UUID] = {}
    for symbol in result.symbols:
        file_id = file_ids.get(symbol.path)
        if file_id is None:
            continue
        symbol_id = uuid4()
        symbol_ids[symbol.local_id] = symbol_id
        connection.execute(
            """
            INSERT INTO symbols (
                id, repository_version_id, file_id, local_id, entity_type,
                name, qualified_name, start_line, end_line, exported
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                symbol_id,
                version_id,
                file_id,
                symbol.local_id,
                symbol.entity_type,
                symbol.name,
                symbol.qualified_name,
                symbol.start_line,
                symbol.end_line,
                symbol.exported,
            ),
        )
    stored_relationships = 0
    unresolved = 0
    for relationship in result.relationships:
        source_id = symbol_ids.get(relationship.source_local_id)
        target_id = symbol_ids.get(relationship.target_local_id) if relationship.target_local_id else None
        if source_id is None or (relationship.resolution_status != "unresolved" and target_id is None):
            continue
        if relationship.resolution_status == "unresolved":
            unresolved += 1
        stored_relationships += 1
        connection.execute(
            """
            INSERT INTO relationships (
                id, repository_version_id, source_symbol_id, target_symbol_id,
                relationship_type, resolution_status, evidence_file,
                evidence_start_line, evidence_end_line, specifier, target_name
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                version_id,
                source_id,
                target_id,
                relationship.relationship_type,
                relationship.resolution_status,
                relationship.evidence_file,
                relationship.evidence_start_line,
                relationship.evidence_end_line,
                relationship.specifier,
                relationship.target_name,
            ),
        )
    failed = any(parsed.parse_status == "failed" for parsed in result.files)
    connection.execute(
        """
        UPDATE repository_versions
        SET analysis_status = %s,
            parser_name = %s,
            parser_version = %s,
            symbol_count = %s,
            relationship_count = %s,
            unresolved_count = %s,
            analysis_error_code = NULL,
            analysis_error_message = NULL,
            embedding_status = 'running',
            embedding_error = NULL
        WHERE id = %s
        """,
        (
            ANALYSIS_COMPLETED_WITH_ERRORS if failed else ANALYSIS_COMPLETED,
            result.parser_name,
            result.parser_version,
            len(symbol_ids),
            stored_relationships,
            unresolved,
            version_id,
        ),
    )
    connection.commit()


MAX_MAP_FILES = 5000
MAX_MAP_EDGES = 20000
TOP_SYMBOLS = 6


def load_file_graph(connection: psycopg.Connection, version_id: UUID) -> dict | None:
    """One node per parsed file and one edge per (source file, target file, type).

    Symbol-level calls, imports, and renders are collapsed so a whole repository
    fits in one response. Unresolved bare imports become package edges.
    """

    version = connection.execute(
        "SELECT analysis_status FROM repository_versions WHERE id = %s",
        (version_id,),
    ).fetchone()
    if version is None:
        return None
    file_rows = connection.execute(
        """
        SELECT files.path, files.parse_status, count(symbols.id) AS symbol_count
        FROM files
        LEFT JOIN symbols ON symbols.file_id = files.id AND symbols.entity_type <> 'module'
        WHERE files.repository_version_id = %s AND files.parse_status IN ('parsed', 'failed')
        GROUP BY files.path, files.parse_status
        ORDER BY files.path
        LIMIT %s
        """,
        (version_id, MAX_MAP_FILES + 1),
    ).fetchall()
    symbol_rows = connection.execute(
        """
        SELECT files.path, symbols.name, symbols.entity_type, symbols.start_line, symbols.end_line, symbols.exported
        FROM symbols
        JOIN files ON files.id = symbols.file_id
        WHERE symbols.repository_version_id = %s AND symbols.entity_type <> 'module'
        ORDER BY files.path, symbols.exported DESC, symbols.start_line
        """,
        (version_id,),
    ).fetchall()
    top: dict[str, list[dict]] = {}
    for row in symbol_rows:
        bucket = top.setdefault(row["path"], [])
        if len(bucket) < TOP_SYMBOLS:
            bucket.append(
                {
                    "name": row["name"],
                    "entity_type": row["entity_type"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                    "exported": row["exported"],
                }
            )
    edge_rows = connection.execute(
        """
        SELECT source_file.path AS source, target_file.path AS target,
               relationships.relationship_type, relationships.resolution_status,
               count(*) AS count,
               min(relationships.evidence_start_line) AS line
        FROM relationships
        JOIN symbols AS source_symbol ON source_symbol.id = relationships.source_symbol_id
        JOIN files AS source_file ON source_file.id = source_symbol.file_id
        JOIN symbols AS target_symbol ON target_symbol.id = relationships.target_symbol_id
        JOIN files AS target_file ON target_file.id = target_symbol.file_id
        WHERE relationships.repository_version_id = %s AND source_file.path <> target_file.path
        GROUP BY 1, 2, 3, 4
        LIMIT %s
        """,
        (version_id, MAX_MAP_EDGES + 1),
    ).fetchall()
    package_rows = connection.execute(
        """
        SELECT relationships.evidence_file AS source, relationships.specifier, count(*) AS count
        FROM relationships
        WHERE relationships.repository_version_id = %s
          AND relationships.resolution_status = 'unresolved'
          AND relationships.specifier IS NOT NULL
          AND relationships.specifier NOT LIKE '.%%'
        GROUP BY 1, 2
        """,
        (version_id,),
    ).fetchall()
    merged: dict[tuple[str, str], dict] = {}
    for row in edge_rows[:MAX_MAP_EDGES]:
        key = (row["source"], row["target"])
        item = merged.setdefault(
            key,
            {"source": row["source"], "target": row["target"], "kinds": {}, "status": row["resolution_status"], "line": row["line"]},
        )
        item["kinds"][row["relationship_type"]] = item["kinds"].get(row["relationship_type"], 0) + row["count"]
        if row["resolution_status"] == "verified":
            item["status"] = "verified"
        item["line"] = min(item["line"], row["line"])
    packages: dict[str, dict] = {}
    for row in package_rows:
        name = package_name(row["specifier"])
        if name is None:
            continue
        entry = packages.setdefault(name, {"name": name, "importers": []})
        if row["source"] not in entry["importers"]:
            entry["importers"].append(row["source"])
    return {
        "analysis_status": version["analysis_status"],
        "truncated": len(file_rows) > MAX_MAP_FILES or len(edge_rows) > MAX_MAP_EDGES,
        "files": [
            {
                "path": row["path"],
                "parse_status": row["parse_status"],
                "symbol_count": row["symbol_count"],
                "top_symbols": top.get(row["path"], []),
            }
            for row in file_rows[:MAX_MAP_FILES]
        ],
        "edges": list(merged.values()),
        "packages": sorted(packages.values(), key=lambda item: (-len(item["importers"]), item["name"])),
    }


def package_name(specifier: str) -> str | None:
    """'react-dom/client' -> 'react-dom', '@scope/pkg/x' -> '@scope/pkg'. Aliases are left out."""

    if specifier.startswith(("/", "~", "#")) or specifier.startswith("@/"):
        return None
    parts = specifier.split("/")
    if specifier.startswith("@"):
        return "/".join(parts[:2]) if len(parts) >= 2 else None
    return parts[0] or None


def load_graph(
    connection: psycopg.Connection,
    version_id: UUID,
    *,
    edge_type: str | None,
    file_path: str | None,
    resolution_status: str | None,
    limit: int,
) -> dict | None:
    version = connection.execute(
        """
        SELECT symbol_count, relationship_count, unresolved_count, analysis_status
        FROM repository_versions
        WHERE id = %s
        """,
        (version_id,),
    ).fetchone()
    if version is None:
        return None
    symbols = connection.execute(
        """
        SELECT
            symbols.id, symbols.entity_type, symbols.name, symbols.qualified_name,
            files.path, symbols.start_line, symbols.end_line, symbols.exported
        FROM symbols
        JOIN files ON files.id = symbols.file_id
        WHERE symbols.repository_version_id = %s
          AND (%s::text IS NULL OR files.path = %s)
        ORDER BY files.path, symbols.start_line, symbols.name
        LIMIT %s
        """,
        (version_id, file_path, file_path, limit + 1),
    ).fetchall()
    relationships = connection.execute(
        """
        SELECT
            relationships.relationship_type,
            relationships.resolution_status,
            relationships.evidence_file,
            relationships.evidence_start_line,
            relationships.evidence_end_line,
            relationships.specifier,
            relationships.target_name,
            source_symbol.qualified_name AS source_qualified_name,
            target_symbol.qualified_name AS target_qualified_name
        FROM relationships
        JOIN symbols AS source_symbol ON source_symbol.id = relationships.source_symbol_id
        LEFT JOIN symbols AS target_symbol ON target_symbol.id = relationships.target_symbol_id
        WHERE relationships.repository_version_id = %s
          AND (%s::text IS NULL OR relationships.relationship_type = %s)
          AND (%s::text IS NULL OR relationships.evidence_file = %s)
          AND (%s::text IS NULL OR relationships.resolution_status = %s)
        ORDER BY relationships.evidence_file, relationships.evidence_start_line, relationships.relationship_type
        LIMIT %s
        """,
        (
            version_id,
            edge_type,
            edge_type,
            file_path,
            file_path,
            resolution_status,
            resolution_status,
            limit + 1,
        ),
    ).fetchall()
    return {
        "analysis_status": version["analysis_status"],
        "symbol_count": version["symbol_count"],
        "relationship_count": version["relationship_count"],
        "unresolved_count": version["unresolved_count"],
        "truncated": len(symbols) > limit or len(relationships) > limit,
        "symbols": [
            {
                "id": str(row["id"]),
                "entity_type": row["entity_type"],
                "name": row["name"],
                "qualified_name": row["qualified_name"],
                "path": row["path"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "exported": row["exported"],
            }
            for row in symbols[:limit]
        ],
        "relationships": [
            {
                "relationship_type": row["relationship_type"],
                "resolution_status": row["resolution_status"],
                "evidence_file": row["evidence_file"],
                "evidence_start_line": row["evidence_start_line"],
                "evidence_end_line": row["evidence_end_line"],
                "specifier": row["specifier"],
                "target_name": row["target_name"],
                "source_qualified_name": row["source_qualified_name"],
                "target_qualified_name": row["target_qualified_name"],
            }
            for row in relationships[:limit]
        ],
    }
