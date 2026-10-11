import asyncio

import httpx2
import pytest

from app.ingestion.archive import LimitReached
from app.ingestion.github import GithubClient, GithubRequestError

SHA = "a" * 40


def run(handler, scenario) -> None:
    async def wrapped() -> None:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
            await scenario(GithubClient(http, token=None))

    asyncio.run(wrapped())


def test_repository_and_commit_resolution() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/repos/octo/widget/commits/main":
            return httpx2.Response(200, json={"sha": SHA})
        return httpx2.Response(200, json={"private": False, "default_branch": "main"})

    async def scenario(github: GithubClient) -> None:
        repository = await github.repository("octo", "widget")
        sha = await github.commit_sha("octo", "widget", "main")
        assert repository.default_branch == "main"
        assert sha == SHA

    run(handler, scenario)


def test_private_repository_is_rejected() -> None:
    async def scenario(github: GithubClient) -> None:
        with pytest.raises(GithubRequestError) as caught:
            await github.repository("octo", "widget")
        assert caught.value.error_code == "repository_not_public"

    run(
        lambda _request: httpx2.Response(200, json={"private": True, "default_branch": "main"}),
        scenario,
    )


def test_missing_repository_reports_not_found() -> None:
    async def scenario(github: GithubClient) -> None:
        with pytest.raises(GithubRequestError) as caught:
            await github.repository("octo", "missing")
        assert caught.value.error_code == "repository_not_found"
        assert caught.value.status_code == 404

    run(lambda _request: httpx2.Response(404, json={"message": "Not Found"}), scenario)


def test_unknown_ref_is_distinct_from_a_missing_repository() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "/commits/" in request.url.path:
            return httpx2.Response(404, json={"message": "Not Found"})
        return httpx2.Response(200, json={"private": False, "default_branch": "main"})

    async def scenario(github: GithubClient) -> None:
        with pytest.raises(GithubRequestError) as caught:
            await github.commit_sha("octo", "widget", "missing")
        assert caught.value.error_code == "unknown_ref"

    run(handler, scenario)


def test_rate_limit_includes_the_reset_time() -> None:
    async def scenario(github: GithubClient) -> None:
        with pytest.raises(GithubRequestError) as caught:
            await github.repository("octo", "widget")
        assert caught.value.error_code == "github_rate_limited"
        assert caught.value.status_code == 429
        assert "resets at" in caught.value.message

    run(
        lambda _request: httpx2.Response(
            403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000000"},
            json={"message": "API rate limit exceeded"},
        ),
        scenario,
    )


def test_redirect_to_another_host_is_refused() -> None:
    calls = {"count": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["count"] += 1
        assert request.url.host == "api.github.com"
        return httpx2.Response(302, headers={"location": "https://evil.example/steal"})

    async def scenario(github: GithubClient) -> None:
        with pytest.raises(GithubRequestError) as caught:
            await github.repository("octo", "widget")
        assert caught.value.error_code == "invalid_redirect"
        assert calls["count"] == 1

    run(handler, scenario)


def test_archive_download_stops_past_the_byte_limit() -> None:
    async def scenario(github: GithubClient) -> None:
        with pytest.raises(LimitReached, match="download limit"):
            await github.archive("octo", "widget", SHA, max_bytes=3)

    run(lambda _request: httpx2.Response(200, content=b"abcdef"), scenario)


def test_commit_history_keeps_parents_and_the_first_message_line() -> None:
    parent = "b" * 40
    other = "c" * 40

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.params["sha"] == SHA
        assert request.url.params["per_page"] == "40"
        return httpx2.Response(
            200,
            json=[
                {
                    "sha": SHA,
                    "commit": {"message": "Merge branches\n\nDetails stay off the graph.", "author": {"name": "Ada", "date": "2026-10-01T00:00:00Z"}},
                    "parents": [{"sha": parent}, {"sha": other}, {"sha": "not-a-sha"}],
                },
                {"sha": "short", "commit": {"message": "skip"}},
            ],
        )

    async def scenario(github: GithubClient) -> None:
        history = await github.commit_history("octo", "widget", SHA)
        assert history == [
            {
                "sha": SHA,
                "message": "Merge branches",
                "author": "Ada",
                "committed_at": "2026-10-01T00:00:00Z",
                "parents": [parent, other],
            }
        ]

    run(handler, scenario)
