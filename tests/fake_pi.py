"""A stand-in pi process that speaks just enough RPC for the tests."""

FAKE = r'''
import json, sys
def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n"); sys.stdout.flush()
for raw in sys.stdin.buffer:
    cmd = json.loads(raw); cid = cmd.get("id"); kind = cmd.get("type")
    if kind == "extension_ui_response":
        sys.stderr.write("ui-answer " + json.dumps(cmd) + "\n"); sys.stderr.flush()
    elif kind == "get_state":
        out({"id": cid, "type": "response", "command": "get_state", "success": True,
             "data": {"sessionId": "s1", "sessionFile": "/tmp/s1.jsonl", "sessionName": "demo",
                      "isStreaming": False, "thinkingLevel": "high",
                      "model": {"id": "balanced", "provider": "router", "name": "Balanced"}}})
    elif kind == "get_entries":
        out({"id": cid, "type": "response", "command": "get_entries", "success": True,
             "data": {"leafId": "a", "entries": [
                 {"type": "message", "id": "a", "parentId": None,
                  "message": {"role": "user", "content": "old prompt", "timestamp": 1}}]}})
    elif kind == "get_session_stats":
        out({"id": cid, "type": "response", "command": "get_session_stats", "success": True,
             "data": {"sessionId": "s1", "cost": 0.25, "totalMessages": 2,
                      "contextUsage": {"tokens": 64000, "contextWindow": 200000, "percent": 32.0}}})
    elif kind == "get_available_models":
        out({"id": cid, "type": "response", "command": "get_available_models", "success": True,
             "data": {"models": [{"id": "balanced", "provider": "router", "name": "Balanced"}]}})
    elif kind == "get_available_thinking_levels":
        out({"id": cid, "type": "response", "command": "get_available_thinking_levels",
             "success": True, "data": {"levels": ["low", "high", "max"]}})
    elif kind == "get_commands":
        out({"id": cid, "type": "response", "command": "get_commands", "success": True,
             "data": {"commands": [{"name": "skill:plan", "description": "Plan it",
                                    "source": "skill"}]}})
    elif kind == "prompt":
        sys.stderr.write("prompt-images " + str(len(cmd.get("images") or [])) + "\n")
        sys.stderr.flush()
        out({"id": cid, "type": "response", "command": "prompt", "success": True,
             "data": {"disposition": "started"}})
        out({"type": "agent_start"})
        out({"type": "message_start", "message": {"role": "user", "content": "new prompt",
                                                  "timestamp": 2}})
        out({"type": "turn_start"})
        out({"type": "message_start", "message": {"role": "assistant", "content": [],
             "stopReason": "pending", "timestamp": 3}})
        out({"type": "message_update", "assistantMessageEvent": {"type": "text_delta",
             "contentIndex": 0, "delta": "hello hub"}})
        out({"type": "message_end", "message": {"role": "assistant", "stopReason": "stop",
             "usage": {}, "timestamp": 3,
             "content": [{"type": "text", "text": "hello hub"}]}})
        out({"type": "agent_settled", "aborted": False})
        out({"id": "ui-1", "type": "extension_ui_request", "method": "select",
             "title": "Pick one", "options": ["Allow", "Block"]})
    elif kind == "set_session_name":
        out({"id": cid, "type": "response", "command": "set_session_name", "success": True})
        out({"type": "session_info_changed", "name": cmd.get("name")})
    elif kind == "trigger_ui":
        out({"id": "ui-1", "type": "extension_ui_request", "method": "select",
             "title": "Pick one", "options": ["Allow", "Block"]})
        out({"id": cid, "type": "response", "command": "trigger_ui", "success": True})
    else:
        out({"id": cid, "type": "response", "command": kind, "success": True})
'''
