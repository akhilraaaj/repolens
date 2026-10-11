"""GitHub API calls used to resolve a commit and download its archive."""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urljoin, urlsplit

import httpx2

from app.ingestion.archive import LimitReached

ALLOWED_HOSTS = {"api.github.com", "codeload.github.com"}
_MAX_REDIRECTS = 3


class GithubRequestError(Exception):
    def __init__(self, error_code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class RepositoryMetadata:
    owner: str
    name: str
    default_branch: str
    private: bool


def github_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    return token or None


class GithubClient:
    def __init__(self, http: httpx2.AsyncClient, token: str | None) -> None:
        self._http = http
        self._token = token

    async def repository(self, owner: str, name: str) -> RepositoryMetadata:
        payload = await self._get_json(f"https://api.github.com/repos/{owner}/{name}")
        if payload.get("private") is True:
            raise GithubRequestError(
                "repository_not_public",
                "This repository is not public.",
                403,
            )
        default_branch = payload.get("default_branch")
        if not isinstance(default_branch, str) or not default_branch:
            raise GithubRequestError(
                "github_unavailable",
                "GitHub did not return the repository's default branch.",
                502,
            )
        return RepositoryMetadata(
            owner=owner,
            name=name,
            default_branch=default_branch,
            private=False,
        )

    async def commit_sha(self, owner: str, name: str, ref: str) -> str:
        encoded_ref = quote(ref, safe="")
        payload = await self._get_json(
            f"https://api.github.com/repos/{owner}/{name}/commits/{encoded_ref}"
        )
        sha = payload.get("sha")
        if not isinstance(sha, str) or len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
            raise GithubRequestError(
                "github_unavailable",
                "GitHub did not return a commit SHA.",
                502,
            )
        return sha

    async def archive(self, owner: str, name: str, sha: str, max_bytes: int) -> bytes:
        url = f"https://codeload.github.com/{owner}/{name}/tar.gz/{sha}"
        response = await self._request("GET", url)
        try:
            self._raise_for_status(response, archive=True, url=url)
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise LimitReached(
                        f"The archive exceeds the {max_bytes} byte download limit."
                    )
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            await response.aclose()

    async def commit_history(self, owner: str, name: str, sha: str) -> list[dict]:
        encoded = quote(sha, safe="")
        payload = await self._read_json(
            f"https://api.github.com/repos/{owner}/{name}/commits?sha={encoded}&per_page=40"
        )
        return parse_commits(payload)

    async def _read_json(self, url: str):
        response = await self._request("GET", url)
        try:
            self._raise_for_status(response, archive=False, url=url)
            return response.json()
        finally:
            await response.aclose()

    async def _get_json(self, url: str) -> dict:
        payload = await self._read_json(url)
        if not isinstance(payload, dict):
            raise GithubRequestError(
                "github_unavailable",
                "GitHub returned a response that was not a JSON object.",
                502,
            )
        return payload

    async def _request(self, method: str, url: str) -> httpx2.Response:
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            host = urlsplit(current).hostname
            if host not in ALLOWED_HOSTS:
                raise GithubRequestError(
                    "invalid_redirect",
                    f"Refused a GitHub redirect to {host or 'an unknown host'}.",
                    502,
                )
            try:
                response = await self._http.request(
                    method,
                    current,
                    headers=self._headers(host),
                    follow_redirects=False,
                )
            except httpx2.TransportError as exc:
                raise GithubRequestError(
                    "github_unavailable",
                    "The GitHub request failed. Try again.",
                    503,
                ) from exc
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                await response.aclose()
                if not location:
                    raise GithubRequestError(
                        "github_unavailable",
                        "GitHub sent a redirect without a destination.",
                        502,
                    )
                current = urljoin(current, location)
                continue
            return response
        raise GithubRequestError("github_unavailable", "GitHub sent too many redirects.", 502)

    def _headers(self, host: str) -> dict[str, str]:
        headers = {"User-Agent": "repolens", "Accept": "application/vnd.github+json"}
        if host == "api.github.com":
            headers["X-GitHub-Api-Version"] = "2022-11-28"
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _raise_for_status(self, response: httpx2.Response, *, archive: bool, url: str) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        body = ""
        if response.status_code in {403, 429}:
            body = response.text.lower()
        rate_limited = response.status_code == 429 or (
            response.status_code == 403 and (remaining == "0" or "rate limit" in body)
        )
        if rate_limited:
            raise GithubRequestError("github_rate_limited", _rate_limit_message(response), 429)
        if response.status_code == 404:
            if archive:
                raise GithubRequestError(
                    "archive_unavailable",
                    "GitHub could not provide the archive for that commit.",
                    404,
                )
            if "/commits/" in url:
                raise GithubRequestError(
                    "unknown_ref",
                    "GitHub could not resolve that ref.",
                    404,
                )
            raise GithubRequestError(
                "repository_not_found",
                "GitHub returned 404. The repository may be missing, private, or renamed.",
                404,
            )
        if response.status_code >= 400:
            raise GithubRequestError(
                "github_unavailable",
                f"GitHub returned HTTP {response.status_code}.",
                502,
            )


def parse_commits(payload: object) -> list[dict]:
    """Keep a bounded, validated slice of GitHub's commit list."""

    if not isinstance(payload, list):
        raise GithubRequestError(
            "github_unavailable",
            "GitHub did not return a commit list.",
            502,
        )
    commits = []
    for item in payload[:40]:
        parsed = _parse_commit(item)
        if parsed is not None:
            commits.append(parsed)
    if not commits:
        raise GithubRequestError(
            "github_unavailable",
            "GitHub did not return any commits.",
            502,
        )
    return commits


def _parse_commit(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    sha = item.get("sha")
    if not _is_sha(sha):
        return None
    commit = item.get("commit")
    if not isinstance(commit, dict):
        return None
    message = commit.get("message")
    if not isinstance(message, str) or message.strip() == "":
        return None
    author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
    account = item.get("author") if isinstance(item.get("author"), dict) else {}
    name = author.get("name") if isinstance(author.get("name"), str) else account.get("login")
    when = author.get("date") if isinstance(author.get("date"), str) else None
    parents = []
    for parent in item.get("parents") or []:
        if isinstance(parent, dict) and _is_sha(parent.get("sha")):
            parents.append(parent["sha"])
    return {
        "sha": sha,
        "message": message.splitlines()[0][:140],
        "author": name[:80] if isinstance(name, str) and name.strip() else "unknown",
        "committed_at": when,
        "parents": parents[:2],
    }


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def _rate_limit_message(response: httpx2.Response) -> str:
    message = "GitHub rate limit reached."
    reset = response.headers.get("x-ratelimit-reset")
    if reset and reset.isdigit():
        moment = datetime.fromtimestamp(int(reset), timezone.utc).isoformat()
        return f"{message} The quota resets at {moment}."
    retry_after = response.headers.get("retry-after")
    if retry_after:
        return f"{message} Retry after {retry_after} seconds."
    return message
