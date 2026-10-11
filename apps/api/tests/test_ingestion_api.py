from datetime import datetime, timedelta, timezone

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.db.connection import connect
from app.main import create_app
from tests.test_ingestion_archive import archive_bytes

SHA = "a" * 40
DATABASE_URL = "postgresql://localhost:5432/repolens_test"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    connection = connect()
    connection.execute("TRUNCATE repositories CASCADE")
    connection.commit()
    connection.close()

    application = create_app(origins=["http://localhost:3000", "http://127.0.0.1:3000"])

    async def inline(work):
        await work

    application.state.schedule = inline
    calls = {"archive": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.host == "codeload.github.com":
            calls["archive"] += 1
            return httpx2.Response(
                200,
                content=archive_bytes(
                    {
                        "src/index.ts": b"export const value = 1;\n",
                        "node_modules/pkg/index.js": b"module.exports = 1;\n",
                    }
                ),
            )
        if "/commits/" in request.url.path:
            return httpx2.Response(200, json={"sha": SHA})
        if request.url.path == "/repos/octo/widget":
            return httpx2.Response(200, json={"private": False, "default_branch": "main"})
        return httpx2.Response(404, json={"message": "Not Found"})

    def http_client() -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))

    application.state.http_client = http_client
    application.state.archive_calls = calls
    return application


def test_invalid_url_does_not_create_a_record(api) -> None:
    response = TestClient(api).post("/ingestions", json={"url": "https://example.com/octo/widget"})

    assert response.status_code == 422
    assert response.json()["error_code"] == "invalid_url"
    connection = connect()
    count = connection.execute("SELECT count(*) AS count FROM repositories").fetchone()
    connection.close()
    assert count["count"] == 0


def test_ingestion_stores_one_version_and_a_manifest(api) -> None:
    client = TestClient(api)
    first = client.post("/ingestions", json={"url": "https://github.com/octo/widget"})
    second = client.post("/ingestions", json={"url": "https://github.com/octo/widget", "ref": "main"})

    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "completed_with_skips"
    assert body["analysis_status"] == "not_started"
    assert body["commit_sha"] == SHA
    assert body["stored_count"] == 1
    assert body["skipped_count"] == 1
    stored = next(item for item in body["files"] if item["disposition"] == "stored")
    assert stored["path"] == "src/index.ts"
    assert "content" not in stored
    assert second.status_code == 200
    assert second.json()["id"] == body["id"]
    assert api.state.archive_calls["archive"] == 1

    found = client.get(f"/ingestions/{body['id']}")
    assert found.status_code == 200
    assert found.json()["commit_sha"] == SHA


def test_rate_limit_is_returned_before_a_version_is_stored(api) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            403,
            headers={"x-ratelimit-remaining": "0", "retry-after": "30"},
            json={"message": "API rate limit exceeded"},
        )

    api.state.http_client = lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    response = TestClient(api).post("/ingestions", json={"url": "https://github.com/octo/widget"})

    assert response.status_code == 429
    assert response.json()["error_code"] == "github_rate_limited"
    connection = connect()
    count = connection.execute("SELECT count(*) AS count FROM repository_versions").fetchone()
    connection.close()
    assert count["count"] == 0


def test_failed_attempt_can_be_retried_without_a_second_version(api) -> None:
    client = TestClient(api)
    created = client.post("/ingestions", json={"url": "https://github.com/octo/widget"})
    version_id = created.json()["id"]
    connection = connect()
    connection.execute(
        """
        UPDATE repository_versions
        SET status = 'failed', error_code = 'github_unavailable', started_at = %s
        WHERE id = %s
        """,
        (datetime.now(timezone.utc) - timedelta(hours=1), version_id),
    )
    connection.commit()
    connection.close()

    retried = client.post("/ingestions", json={"url": "https://github.com/octo/widget"})

    assert retried.status_code == 200
    assert retried.json()["id"] == version_id
    assert retried.json()["status"] == "completed_with_skips"
    connection = connect()
    count = connection.execute("SELECT count(*) AS count FROM repository_versions").fetchone()
    connection.close()
    assert count["count"] == 1


def test_missing_ingestion_returns_404(api) -> None:
    response = TestClient(api).get("/ingestions/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error_code"] == "ingestion_not_found"


def test_entry_limit_keeps_files_classified_before_the_stop(api, monkeypatch) -> None:
    monkeypatch.setenv("REPOLENS_MAX_ENTRIES", "1")

    response = TestClient(api).post("/ingestions", json={"url": "https://github.com/octo/widget"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "limit_exceeded"
    assert body["stored_count"] == 1
    assert [item["path"] for item in body["files"]] == ["src/index.ts"]


def test_database_unavailable_keeps_health_independent(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://127.0.0.1:1/repolens")
    application = create_app()
    client = TestClient(application)

    health = client.get("/health")
    ingestion = client.post("/ingestions", json={"url": "https://github.com/octo/widget"})

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ingestion.status_code == 503
    assert ingestion.json()["error_code"] == "database_unavailable"
