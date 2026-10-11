"""Provider settings. The stored API key is never returned."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.db.connection import DatabaseUnavailable, connect
from app.llm.store import public_provider, read_provider, save_provider

router = APIRouter()


class ProviderBody(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


@router.get("/provider")
def read() -> JSONResponse:
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        return JSONResponse(status_code=200, content=public_provider(read_provider(connection)))
    finally:
        connection.close()


@router.post("/provider")
def update(body: ProviderBody) -> JSONResponse:
    try:
        connection = connect()
    except DatabaseUnavailable as exc:
        return _error(503, "database_unavailable", exc.message)
    try:
        provided = body.model_dump(exclude_unset=True)
        payload = save_provider(
            connection,
            provider=body.provider,
            base_url=body.base_url,
            model=body.model,
            api_key=provided.get("api_key"),
            keep_api_key="api_key" not in provided,
        )
    except ValueError as exc:
        return _error(422, "invalid_provider", str(exc))
    finally:
        connection.close()
    return JSONResponse(status_code=200, content=payload)


def _error(status_code: int, error_code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error_code": error_code, "message": message})
