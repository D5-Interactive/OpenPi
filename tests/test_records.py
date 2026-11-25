import msgspec

from openpi.protocol.records import (
    CommandInfo,
    ExtensionUIRequest,
    Model,
    Response,
    SessionStats,
    State,
    decode,
)


def test_state_decodes_core_fields_and_ignores_unknown_ones():
    state = decode(
        {
            "model": {"id": "balanced", "provider": "router", "name": "Balanced", "reasoning": True,
                      "contextWindow": 200000, "cost": {"input": 0.0}},
            "thinkingLevel": "high",
            "isStreaming": True,
            "isCompacting": False,
            "sessionId": "abc123",
            "sessionName": "fix/upload-retry",
            "pendingMessageCount": 2,
            "messageCount": 9,
            "somethingNew": {"ignored": True},
        },
        State,
    )
    assert state.model.id == "balanced"
    assert state.model.reasoning is True
    assert state.thinking_level == "high"
    assert state.is_streaming and not state.is_compacting
    assert state.session_name == "fix/upload-retry"
    assert state.pending == 2


def test_state_without_model_is_allowed():
    state = decode({"isStreaming": False}, State)
    assert state.model is None
    assert state.session_name is None


def test_response_keeps_error_and_success_flag():
    resp = decode({"id": "3", "type": "response", "command": "set_model",
                   "success": False, "error": "Model not found: invalid/model"}, Response)
    assert resp.success is False
    assert resp.error == "Model not found: invalid/model"
    assert resp.data is None


def test_model_list_decodes_from_available_models_payload():
    models = msgspec.convert(
        {"models": [{"id": "a", "provider": "p", "input": ["text", "image"]},
                    {"id": "b", "provider": "p", "reasoning": True}]},
        AvailableModels,
    ).models
    assert [m.id for m in models] == ["a", "b"]
    assert models[0].input == ["text", "image"]
    assert models[1].reasoning is True


def test_stats_tolerates_missing_context_usage():
    stats = decode({"sessionId": "s", "totalMessages": 3, "cost": 0.5,
                    "tokens": {"total": 1200}}, SessionStats)
    assert stats.cost == 0.5
    assert stats.context_usage is None
    assert stats.tokens["total"] == 1200


def test_stats_decodes_context_usage():
    stats = decode({"contextUsage": {"tokens": 64000, "contextWindow": 200000, "percent": 32.0}},
                   SessionStats)
    assert stats.context_usage.percent == 32.0


def test_extension_ui_select_request_decodes_options_and_timeout():
    req = decode({"id": "u1", "type": "extension_ui_request", "method": "select",
                  "title": "Allow command?", "options": ["Allow", "Block"], "timeout": 10000},
                 ExtensionUIRequest)
    assert req.method == "select"
    assert req.options == ["Allow", "Block"]
    assert req.timeout == 10000


def test_command_info_decodes_slash_menu_entry():
    cmd = decode({"name": "skill:plan", "description": "Draft a plan", "source": "skill"}, CommandInfo)
    assert cmd.name == "skill:plan"
    assert cmd.source == "skill"


class AvailableModels(msgspec.Struct):
    models: list[Model] = msgspec.field(default_factory=list)
