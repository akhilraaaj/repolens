"""Symbol change-impact from the stored graph."""

from uuid import UUID

import psycopg

from app.answers.tools import find_symbol, neighbors, related_tests


def impact_for_name(connection: psycopg.Connection, version_id: UUID, name: str, depth: int) -> dict | None:
    version = connection.execute(
        "SELECT id FROM repository_versions WHERE id = %s",
        (version_id,),
    ).fetchone()
    if version is None:
        return None
    matches = find_symbol(connection, version_id, name)
    if not matches:
        return {
            "symbol": None,
            "affected": [],
            "related_tests": [],
            "uncertainties": [f"No symbol named {name} is in this snapshot."],
        }
    symbol = matches[0]
    affected = neighbors(connection, version_id, UUID(symbol["id"]), incoming=True, depth=depth)
    return {
        "symbol": symbol,
        "affected": affected,
        "related_tests": related_tests(affected),
        "uncertainties": [
            "Only relationships extracted from stored JavaScript and TypeScript are included.",
            "A dependent at a greater distance than the requested depth is omitted.",
        ],
    }
