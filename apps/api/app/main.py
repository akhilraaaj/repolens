"""RepoLens API.

GET /health reports that this process is running. It does not check PostgreSQL.
Ingestion, analysis, search, and question routes live on their own routers.
"""

import os
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.analysis.routes import router as analysis_router
from app.env import load_local_env
from app.ingestion.routes import open_http_client, router, schedule_in_background
from app.llm.routes import router as provider_router
from app.overview.routes import router as overview_router
from app.workspace.routes import router as workspace_router

load_local_env()

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


class HealthResponse(BaseModel):
    status: Literal["ok"]


def cors_origins() -> list[str]:
    """Return browser origins allowed to read API responses.

    An unset or blank REPOLENS_CORS_ORIGINS uses the local development origins.
    """

    raw = os.environ.get("REPOLENS_CORS_ORIGINS")
    if raw is None or raw.strip() == "":
        return list(DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def health() -> HealthResponse:
    """Report that the API process can serve a request."""

    return HealthResponse(status="ok")


def create_app(origins: list[str] | None = None) -> FastAPI:
    """Build the API application.

    Pass origins in tests so the result does not depend on the process environment.
    """

    application = FastAPI(title="RepoLens API")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins() if origins is None else origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["content-type"],
    )
    application.add_api_route(
        "/health",
        health,
        methods=["GET"],
        response_model=HealthResponse,
    )
    application.include_router(router)
    application.include_router(analysis_router)
    application.include_router(workspace_router)
    application.include_router(overview_router)
    application.include_router(provider_router)
    application.state.schedule = schedule_in_background
    application.state.http_client = open_http_client
    return application


app = create_app()
