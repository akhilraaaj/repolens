"""Shared text helpers for search and citations."""

import hashlib
import re


def safe_relative_path(path: str) -> str:
    """Reject paths that could leave the indexed snapshot."""

    if path.strip() == "" or "\\" in path or path.startswith("/"):
        raise ValueError("That file path is not valid.")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("That file path is not valid.")
    return path


def slice_lines(content: str, start_line: int, end_line: int, *, limit: int = 8000) -> str | None:
    lines = content.splitlines()
    if start_line < 1 or start_line > len(lines):
        return None
    end_line = min(end_line, len(lines))
    if end_line < start_line:
        return None
    text = "\n".join(lines[start_line - 1 : end_line])
    if len(text) > limit:
        return text[:limit]
    return text


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def identifiers(text: str) -> list[str]:
    found: list[str] = []
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
        if len(token) < 2 or token.lower() in {
            "the",
            "what",
            "how",
            "does",
            "do",
            "did",
            "this",
            "that",
            "from",
            "with",
            "repository",
            "repo",
            "project",
            "codebase",
            "program",
            "where",
            "start",
        }:
            continue
        if token not in found:
            found.append(token)
    return found[:8]
