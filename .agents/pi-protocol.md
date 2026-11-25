# pi integration facts (authoritative)

Source: installed pi 1.5.2 docs at
`~/.pi/agent/install/releases/1.5.2/node_modules/@earendil-works/pi-coding-agent/docs/`
(`rpc.md`, `rpc-commands.md`, `json.md`, `rpc-extension-ui.md`, `session-format.md`,
`message-types.md`, `sessions.md`, `security.md`). Read those before changing the client.

## There is no server. Spawn one process per session.

```
pi --mode rpc [--session <path>|--session-id <id>|--continue|--fork <path>] [--name <n>] [--no-session]
```

- RPC mode = long-lived child process, JSONL on stdin/stdout. This is pi's only remote-control API.
- One process = one session. Parallel sessions/worktrees/multi-run = N processes. No shared daemon.
- stdout is protocol only; stderr is logs. Never parse stderr as protocol.
- Close stdin to shut down; pi disposes cleanly. SIGTERM also starts an orderly shutdown.

## Framing rules (get these wrong and the client dies)

- Split records on **LF only**. JS `readline` also splits on U+2028/U+2029, which are legal
  inside JSON strings — read bytes and split on `b"\n"`, strip a trailing `\r`.
- Read stdout continuously; a stalled reader blocks pi on backpressure.
- One JSON object per line. `id` on a command is echoed on its `response`.
- Command handling is asynchronous: correlate by `id`, never by order.

## Commands we need (stdin)

| Command | Notes |
|---|---|
| `prompt` | `{message, images?, streamingBehavior?}`. `streamingBehavior`: `"steer"` or `"followUp"` required while streaming, else error. Response `data.disposition`: `started`/`queued`/`handled`. Accepted ≠ finished. |
| `steer` / `follow_up` | Queue separately; `clear_queue` returns their text so Esc can restore the editor. |
| `abort` | Responds after the session is idle. |
| `get_state` | model, thinkingLevel, isStreaming, isCompacting, sessionFile, sessionId, sessionName, pendingMessageCount. |
| `get_messages` | Full conversation (post-compaction view). |
| `get_entries` | Append-only tree entries; `since: <entryId>` is a durable cursor. Use for history/backfill and branch UI. |
| `get_tree` | `{tree, leafId}` of `{entry, children, label?}`. |
| `switch_session` / `new_session` / `fork` / `clone` | All can be cancelled by extension handlers (`data.cancelled`). |
| `set_model`, `cycle_model`, `get_available_models` | Model object: id, provider, api, baseUrl, reasoning, input, contextWindow, maxTokens, cost. |
| `set_thinking_level`, `get_available_thinking_levels` | off/minimal/low/medium/high/xhigh/max. |
| `compact`, `set_auto_compaction`, `set_auto_retry`, `abort_retry` | |
| `bash`, `abort_bash` | Direct shell in the session; output joins context on the next prompt. Streams `bash_execution_update` with the command's `id`. |
| `get_session_stats` | tokens, cost, contextUsage {tokens, contextWindow, percent}. |
| `set_session_name`, `export_html`, `get_last_assistant_text` | |
| `get_commands` | Skills / prompt templates / extension commands for the `/` menu. TUI-only commands are absent. |

## Events (stdout)

`agent_start`, `turn_start`, `message_start`, `message_update`, `message_end`, `turn_end`,
`agent_end`, `agent_settled`, `tool_execution_start|update|end`, `queue_update`,
`entry_appended`, `session_info_changed`, `thinking_level_changed`,
`compaction_start|end`, `auto_retry_start|end`, `summarization_retry_*`,
`bash_execution_update`, `extension_error`.

- `message_update` carries **deltas only**: `{usage, assistantMessageEvent}` with types
  `text_start/delta/end`, `thinking_start/delta/end`, `toolcall_start/delta/end`.
  Buffer deltas, then replace with `*_end` content, then replace the whole message with
  `message_end.message`.
- `agent_end` = one low-level run ended; retries/compaction/queue can still run.
  `agent_settled` = nothing more will happen automatically. **Gate "done" on `agent_settled`.**
- Ordering: subscribe before sending a prompt, or you can miss a fast completion.

## Messages

Content blocks: `text`, `image` (base64 + mimeType), `thinking`, `toolCall`
(`{id, name, arguments}`). Roles: `system`, `user`, `assistant`, `toolResult`,
`bashExecution`, `custom`, `branchSummary`, `compactionSummary`. Tolerate unknown roles.

## Extension UI subprotocol

- `extension_ui_request` with `method`:
  - dialogs (block until answered): `select` (options), `confirm` (title+message), `input`
    (placeholder), `editor` (prefill). May carry `timeout`; pi auto-resolves, so the client
    need not track it.
  - fire-and-forget: `notify` (`notifyType`: info|warning|error), `setStatus`, `setWidget`,
    `setTitle`, `set_editor_text`.
- Answer with `extension_ui_response` `{id, value}` / `{id, confirmed}` / `{id, cancelled:true}`.
  It produces no normal command response.
- `ctx.mode == "rpc"` and `hasUI == true`; TUI-only extension features (`custom()`, theming,
  header/footer) are no-ops. Extensions written for the TUI degrade, not crash.

## Session storage (read-only access for the browser)

```
~/.pi/agent/sessions/--<mangled-cwd>--/<ISO-ts>_<session-id>.jsonl
```

Header line `{"type":"session","version":3,"id","timestamp","cwd","parentSession?"}`,
then entries with `id`/`parentId`/`timestamp`: `message`, `model_change`,
`thinking_level_change`, `usage`, `compaction`, `context_edit`, `branch_summary`, `custom`,
`custom_message`, `label`, `session_info` (display name). Entries form a tree; the leaf is
the active branch. `buildContextEntries` walks leaf→root and honors the latest compaction.

Cheap session list = read the first line (cwd/id) + scan for `session_info`/first user text +
file mtime. Do this off the GUI thread for large histories.

## Model picker specifics

- `get_available_models` returns hundreds of entries on a configured machine (408 here) and the
  list can differ per cwd because project settings add models. Group by `provider`, filter by
  `input` support when the prompt has images.
- **Virtual models** exist: an extension can register a model that picks a physical model per
  request (`pi.registerVirtualModel`). The session's selected model may therefore be virtual
  while each assistant message names the physical model that answered. Show both — selection
  from `get_state.model`, dispatch from the last assistant message — or the UI will look wrong.
- Thinking levels are model-specific (`get_available_thinking_levels`); do not hardcode the
  seven levels from the docs.
- `sessionFile` is absent when pi runs with `--no-session`; `sessionName` is absent until set.

Verified against pi 1.5.2 on this machine: `pi --mode rpc --no-session --no-extensions --no-mcp`
answered `get_state`, `get_available_models` (408), and `get_available_thinking_levels`
(`["low","high","max"]` for the configured virtual model `balanced`) over JSONL, then exited 0
on stdin EOF with empty stderr.

## Trust and safety gotchas

- **RPC/JSON/print cannot show pi's project-trust prompt.** With `defaultProjectTrust: "ask"`,
  protected project resources (`.pi/settings.json`, `.pi/extensions`, `.pi/skills`,
  `.agents/skills`, …) are silently skipped. openpi must decide and pass `--approve` /
  `--no-approve` per project, and surface that choice in the UI.
- pi does **not** ask approval per tool call. Any confirm dialog you see comes from an
  extension via `extension_ui_request`. Do not invent a permission gate in the client.
- `--session`/`--resume` run in the session's own cwd, not the launching cwd. `--fork` uses
  the current directory and creates a new session.
- Session dir override: `--session-dir`, `PI_CODING_AGENT_SESSION_DIR`, or `sessionDir` setting.
