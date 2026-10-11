"""GitHub repository URL allowlist."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


class InvalidRepositoryUrl(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "invalid_url"
        self.message = message


@dataclass(frozen=True)
class ParsedRepositoryUrl:
    owner: str
    name: str
    ref: str | None
    canonical_url: str


def parse_repository_url(value: str) -> ParsedRepositoryUrl:
    """Accept a public GitHub repository URL, optionally with a slash-free ref."""

    candidate = value.strip()
    if not candidate:
        raise InvalidRepositoryUrl("Enter a GitHub repository URL.")

    parts = urlsplit(candidate)
    if parts.scheme != "https" or parts.hostname != "github.com":
        raise InvalidRepositoryUrl("Only https://github.com repository URLs are accepted.")
    if parts.username or parts.password:
        raise InvalidRepositoryUrl("The URL must not include a username or password.")
    if parts.port is not None:
        raise InvalidRepositoryUrl("The URL must not include a port.")
    if parts.query or parts.fragment:
        raise InvalidRepositoryUrl("The URL must not include a query or fragment.")

    segments = [segment for segment in parts.path.split("/") if segment]
    ref: str | None = None
    if len(segments) == 2:
        owner, name = segments
    elif len(segments) == 4 and segments[2] == "tree":
        owner, name, _, ref = segments
        if "/" in ref:
            raise InvalidRepositoryUrl(
                "A /tree URL can only include a ref without slashes. Put branch names that contain slashes in the ref field."
            )
    else:
        raise InvalidRepositoryUrl(
            "Use https://github.com/owner/name, with an optional /tree/ref whose ref contains no slash."
        )

    if name.endswith(".git"):
        name = name[: -len(".git")]
    _validate_name("owner", owner, max_length=39)
    _validate_name("repository", name, max_length=100)
    if ref is not None:
        ref = validate_ref(ref)
    return ParsedRepositoryUrl(
        owner=owner,
        name=name,
        ref=ref,
        canonical_url=f"https://github.com/{owner}/{name}",
    )


def validate_ref(ref: str) -> str:
    candidate = ref.strip()
    if not candidate:
        raise InvalidRepositoryUrl("The ref is empty.")
    if len(candidate) > 255:
        raise InvalidRepositoryUrl("The ref is too long.")
    if any(character in candidate for character in "\r\n\t ?#\\"):
        raise InvalidRepositoryUrl("The ref contains characters that cannot be used in a GitHub request.")
    return candidate


def _validate_name(label: str, value: str, *, max_length: int) -> None:
    if value in {".", ".."} or value.startswith(".") or not _NAME.fullmatch(value):
        raise InvalidRepositoryUrl(f"The {label} contains characters GitHub repository URLs do not use.")
    if len(value) > max_length:
        raise InvalidRepositoryUrl(f"The {label} is too long.")
