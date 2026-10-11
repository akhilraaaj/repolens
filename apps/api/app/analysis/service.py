"""Analyze one stored snapshot and replace its graph."""

import os
from uuid import UUID

from app.analysis.active import clear_active, mark_active
from app.analysis.parser import AnalyzerFailure, run_parser
from app.analysis.store import load_source_files, mark_analysis_failed, replace_graph
from app.db.connection import connect
from app.search.chunks import rebuild_chunks
from app.search.vectors import embed_version

PARSABLE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
CONFIG_NAMES = {"tsconfig.json", "jsconfig.json"}


def analysis_timeout_seconds() -> float:
    raw = os.environ.get("REPOLENS_MAX_ANALYSIS_SECONDS", "").strip()
    if raw == "":
        return 60
    value = int(raw)
    if value <= 0:
        raise ValueError("REPOLENS_MAX_ANALYSIS_SECONDS must be positive.")
    return float(value)


def execute_analysis(version_id: UUID) -> None:
    """Parse outside the database transaction so a poll cannot deadlock with it."""

    mark_active(version_id)
    try:
        _execute_analysis(version_id)
    finally:
        clear_active(version_id)


def _execute_analysis(version_id: UUID) -> None:
    try:
        parsable, skipped, config = _source_texts(version_id)
        result = run_parser(parsable, analysis_timeout_seconds(), config)
    except AnalyzerFailure as exc:
        _fail(version_id, exc.error_code, exc.message)
        return
    except ValueError as exc:
        _fail(version_id, "invalid_configuration", str(exc))
        return
    except Exception:
        _fail(version_id, "unexpected_error", "Analysis failed before the graph was stored.")
        return
    connection = connect()
    try:
        replace_graph(connection, version_id, result, skipped_paths=skipped)
    except Exception:
        connection.rollback()
        _fail(version_id, "unexpected_error", "Analysis failed before the graph was stored.")
        return
    finally:
        connection.close()
    _index_snapshot(version_id)


def _source_texts(version_id: UUID) -> tuple[list[dict[str, str]], list[str], dict[str, str] | None]:
    connection = connect()
    try:
        rows = load_source_files(connection, version_id)
        parsable: list[dict[str, str]] = []
        skipped: list[str] = []
        configs: list[dict[str, str]] = []
        for row in rows:
            if row["disposition"] != "stored" or not isinstance(row["content"], str):
                continue
            path = row["path"]
            if path.endswith(".d.ts"):
                skipped.append(path)
                continue
            if any(path.endswith(suffix) for suffix in PARSABLE_SUFFIXES):
                parsable.append({"path": path, "content": row["content"]})
            elif path.split("/")[-1] in CONFIG_NAMES:
                configs.append({"path": path, "content": row["content"]})
        connection.rollback()
        return parsable, skipped, choose_config(configs)
    finally:
        connection.close()


def choose_config(configs: list[dict[str, str]]) -> dict[str, str] | None:
    """Prefer the shallowest tsconfig.json, then the shallowest jsconfig.json."""

    if not configs:
        return None
    return min(configs, key=lambda item: (item["path"].count("/"), item["path"].endswith("jsconfig.json"), item["path"]))


def _index_snapshot(version_id: UUID) -> None:
    """Keyword chunks and embeddings follow a stored graph and cannot erase it."""

    connection = connect()
    try:
        rebuild_chunks(connection, version_id)
        # Commit the chunks before embedding. Otherwise this transaction holds
        # the version row for the whole model run, and the workspace poll waits.
        connection.commit()
        embed_version(connection, version_id)
    except Exception:
        connection.rollback()
        connection.execute(
            """
            UPDATE repository_versions
            SET embedding_status = 'failed',
                embedding_error = 'Search indexing failed. The graph is still stored.'
            WHERE id = %s
            """,
            (version_id,),
        )
        connection.commit()
    finally:
        connection.close()


def _fail(version_id: UUID, error_code: str, message: str) -> None:
    connection = connect()
    try:
        mark_analysis_failed(connection, version_id, error_code, message)
    finally:
        connection.close()
