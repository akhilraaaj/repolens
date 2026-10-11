"""Workspace endpoints: files, search, questions, and impact."""

import json
import os
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from app.answers.service import iter_answer
from app.answers.tools import get_file
from app.db.connection import DatabaseUnavailable, connect
from app.impact.service import impact_for_name
from app.ingestion.github import GithubClient, GithubRequestError, github_token
from app.ingestion.routes import open_http_client
from app.llm.registry import get_provider
from app.search.embedder import DIMENSIONS, model_name
from app.search.evaluate import evaluate_dataset, golden_set, list_datasets, load_dataset, store_evaluation
from app.search.rerank import rerank_enabled, reranker_name
from app.search.retrieve import search_version, trace_search
from app.search.text import safe_relative_path

router = APIRouter()

# Matches the largest file ingestion stores, so the viewer can show any stored file.
VIEW_LIMIT = 512 * 1024


class QuestionBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = None


class ImpactBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    depth: int = Field(default=2, ge=1, le=3)


class GoldenQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    expected_paths: list[str] = Field(min_length=1, max_length=10)

    @field_validator("expected_paths")
    @classmethod
    def paths_stay_inside(cls, paths: list[str]) -> list[str]:
        return [safe_relative_path(path) for path in paths]


class EvaluationBody(BaseModel):
    dataset: str | None = Field(default=None, min_length=1, max_length=40)
    questions: list[GoldenQuestion] | None = Field(default=None, min_length=1, max_length=20)
    k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def one_source(self) -> "EvaluationBody":
        if (self.dataset is None) == (self.questions is None):
            raise ValueError("Send either a dataset name or a list of questions.")
        return self


@router.get("/config")
def read_config() -> dict:
    chat = bool(os.environ.get("REPOLENS_CHAT_BASE_URL", "").strip() and os.environ.get("REPOLENS_CHAT_MODEL", "").strip())
    try:
        connection = connect()
    except DatabaseUnavailable:
        connection = None
    if connection is not None:
        try:
            chat = get_provider(connection) is not None
        finally:
            connection.close()
    return {
        "embedding_model": model_name(),
        "embedding_dimensions": DIMENSIONS,
        "embedding_endpoint_configured": bool(os.environ.get("REPOLENS_EMBEDDING_BASE_URL", "").strip()),
        "reranker_enabled": rerank_enabled(),
        "reranker_model": reranker_name() if rerank_enabled() else None,
        "chat_configured": chat,
    }


@router.get("/ingestions/{ingestion_id}/files")
def read_file(
    ingestion_id: str,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> JSONResponse:
    version_id = _version_id(ingestion_id)
    if version_id is None:
        return _missing()
    try:
        relative = safe_relative_path(path)
    except ValueError as exc:
        return _error(422, "invalid_path", str(exc))
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        payload = get_file(connection, version_id, relative, start_line, end_line, limit=VIEW_LIMIT)
    finally:
        connection.close()
    if payload is None:
        return _error(404, "file_not_found", "That file is not in the stored snapshot.")
    return JSONResponse(status_code=200, content=payload)


@router.get("/ingestions/{ingestion_id}/search")
def search(ingestion_id: str, q: str = Query(min_length=1, max_length=200), limit: int = Query(default=20, ge=1, le=50)) -> JSONResponse:
    version_id = _version_id(ingestion_id)
    if version_id is None:
        return _missing()
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        results = search_version(connection, version_id, q, limit)
    finally:
        connection.close()
    return JSONResponse(status_code=200, content={"query": q, "results": results})


@router.get("/ingestions/{ingestion_id}/retrieval")
def retrieval_lab(ingestion_id: str, q: str = Query(min_length=1, max_length=200), limit: int = Query(default=5, ge=1, le=10)) -> JSONResponse:
    version_id = _version_id(ingestion_id)
    if version_id is None:
        return _missing()
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        traced = trace_search(connection, version_id, q, limit)
    finally:
        connection.close()
    timings = traced.pop("timings_ms")
    return JSONResponse(
        status_code=200,
        content={
            "query": q,
            "reranker_enabled": rerank_enabled(),
            "strategies": traced,
            "timings_ms": timings,
        },
    )


@router.get("/evaluation/datasets")
def evaluation_datasets() -> dict:
    return {"datasets": list_datasets()}


@router.post("/ingestions/{ingestion_id}/evaluation")
def run_evaluation(ingestion_id: str, body: EvaluationBody) -> JSONResponse:
    version_id = _version_id(ingestion_id)
    if version_id is None:
        return _missing()
    if body.questions is not None:
        dataset = golden_set([item.model_dump() for item in body.questions])
    else:
        try:
            dataset = load_dataset(body.dataset or "")
        except ValueError as exc:
            return _error(422, "unknown_dataset", str(exc))
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        exists = connection.execute("SELECT id FROM repository_versions WHERE id = %s", (version_id,)).fetchone()
        if exists is None:
            return _missing()
        report = evaluate_dataset(connection, version_id, dataset, k=body.k)
        run_id = store_evaluation(connection, version_id, report)
    finally:
        connection.close()
    return JSONResponse(status_code=200, content={"id": run_id, **report})


@router.get("/ingestions/{ingestion_id}/evaluation")
def read_evaluation(ingestion_id: str) -> JSONResponse:
    version_id = _version_id(ingestion_id)
    if version_id is None:
        return _missing()
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        rows = connection.execute(
            """
            SELECT id, dataset_name, k, results, created_at
            FROM evaluation_runs
            WHERE repository_version_id = %s
            ORDER BY created_at DESC
            LIMIT 5
            """,
            (version_id,),
        ).fetchall()
    finally:
        connection.close()
    return JSONResponse(
        status_code=200,
        content={
            "runs": [
                {
                    "id": str(row["id"]),
                    "dataset": row["dataset_name"],
                    "k": row["k"],
                    "summary": row["results"].get("summary", {}),
                    "created_at": row["created_at"].isoformat(),
                }
                for row in rows
            ]
        },
    )


@router.post("/ingestions/{ingestion_id}/questions")
def ask(ingestion_id: str, body: QuestionBody) -> StreamingResponse:
    version_id = _version_id(ingestion_id)
    thread_id = _optional_uuid(body.thread_id)

    def events():
        if version_id is None:
            yield _sse("error", {"message": "That ingestion record does not exist."})
            return
        if body.thread_id and thread_id is None:
            yield _sse("error", {"message": "That conversation id is not valid."})
            return
        try:
            connection = connect()
        except DatabaseUnavailable as exc:
            yield _sse("error", {"message": exc.message})
            return
        try:
            for event, data in iter_answer(connection, version_id, body.question.strip(), thread_id):
                yield _sse(event, data)
        finally:
            connection.close()

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/ingestions/{ingestion_id}/commits")
async def commits(ingestion_id: str) -> JSONResponse:
    version_id = _version_id(ingestion_id)
    if version_id is None:
        return _missing()
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        row = connection.execute(
            """
            SELECT repositories.owner, repositories.name, versions.commit_sha
            FROM repository_versions AS versions
            JOIN repositories ON repositories.id = versions.repository_id
            WHERE versions.id = %s
            """,
            (version_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return _missing()
    try:
        async with open_http_client() as http:
            history = await GithubClient(http, github_token()).commit_history(row["owner"], row["name"], row["commit_sha"])
    except GithubRequestError as exc:
        return _error(exc.status_code, exc.error_code, exc.message)
    return JSONResponse(status_code=200, content={"head": row["commit_sha"], "commits": history})


@router.post("/ingestions/{ingestion_id}/impact")
def impact(ingestion_id: str, body: ImpactBody) -> JSONResponse:
    version_id = _version_id(ingestion_id)
    if version_id is None:
        return _missing()
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        payload = impact_for_name(connection, version_id, body.name.strip(), body.depth)
    finally:
        connection.close()
    if payload is None:
        return _missing()
    return JSONResponse(status_code=200, content=payload)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _optional_uuid(value: str | None) -> UUID | None:
    if value is None or value.strip() == "":
        return None
    return _version_id(value)


def _version_id(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _missing() -> JSONResponse:
    return _error(404, "ingestion_not_found", "That ingestion record does not exist.")


def _error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error_code": error_code, "message": message})
