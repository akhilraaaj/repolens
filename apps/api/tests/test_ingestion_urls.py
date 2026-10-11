import pytest

from app.ingestion.filters import skip_reason_for_path
from app.ingestion.urls import InvalidRepositoryUrl, parse_repository_url


@pytest.mark.parametrize(
    ("value", "owner", "name", "ref"),
    [
        ("https://github.com/Octo/Widget", "Octo", "Widget", None),
        ("https://github.com/Octo/Widget/", "Octo", "Widget", None),
        ("https://github.com/Octo/Widget.git", "Octo", "Widget", None),
        ("https://github.com/Octo/Widget/tree/main", "Octo", "Widget", "main"),
    ],
)
def test_parse_supported_github_urls(value: str, owner: str, name: str, ref: str | None) -> None:
    parsed = parse_repository_url(value)

    assert parsed.owner == owner
    assert parsed.name == name
    assert parsed.ref == ref
    assert parsed.canonical_url == "https://github.com/Octo/Widget"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://github.com/Octo/Widget",
        "https://gitlab.com/Octo/Widget",
        "https://github.com/Octo/Widget?ref=main",
        "https://github.com/Octo/Widget#readme",
        "https://github.com:443/Octo/Widget",
        "https://user:token@github.com/Octo/Widget",
        "https://github.com/Octo/Widget/tree/feature/sidebar",
        "https://github.com/Octo/Widget/blob/main/README.md",
        "https://github.com/../Widget",
        "https://github.com/.hidden/Widget",
    ],
)
def test_parse_rejects_unsupported_urls(value: str) -> None:
    with pytest.raises(InvalidRepositoryUrl) as caught:
        parse_repository_url(value)

    assert caught.value.error_code == "invalid_url"


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("src/app.ts", None),
        ("node_modules/pkg/index.js", "dependency"),
        ("packages/web/node_modules/pkg/index.js", "dependency"),
        (".git/config", "dependency"),
        ("dist/index.js", "generated"),
        ("src/app.min.js", "generated"),
        ("src/app.js.map", "generated"),
        ("assets/logo.png", "binary"),
    ],
)
def test_skip_reason_for_path(path: str, reason: str | None) -> None:
    assert skip_reason_for_path(path) == reason
