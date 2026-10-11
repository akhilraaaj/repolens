"""OpenAI-compatible chat completions, including Ollama's OpenAI shim and hosted APIs."""

import json
from collections.abc import Iterator

import httpx2

from app.llm.types import ModelTurn, ProviderError, ToolCall

TIMEOUT = httpx2.Timeout(60.0, connect=5.0)


class OpenAICompatible:
    def __init__(self, *, base_url: str, model: str, api_key: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or ""

    def complete(self, messages: list[dict], tools: list[dict] | None = None, timeout: httpx2.Timeout | None = None) -> ModelTurn:
        body: dict = {"model": self.model, "messages": messages, "temperature": 0}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        payload = self._post("/chat/completions", body, timeout)
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            raise ProviderError("The model returned no completion.")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise ProviderError("The model returned no completion.")
        return ModelTurn(content=_text(message.get("content")), tool_calls=_openai_tools(message.get("tool_calls")))

    def stream(self, messages: list[dict]) -> Iterator[str]:
        body = {"model": self.model, "messages": messages, "temperature": 0, "stream": True}
        with httpx2.Client(timeout=TIMEOUT) as client:
            try:
                with client.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers(), json=body) as response:
                    if response.status_code >= 400:
                        raise ProviderError("The model rejected the request.")
                    for line in response.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = payload.get("choices") if isinstance(payload, dict) else None
                        if not isinstance(choices, list) or not choices:
                            continue
                        delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
                        text = _text(delta.get("content")) if isinstance(delta, dict) else ""
                        if text:
                            yield text
            except httpx2.HTTPError as exc:
                raise ProviderError("The model could not be reached.") from exc

    def _post(self, path: str, body: dict, timeout: httpx2.Timeout | None = None) -> dict:
        try:
            response = httpx2.post(f"{self.base_url}{path}", headers=self._headers(), json=body, timeout=timeout or TIMEOUT)
        except httpx2.HTTPError as exc:
            raise ProviderError("The model could not be reached.") from exc
        if response.status_code >= 400:
            raise ProviderError("The model rejected the request.")
        payload = response.json()
        if not isinstance(payload, dict):
            raise ProviderError("The model returned an unexpected response.")
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        return headers


def _arguments(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _openai_tools(value: object) -> list[ToolCall]:
    if not isinstance(value, list):
        return []
    calls = []
    for item in value:
        if not isinstance(item, dict):
            continue
        function = item.get("function") if isinstance(item.get("function"), dict) else {}
        calls.append(
            ToolCall(
                id=item.get("id") if isinstance(item.get("id"), str) else "call",
                name=function.get("name") if isinstance(function.get("name"), str) else "",
                arguments=_arguments(function.get("arguments")),
            )
        )
    return [call for call in calls if call.name]
