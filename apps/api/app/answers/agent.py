"""A bounded, read-only tool loop. The model can look, and it cannot change anything."""

import json

import psycopg
from uuid import UUID

from app.answers.tools import find_symbol, get_file, neighbors, search_code
from app.llm.types import ProviderError, ToolCall
from app.search.text import safe_relative_path

MAX_ROUNDS = 4
MAX_CALLS = 6
RESULT_CHARS = 4000

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search the stored snapshot. Returns file paths and line ranges.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file",
            "description": "Read a stored file between two line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_symbol",
            "description": "Find a function, class, or value by its exact name.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dependents",
            "description": "List symbols that depend on a named symbol, up to three steps away.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "depth": {"type": "integer"}},
                "required": ["name"],
            },
        },
    },
]


def run_tool_loop(connection: psycopg.Connection, version_id: UUID, provider, messages: list[dict]) -> tuple[str, list[dict], list[str]]:
    """Return the model's last prose, a log of tool calls, and the files it opened."""

    log: list[dict] = []
    trace: list[str] = []
    calls = 0
    for _ in range(MAX_ROUNDS):
        try:
            turn = provider.complete(messages, TOOL_SPECS)
        except ProviderError:
            break
        if not turn.tool_calls or calls >= MAX_CALLS:
            return turn.content, log, trace
        messages.append(_assistant_tool_message(turn.content, turn.tool_calls))
        for call in turn.tool_calls:
            if calls >= MAX_CALLS:
                break
            calls += 1
            text, paths = execute_tool(connection, version_id, call.name, call.arguments)
            for path in paths:
                if path not in trace:
                    trace.append(path)
            log.append({"name": call.name, "summary": _summary(call.name, call.arguments, text), "paths": paths})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": text[:RESULT_CHARS]})
    try:
        turn = provider.complete(messages, None)
        return turn.content, log, trace
    except ProviderError:
        return "", log, trace


def execute_tool(connection: psycopg.Connection, version_id: UUID, name: str, arguments: dict) -> tuple[str, list[str]]:
    try:
        if name == "search_code":
            query = _text(arguments.get("query"), 200)
            hits = search_code(connection, version_id, query)[:6]
            paths = []
            rows = []
            for hit in hits:
                if hit["path"] not in paths:
                    paths.append(hit["path"])
                rows.append({"path": hit["path"], "start_line": hit["start_line"], "end_line": hit["end_line"], "snippet": hit["snippet"][:400]})
            return json.dumps(rows), paths
        if name == "get_file":
            path = safe_relative_path(_text(arguments.get("path"), 300))
            start = _line(arguments.get("start_line"))
            end = _line(arguments.get("end_line"))
            opened = get_file(connection, version_id, path, start, end)
            if opened is None:
                return "That file is not in the stored snapshot.", []
            return opened["content"], [opened["path"]]
        if name == "find_symbol":
            symbol_name = _text(arguments.get("name"), 200)
            found = find_symbol(connection, version_id, symbol_name)[:5]
            return json.dumps(found), [item["path"] for item in found]
        if name == "dependents":
            symbol_name = _text(arguments.get("name"), 200)
            matches = find_symbol(connection, version_id, symbol_name)
            if not matches:
                return "No symbol with that name is stored.", []
            depth = arguments.get("depth", 2)
            depth = depth if isinstance(depth, int) else 2
            found = neighbors(connection, version_id, UUID(matches[0]["id"]), incoming=True, depth=depth)
            return json.dumps(found[:12]), [item["path"] for item in found[:12]]
    except ValueError as exc:
        return str(exc), []
    return "That tool is not available.", []


def _assistant_tool_message(content: str, calls: list[ToolCall]) -> dict:
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments)}}
            for call in calls
        ],
    }


def _summary(name: str, arguments: dict, text: str) -> str:
    if name == "search_code":
        return f"search {arguments.get('query', '')}"[:160]
    if name == "get_file":
        return f"read {arguments.get('path', '')}"[:160]
    if name == "find_symbol":
        return f"symbol {arguments.get('name', '')}"[:160]
    if name == "dependents":
        return f"dependents of {arguments.get('name', '')}"[:160]
    return text[:80]


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError("That argument must be text.")
    cleaned = value.strip()
    if cleaned == "" or len(cleaned) > limit:
        raise ValueError("That argument is empty or too long.")
    return cleaned


def _line(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Line numbers must be integers.")
    if value < 1 or value > 100_000:
        raise ValueError("That line number is out of range.")
    return value
