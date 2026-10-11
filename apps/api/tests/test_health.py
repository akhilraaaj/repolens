from fastapi.testclient import TestClient

from app.main import HealthResponse, cors_origins, create_app, health

client = TestClient(create_app(origins=["http://localhost:3000", "http://127.0.0.1:3000"]))


def test_health_function_returns_ok() -> None:
    assert health() == HealthResponse(status="ok")


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_path_returns_404() -> None:
    response = client.get("/missing")

    assert response.status_code == 404


def test_allowed_origin_receives_cors_header() -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_preflight_allows_json_post_from_the_local_page() -> None:
    response = client.options(
        "/ingestions",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "POST" in response.headers.get("access-control-allow-methods", "")
    assert "content-type" in response.headers.get("access-control-allow-headers", "").lower()


def test_disallowed_origin_does_not_receive_cors_header() -> None:
    response = client.get("/health", headers={"Origin": "http://evil.example"})

    assert response.headers.get("access-control-allow-origin") is None


def test_cors_origins_use_defaults_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("REPOLENS_CORS_ORIGINS", raising=False)

    assert cors_origins() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_cors_origins_use_defaults_when_blank(monkeypatch) -> None:
    monkeypatch.setenv("REPOLENS_CORS_ORIGINS", "   ")

    assert cors_origins() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_cors_origins_parse_comma_separated_values(monkeypatch) -> None:
    monkeypatch.setenv(
        "REPOLENS_CORS_ORIGINS",
        " http://localhost:3000, http://example.com ",
    )

    assert cors_origins() == ["http://localhost:3000", "http://example.com"]


def test_cors_origins_skip_empty_entries(monkeypatch) -> None:
    monkeypatch.setenv("REPOLENS_CORS_ORIGINS", "http://localhost:3000,, ,")

    assert cors_origins() == ["http://localhost:3000"]
