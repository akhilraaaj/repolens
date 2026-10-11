"""HTTP routes for static analysis."""

import asyncio
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from app.analysis.service import analysis_timeout_seconds, execute_analysis
from app.analysis.store import claim_analysis, load_file_graph, load_graph
from app.db.connection import DatabaseUnavailable, connect
from app.db.store import load_ingestion

router = APIRouter()


@router.post("/ingestions/{ingestion_id}/analysis")
async def start_analysis(ingestion_id: str, request: Request) -> JSONResponse:
    version_id = _version_id(ingestion_id)
    if version_id is None:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    try:
        timeout = analysis_timeout_seconds()
        connection = connect()
    except ValueError as exc:
        return _error(500, "invalid_configuration", str(exc))
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        action = claim_analysis(connection, version_id, stale_after=timedelta(seconds=timeout))
    finally:
        connection.close()
    if action == "missing":
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    if action == "rejected":
        return _error(409, "analysis_not_ready", "Analysis starts after a source snapshot is stored.")
    if action == "run":

        async def work() -> None:
            await asyncio.to_thread(execute_analysis, version_id)

        await request.app.state.schedule(work())
    return _ingestion_response(version_id)


@router.get("/ingestions/{ingestion_id}/graph")
def read_graph(
    ingestion_id: str,
    edge_type: str | None = None,
    file: str | None = None,
    resolution_status: str | None = None,
    limit: int = Query(default=500, ge=1, le=500),
) -> JSONResponse:
    version_id = _version_id(ingestion_id)
    if version_id is None:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        payload = load_graph(
            connection,
            version_id,
            edge_type=edge_type,
            file_path=file,
            resolution_status=resolution_status,
            limit=limit,
        )
    finally:
        connection.close()
    if payload is None:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    return JSONResponse(status_code=200, content=payload)


@router.get("/ingestions/{ingestion_id}/graph/files")
def read_file_graph(ingestion_id: str) -> JSONResponse:
    version_id = _version_id(ingestion_id)
    if version_id is None:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        payload = load_file_graph(connection, version_id)
    finally:
        connection.close()
    if payload is None:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    return JSONResponse(status_code=200, content=payload)


def _ingestion_response(version_id: UUID) -> JSONResponse:
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        payload = load_ingestion(connection, version_id)
    finally:
        connection.close()
    if payload is None:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    status_code = 202 if payload["analysis_status"] == "running" else 200
    return JSONResponse(status_code=status_code, content=payload)


def _version_id(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error_code": error_code, "message": message})
