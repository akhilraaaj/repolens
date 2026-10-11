"""HTTP routes for repository ingestion."""

import asyncio
from collections.abc import Awaitable
from uuid import UUID

import httpx2
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.analysis.active import STALE_EMBEDDING, is_active
from app.db.connection import DatabaseUnavailable, connect
from app.db.store import load_ingestion
from app.ingestion.github import GithubClient, GithubRequestError, github_token
from app.ingestion.limits import InvalidIngestionConfiguration, limits_from_env
from app.ingestion.service import execute, prepare_version
from app.ingestion.urls import InvalidRepositoryUrl, parse_repository_url, validate_ref

router = APIRouter()


class IngestionRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    ref: str | None = None


def open_http_client() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(timeout=httpx2.Timeout(30.0))


async def schedule_in_background(work: Awaitable[None]) -> None:
    task = asyncio.create_task(work)
    task.add_done_callback(_observe_task)


def _observe_task(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    task.exception()


@router.post("/ingestions")
async def create_ingestion(body: IngestionRequest, request: Request) -> JSONResponse:
    try:
        parsed = parse_repository_url(body.url)
        if body.ref is not None:
            explicit_ref = validate_ref(body.ref)
        else:
            explicit_ref = None
        limits = limits_from_env()
    except InvalidRepositoryUrl as exc:
        return _error(422, exc.error_code, exc.message)
    except InvalidIngestionConfiguration as exc:
        return _error(500, "invalid_configuration", exc.message)

    try:
        connect().close()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)

    try:
        async with request.app.state.http_client() as http:
            github = GithubClient(http, github_token())
            try:
                repository = await github.repository(parsed.owner, parsed.name)
                requested_ref = explicit_ref or parsed.ref or repository.default_branch
                requested_ref = validate_ref(requested_ref)
                commit_sha = await github.commit_sha(parsed.owner, parsed.name, requested_ref)
            except InvalidRepositoryUrl as exc:
                return _error(422, exc.error_code, exc.message)
            except GithubRequestError as exc:
                return _error(exc.status_code, exc.error_code, exc.message)
    except GithubRequestError as exc:
        return _error(exc.status_code, exc.error_code, exc.message)

    try:
        version_id, action = prepare_version(
            owner=parsed.owner,
            name=parsed.name,
            canonical_url=parsed.canonical_url,
            default_branch=repository.default_branch,
            commit_sha=commit_sha,
            requested_ref=requested_ref,
            limits=limits,
        )
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)

    if action == "run":
        token = github_token()

        async def work() -> None:
            async with request.app.state.http_client() as http:
                await execute(version_id, GithubClient(http, token), limits)

        await request.app.state.schedule(work())

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
    status_code = 202 if payload["status"] == "running" else 200
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/ingestions/{ingestion_id}")
def read_ingestion(ingestion_id: str) -> JSONResponse:
    try:
        version_id = UUID(ingestion_id)
    except ValueError:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        _release_orphaned_embedding(connection, version_id)
        payload = load_ingestion(connection, version_id)
    finally:
        connection.close()
    if payload is None:
        return _error(404, "ingestion_not_found", "That ingestion record does not exist.")
    return JSONResponse(status_code=200, content=payload)


def _release_orphaned_embedding(connection, version_id: UUID) -> None:
    if is_active(version_id):
        return
    connection.execute(
        """
        UPDATE repository_versions
        SET embedding_status = 'failed', embedding_error = %s
        WHERE id = %s AND embedding_status = 'running'
        """,
        (STALE_EMBEDDING, version_id),
    )
    connection.commit()


def _error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error_code": error_code, "message": message})
