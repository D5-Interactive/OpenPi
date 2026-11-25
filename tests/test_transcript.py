from openpi.pi.transcript import Transcript


def delta(text, index=0):
    return {"type": "message_update",
            "assistantMessageEvent": {"type": "text_delta", "contentIndex": index, "delta": text}}


def test_text_deltas_accumulate_and_message_end_is_authoritative():
    t = Transcript()
    t.apply({"type": "message_start", "message": {"role": "user", "content": "hi", "timestamp": 1}})
    t.apply({"type": "turn_start"})
    t.apply({"type": "message_start",
             "message": {"role": "assistant", "content": [], "stopReason": "pending", "timestamp": 2}})
    t.apply(delta("Hel"))
    t.apply(delta("lo"))
    assert [b.kind for b in t.blocks] == ["user", "text"]
    assert t.blocks[1].text == "Hello"
    t.apply({"type": "message_end",
             "message": {"role": "assistant", "content": [{"type": "text", "text": "Hello!"}],
                         "usage": {}, "stopReason": "stop", "timestamp": 2}})
    assert t.blocks[1].text == "Hello!"
    assert t.streaming is False


def test_thinking_and_text_become_separate_blocks_in_order():
    t = Transcript()
    t.apply({"type": "message_start",
             "message": {"role": "assistant", "content": [], "stopReason": "pending", "timestamp": 1}})
    t.apply({"type": "message_update", "assistantMessageEvent":
             {"type": "thinking_delta", "contentIndex": 0, "delta": "the queue drops it"}})
    t.apply(delta("Fixed it.", 1))
    assert [b.kind for b in t.blocks] == ["thinking", "text"]
    assert t.blocks[0].text == "the queue drops it"
    assert t.blocks[1].text == "Fixed it."


def test_tool_call_from_message_becomes_a_card_and_result_attaches():
    t = Transcript()
    t.apply({"type": "message_start",
             "message": {"role": "assistant", "content": [], "stopReason": "pending", "timestamp": 1}})
    t.apply({"type": "message_end", "message": {
        "role": "assistant", "stopReason": "toolUse", "timestamp": 1, "usage": {},
        "content": [{"type": "toolCall", "id": "c1", "name": "bash",
                     "arguments": {"command": "ls"}}]}})
    [card] = t.blocks
    assert (card.kind, card.name, card.args["command"]) == ("tool", "bash", "ls")
    t.apply({"type": "tool_execution_start", "toolCallId": "c1", "toolName": "bash",
             "args": {"command": "ls"}})
    t.apply({"type": "tool_execution_end", "toolCallId": "c1", "toolName": "bash",
             "isError": False, "durationMs": 42,
             "result": {"content": [{"type": "text", "text": "a.txt"}]}})
    assert t.blocks[0].result == "a.txt"
    assert t.blocks[0].duration_ms == 42
    assert t.blocks[0].is_error is False


def test_partial_tool_result_streams_into_the_card():
    t = Transcript()
    t.apply({"type": "tool_execution_start", "toolCallId": "c2", "toolName": "bash",
             "args": {"command": "make"}})
    t.apply({"type": "tool_execution_update", "toolCallId": "c2", "toolName": "bash",
             "partialResult": {"content": [{"type": "text", "text": "compiling 1/9"}]}})
    assert t.blocks[0].result == "compiling 1/9"
    assert t.blocks[0].is_error is False


def test_tool_result_message_attaches_to_the_existing_card():
    t = Transcript()
    t.apply({"type": "message_start",
             "message": {"role": "assistant", "content": [], "stopReason": "pending", "timestamp": 1}})
    t.apply({"type": "message_end", "message": {
        "role": "assistant", "stopReason": "toolUse", "timestamp": 1, "usage": {},
        "content": [{"type": "toolCall", "id": "c3", "name": "read", "arguments": {"path": "a"}}]}})
    t.apply({"type": "message_start", "message": {
        "role": "toolResult", "toolCallId": "c3", "toolName": "read", "isError": False,
        "content": [{"type": "text", "text": "file body"}], "timestamp": 2}})
    [card] = t.blocks
    assert card.result == "file body"


def test_queue_update_tracks_counts_without_adding_blocks():
    t = Transcript()
    t.apply({"type": "queue_update", "steering": ["change direction"], "followUp": ["then summarise"]})
    assert t.blocks == []
    assert t.queued == (1, 1)


def test_compaction_and_error_become_notices():
    t = Transcript()
    t.apply({"type": "compaction_start", "reason": "threshold"})
    t.apply({"type": "extension_error", "extensionPath": "/x.ts", "event": "tool_call",
             "error": "boom"})
    assert [b.kind for b in t.blocks] == ["notice", "notice"]
    assert "Compacting" in t.blocks[0].text and "nearly full" in t.blocks[0].text
    assert "boom" in t.blocks[1].text and t.blocks[1].is_error


def test_unknown_events_are_ignored():
    t = Transcript()
    t.apply({"type": "something_new", "payload": 1})
    assert t.blocks == []


def test_message_end_keeps_a_tool_card_created_during_streaming():
    t = Transcript()
    t.apply({"type": "message_start",
             "message": {"role": "assistant", "content": [], "stopReason": "pending", "timestamp": 1}})
    t.apply(delta("running it"))
    t.apply({"type": "message_update", "assistantMessageEvent": {
        "type": "toolcall_end", "contentIndex": 1,
        "toolCall": {"type": "toolCall", "id": "c7", "name": "bash",
                     "arguments": {"command": "ls"}}}})
    t.apply({"type": "tool_execution_end", "toolCallId": "c7", "toolName": "bash",
             "isError": False, "result": {"content": [{"type": "text", "text": "out"}]}})
    t.apply({"type": "message_end", "message": {
        "role": "assistant", "stopReason": "toolUse", "timestamp": 1, "usage": {},
        "content": [{"type": "text", "text": "running it"},
                    {"type": "toolCall", "id": "c7", "name": "bash",
                     "arguments": {"command": "ls"}}]}})
    assert [b.kind for b in t.blocks] == ["text", "tool"]
    assert t.blocks[0].text == "running it"
    assert t.blocks[1].result == "out"


def test_backfill_from_entries_links_tool_results():
    entries = [
        {"type": "message", "id": "1", "message": {"role": "user", "content": "do it", "timestamp": 1}},
        {"type": "message", "id": "2", "message": {
            "role": "assistant", "stopReason": "toolUse", "timestamp": 2, "usage": {}, "provider": "p",
            "model": "m", "content": [
                {"type": "thinking", "thinking": "plan"},
                {"type": "text", "text": "running"},
                {"type": "toolCall", "id": "c9", "name": "bash", "arguments": {"command": "ls"}}]}},
        {"type": "message", "id": "3", "message": {
            "role": "toolResult", "toolCallId": "c9", "toolName": "bash", "isError": False,
            "content": [{"type": "text", "text": "out"}], "timestamp": 3}},
    ]
    t = Transcript.from_entries(entries)
    assert [b.kind for b in t.blocks] == ["user", "thinking", "text", "tool"]
    assert t.blocks[-1].result == "out"
    assert t.blocks[0].text == "do it"


def test_failed_assistant_turn_is_reported_not_silent():
    t = Transcript()
    t.apply({"type": "message_start", "message": {"role": "user", "content": "hi", "timestamp": 1}})
    t.apply({"type": "message_start", "message": {"role": "assistant", "content": [],
                                                 "stopReason": "pending", "timestamp": 2}})
    t.apply({"type": "message_end", "message": {
        "role": "assistant", "content": [], "stopReason": "error", "usage": {},
        "errorMessage": "provider refused", "timestamp": 2}})
    kinds = [b.kind for b in t.blocks]
    assert kinds == ["user", "notice"]
    assert t.blocks[-1].is_error
    assert "provider refused" in t.blocks[-1].text
