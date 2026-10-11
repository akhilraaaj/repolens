"""HTTP route for the Repo Brief."""

from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.connection import DatabaseUnavailable, connect
from app.overview.docs import build_documentation
from app.overview.service import build_overview

router = APIRouter()


@router.get("/ingestions/{ingestion_id}/overview")
def read_overview(ingestion_id: str) -> JSONResponse:
    try:
        version_id = UUID(ingestion_id)
    except ValueError:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        payload = build_overview(connection, version_id)
    finally:
        connection.close()
    if payload is None:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    return JSONResponse(status_code=200, content=payload)


@router.get("/ingestions/{ingestion_id}/documentation")
def read_documentation(ingestion_id: str) -> JSONResponse:
    try:
        version_id = UUID(ingestion_id)
    except ValueError:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        payload = build_documentation(connection, version_id)
    finally:
        connection.close()
    if payload is None:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    return JSONResponse(status_code=200, content=payload)


def _error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error_code": error_code, "message": message})
