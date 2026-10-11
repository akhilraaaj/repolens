"""Ollama's native chat API. The OpenAI-compatible shim is the other provider."""

import json
from collections.abc import Iterator

import httpx2

from app.llm.openai_compatible import _arguments
from app.llm.types import ModelTurn, ProviderError, ToolCall

TIMEOUT = httpx2.Timeout(120.0, connect=5.0)


class Ollama:
    def __init__(self, *, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete(self, messages: list[dict], tools: list[dict] | None = None, timeout: httpx2.Timeout | None = None) -> ModelTurn:
        body: dict = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            body["tools"] = tools
        payload = self._post(body, timeout)
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict):
            raise ProviderError("Ollama returned no message.")
        content = message.get("content") if isinstance(message.get("content"), str) else ""
        return ModelTurn(content=content, tool_calls=_ollama_tools(message.get("tool_calls")))

    def stream(self, messages: list[dict]) -> Iterator[str]:
        body = {"model": self.model, "messages": messages, "stream": True}
        with httpx2.Client(timeout=TIMEOUT) as client:
            try:
                with client.stream("POST", f"{self.base_url}/api/chat", json=body) as response:
                    if response.status_code >= 400:
                        raise ProviderError("Ollama rejected the request.")
                    for line in response.iter_lines():
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        message = payload.get("message") if isinstance(payload, dict) else None
                        content = message.get("content") if isinstance(message, dict) else ""
                        if isinstance(content, str) and content:
                            yield content
                        if isinstance(payload, dict) and payload.get("done") is True:
                            break
            except httpx2.HTTPError as exc:
                raise ProviderError("Ollama could not be reached.") from exc

    def _post(self, body: dict, timeout: httpx2.Timeout | None = None) -> dict:
        try:
            response = httpx2.post(f"{self.base_url}/api/chat", json=body, timeout=timeout or TIMEOUT)
        except httpx2.HTTPError as exc:
            raise ProviderError("Ollama could not be reached.") from exc
        if response.status_code >= 400:
            raise ProviderError("Ollama rejected the request.")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ProviderError("Ollama returned an unexpected response.")
        return payload


def _ollama_tools(value: object) -> list[ToolCall]:
    if not isinstance(value, list):
        return []
    calls = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        function = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = function.get("name")
        if not isinstance(name, str) or name == "":
            continue
        calls.append(ToolCall(id=f"call-{index}", name=name, arguments=_arguments(function.get("arguments"))))
    return calls
