"""Turn pi's session events into a flat, renderable list of blocks.

Pure Python: no Qt import here, so it is testable headless and reusable for backfill from
session entries. Each block has a stable uid the UI uses to update a widget in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NOTICE_REASONS = {
    "manual": "compaction requested",
    "threshold": "context nearly full",
    "overflow": "context overflowed the model window",
}


@dataclass(slots=True)
class Block:
    uid: str
    kind: str  # user | text | thinking | tool | bash | notice
    text: str = ""
    name: str = ""
    args: dict = field(default_factory=dict)
    result: str = ""
    is_error: bool = False
    duration_ms: int | None = None
    meta: dict = field(default_factory=dict)


def content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def _result_text(result) -> str:
    if isinstance(result, dict):
        return content_text(result.get("content"))
    return content_text(result)


class Transcript:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.streaming = False
        self.busy = False
        self.queued = (0, 0)
        self.error = ""
        self._seq = 0
        self._msg_start = 0
        self._message_blocks: list[Block] = []
        self._by_index: dict[int, Block] = {}
        self._tools: dict[str, Block] = {}

    # -- helpers ---------------------------------------------------------

    def _uid(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq}"

    def _new(self, kind: str, **kwargs) -> Block:
        block = Block(uid=self._uid(kind[0]), kind=kind, **kwargs)
        self.blocks.append(block)
        self._message_blocks.append(block)
        return block

    def _tool(self, call_id: str, name: str = "", args: dict | None = None) -> Block:
        block = self._tools.get(call_id)
        if block is None:
            block = Block(uid=f"t{call_id}", kind="tool", name=name, args=args or {}, meta={"tool_call_id": call_id})
            self.blocks.append(block)
            self._tools[call_id] = block
        else:
            if name:
                block.name = name
            if args:
                block.args = args
        return block

    def _index_block(self, content_index: int, kind: str) -> Block:
        block = self._by_index.get(content_index)
        if block is None or block.kind != kind:
            block = self._new(kind)
            self._by_index[content_index] = block
        return block

    def notice(self, text: str, is_error: bool = False) -> Block:
        block = Block(uid=self._uid("n"), kind="notice", text=text, is_error=is_error)
        self.blocks.append(block)
        self._message_blocks.append(block)
        return block

    # -- event entry point ----------------------------------------------

    def apply(self, event: dict) -> None:
        kind = event.get("type")
        handler = getattr(self, f"_on_{kind}", None)
        if handler is not None:
            handler(event)

    # -- events ----------------------------------------------------------

    def _on_agent_start(self, event):
        self.busy = True
        self.error = ""

    def _on_turn_start(self, event):
        self.busy = True

    def _on_agent_settled(self, event):
        self.busy = False
        self.streaming = False

    def _on_message_start(self, event):
        message = event.get("message") or {}
        role = message.get("role")
        if role == "user":
            self._new("user", text=content_text(message.get("content")))
        elif role == "toolResult":
            self._tool(message.get("toolCallId", ""), message.get("toolName", ""))
            self._tools[message.get("toolCallId", "")].result = content_text(message.get("content"))
            self._tools[message.get("toolCallId", "")].is_error = bool(message.get("isError"))
        elif role == "assistant":
            self.streaming = True
            self.busy = True
            self._msg_start = len(self.blocks)
            self._message_blocks = []
            self._by_index = {}

    def _on_message_update(self, event):
        update = event.get("assistantMessageEvent") or {}
        kind = update.get("type")
        index = update.get("contentIndex", 0)
        if kind == "text_delta":
            self._index_block(index, "text").text += update.get("delta", "")
        elif kind == "text_end":
            self._index_block(index, "text").text = update.get("content", "")
        elif kind == "thinking_delta":
            self._index_block(index, "thinking").text += update.get("delta", "")
        elif kind == "thinking_end":
            self._index_block(index, "thinking").text = update.get("content", "")
        elif kind == "toolcall_end":
            call = update.get("toolCall") or {}
            self._tool(call.get("id", ""), call.get("name", ""), call.get("arguments") or {})

    def _on_message_end(self, event):
        message = event.get("message") or {}
        if message.get("role") != "assistant":
            return
        content = message.get("content") or []
        replace_from = self._msg_start
        kept: list[Block] = []
        for index, part in enumerate(content):
            ptype = part.get("type")
            if ptype == "text":
                old = self._by_index.get(index)
                block = old if old is not None and old.kind == "text" else self._new("text")
                block.text = part.get("text", "")
                kept.append(block)
            elif ptype == "thinking":
                old = self._by_index.get(index)
                block = old if old is not None and old.kind == "thinking" else self._new("thinking")
                block.text = part.get("thinking", "")
                kept.append(block)
            elif ptype == "toolCall":
                block = self._tool(part.get("id", ""), part.get("name", ""),
                                   part.get("arguments") or {})
                block.meta["orphan"] = True
                kept.append(block)
        self.blocks[replace_from:] = kept
        self._message_blocks = kept
        self.streaming = False
        self.error = message.get("errorMessage") or ""
        if message.get("stopReason") == "error" or self.error:
            self.notice(f"pi: {self.error or 'the model returned an error'}", is_error=True)
        elif message.get("stopReason") == "aborted":
            self.notice("Turn aborted")

    def _on_tool_execution_start(self, event):
        self._tool(event.get("toolCallId", ""), event.get("toolName", ""),
                   event.get("args") or {})

    def _on_tool_execution_update(self, event):
        block = self._tool(event.get("toolCallId", ""), event.get("toolName", ""))
        block.result = _result_text(event.get("partialResult"))

    def _on_tool_execution_end(self, event):
        block = self._tool(event.get("toolCallId", ""), event.get("toolName", ""))
        block.result = _result_text(event.get("result"))
        block.is_error = bool(event.get("isError"))
        block.duration_ms = event.get("durationMs")

    def _on_queue_update(self, event):
        self.queued = (len(event.get("steering") or []), len(event.get("followUp") or []))

    def _on_compaction_start(self, event):
        reason = event.get("reason", "")
        self.notice(f"Compacting context ({NOTICE_REASONS.get(reason, reason or 'compaction')})")

    def _on_compaction_end(self, event):
        if event.get("aborted"):
            self.notice("Compaction aborted", is_error=True)
        elif event.get("errorMessage"):
            self.notice(f"Compaction failed: {event['errorMessage']}", is_error=True)
        else:
            self.notice("Context compacted")

    def _on_auto_retry_start(self, event):
        self.notice(f"Retrying ({event.get('attempt')}/{event.get('maxAttempts')}): "
                    f"{event.get('errorMessage', '')}".strip())

    def _on_auto_retry_end(self, event):
        if not event.get("success"):
            self.notice(f"Retries failed: {event.get('finalError', '')}", is_error=True)

    def _on_extension_error(self, event):
        self.notice(f"Extension error in {event.get('event', 'handler')}: "
                    f"{event.get('error', '')}", is_error=True)

    def _on_bash_execution_update(self, event):
        bid = event.get("id", "")
        block = next((b for b in self.blocks if b.kind == "bash" and b.uid == f"bash-{bid}"), None)
        if block is None:
            block = Block(uid=f"bash-{bid}", kind="bash")
            self.blocks.append(block)
        block.result += event.get("delta", "")

    # -- backfill --------------------------------------------------------

    @classmethod
    def from_entries(cls, entries: list[dict]) -> "Transcript":
        t = cls()
        for entry in entries:
            kind = entry.get("type")
            if kind == "message":
                message = entry.get("message") or {}
                role = message.get("role")
                if role == "user":
                    t.blocks.append(Block(uid=t._uid("u"), kind="user",
                                          text=content_text(message.get("content"))))
                elif role == "toolResult":
                    call_id = message.get("toolCallId", "")
                    block = t._tool(call_id, message.get("toolName", ""))
                    block.result = content_text(message.get("content"))
                    block.is_error = bool(message.get("isError"))
                elif role == "assistant":
                    for part in message.get("content") or []:
                        ptype = part.get("type")
                        if ptype == "text":
                            t.blocks.append(Block(uid=t._uid("x"), kind="text",
                                                  text=part.get("text", "")))
                        elif ptype == "thinking":
                            t.blocks.append(Block(uid=t._uid("k"), kind="thinking",
                                                  text=part.get("thinking", "")))
                        elif ptype == "toolCall":
                            t._tool(part.get("id", ""), part.get("name", ""),
                                    part.get("arguments") or {})
            elif kind == "compaction":
                t.blocks.append(Block(uid=t._uid("n"), kind="notice",
                                      text=f"Context compacted ({entry.get('tokensBefore', '?')} tokens before)"))
            elif kind == "branch_summary":
                t.blocks.append(Block(uid=t._uid("n"), kind="notice",
                                      text=f"Branched: {entry.get('summary', '')}".strip()))
            elif kind == "custom_message" and entry.get("display"):
                t.blocks.append(Block(uid=t._uid("c"), kind="notice",
                                      text=content_text(entry.get("content"))))
        return t
