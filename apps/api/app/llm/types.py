"""Shared shapes for a chat provider. Keys never appear on these objects' logs."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ModelTurn:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


class ProviderError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
