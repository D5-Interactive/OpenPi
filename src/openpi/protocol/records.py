"""Typed views of the pi RPC records openpi consumes.

Unknown fields are ignored on purpose: pi adds fields, and a new field must not break the
client. Anything not modelled here stays a plain dict at the edge.
"""

from __future__ import annotations

import msgspec


def decode(data: dict, struct_type):
    return msgspec.convert(data, struct_type)


class Model(msgspec.Struct):
    id: str = ""
    provider: str = ""
    name: str = ""
    api: str = ""
    baseUrl: str | None = None
    reasoning: bool = False
    input: list[str] = msgspec.field(default_factory=list)
    contextWindow: int | None = None
    maxTokens: int | None = None
    cost: dict | None = None

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.id}" if self.provider else self.id


class AvailableModels(msgspec.Struct):
    models: list[Model] = msgspec.field(default_factory=list)


class ThinkingLevels(msgspec.Struct):
    levels: list[str] = msgspec.field(default_factory=list)


class State(msgspec.Struct):
    model: Model | None = None
    thinkingLevel: str = "off"
    isStreaming: bool = False
    isCompacting: bool = False
    sessionFile: str | None = None
    sessionId: str = ""
    sessionName: str | None = None
    pendingMessageCount: int = 0
    messageCount: int = 0
    steeringMode: str = ""
    followUpMode: str = ""
    autoCompactionEnabled: bool = True

    # snake_case aliases for call sites; msgspec keeps the wire names above.
    @property
    def thinking_level(self) -> str:
        return self.thinkingLevel

    @property
    def is_streaming(self) -> bool:
        return self.isStreaming

    @property
    def is_compacting(self) -> bool:
        return self.isCompacting

    @property
    def session_id(self) -> str:
        return self.sessionId

    @property
    def session_name(self) -> str | None:
        return self.sessionName

    @property
    def session_file(self) -> str | None:
        return self.sessionFile

    @property
    def pending(self) -> int:
        return self.pendingMessageCount


class ContextUsage(msgspec.Struct):
    tokens: int | None = None
    contextWindow: int | None = None
    percent: float | None = None


class SessionStats(msgspec.Struct):
    sessionFile: str | None = None
    sessionId: str = ""
    userMessages: int = 0
    assistantMessages: int = 0
    toolCalls: int = 0
    toolResults: int = 0
    totalMessages: int = 0
    tokens: dict = msgspec.field(default_factory=dict)
    cost: float = 0.0
    contextUsage: ContextUsage | None = None

    @property
    def context_usage(self) -> ContextUsage | None:
        return self.contextUsage


class Response(msgspec.Struct):
    type: str = ""
    id: str | None = None
    command: str = ""
    success: bool = False
    data: dict | None = None
    error: str | None = None


class Commands(msgspec.Struct):
    commands: list[CommandInfo] = msgspec.field(default_factory=list)


class CommandInfo(msgspec.Struct):
    name: str = ""
    description: str = ""
    source: str = ""


class Entries(msgspec.Struct):
    entries: list[dict] = msgspec.field(default_factory=list)
    leafId: str | None = None


class ExtensionUIRequest(msgspec.Struct):
    id: str = ""
    type: str = ""
    method: str = ""
    title: str = ""
    message: str = ""
    options: list[str] = msgspec.field(default_factory=list)
    placeholder: str = ""
    prefill: str = ""
    timeout: int | None = None
    notifyType: str = "info"
    statusKey: str = ""
    statusText: str | None = None
    widgetKey: str = ""
    widgetLines: list[str] | None = None
    widgetPlacement: str = "aboveEditor"
    text: str = ""

    @property
    def is_dialog(self) -> bool:
        return self.method in ("select", "confirm", "input", "editor")
