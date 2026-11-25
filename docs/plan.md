# openpi — plan

`openpi` is a control room for the **pi** coding agent: a PySide6 desktop app, a background web
server, and a relay so the server is reachable from a phone. Built with PySide6, click, and
msgspec. OpenChamber does this for OpenCode; openpi does it for pi.

Research behind this plan: [`docs/research/openchamber.md`](research/openchamber.md).
Integration facts (RPC, events, sessions): [`.agents/pi-protocol.md`](../.agents/pi-protocol.md).
Target module layout and invariants: [`.agents/architecture.md`](../.agents/architecture.md).

## 1. Shape: one runtime, several clients

openpi runs the sessions in one place and puts clients on top of them, like OpenChamber:

- **`openpi serve`** — a background server (no display) that owns pi processes, the transcript
  reducer, and SSE fan-out. It is the single source of truth for a machine.
- **Desktop app** — currently runs its own runtime in-process (M1). Connecting the desktop to a
  remote server is the follow-up that finishes the model.
- **Web client** — one static page served by the server; works on a phone browser.
- **Relay** — a server behind NAT dials out to a relay; browsers reach it through the relay
  without an open port.

pi itself needs no server: it already speaks JSONL over stdio (`pi --mode rpc`) and owns
sessions, models, skills, MCP, and extensions. openpi adds the multi-client layer, not an agent
implementation.

What is still deliberately absent: a database, an extension sandbox, a permission system, and
any re-implementation of pi config.

## 2. Goals

1. **See and steer many sessions at once.** pi's TUI is one conversation; openpi keeps every
   opened session streaming in the background and switches instantly.
2. **Read streams, not walls of text.** Markdown text, thinking blocks, tool calls with
   collapsible args/results, bash output, compaction and retry markers, token/cost accounting.
3. **Review and land work without leaving the window.** Diff, stage, commit (message written by
   the session's model), branch, worktree.
4. **Orchestrate cheaply.** Multi-model runs, scheduled prompts, an optional review pass over a
   diff. Only where pi gives us the pieces.
5. **Never lie about state.** Three-state loading (`loading`/`ready`/`error`), live status from
   events, "done" only on `agent_settled`.
6. **Leave the desk.** The same sessions from a browser, including through a relay when the
   machine has no public address.

## 3. Non-goals (v1)

- Pairing QR codes, per-device tokens, private relay encryption, push notifications, and a
  mobile app shell. v1 is one server token, browser UI, and a self-hosted relay.
- A permission model. pi has no per-tool approval; inventing one in the GUI would be a lie.
  openpi renders extension dialogs and decides **project trust** at spawn time.
- Extension SDK or plugin sandbox. pi extensions run in-process and call `ctx.ui`; openpi
  renders `extension_ui_request`.
- Notes/todos/plans as a private store. The agent reads repo markdown; openpi will not keep a
  parallel database of intent.
- Provider/MCP/skills config editors. pi's own config and `pi config` stay authoritative.
- Voice, embedded browser, auto model routing, agent-written workflows.

## 4. Shape

```
┌──────────────┬──────────────────────────────────────────────┬──────────────┐
│ projects     │ transcript                                   │ context      │
│  openpi      │  ▸ user                                      │ model        │
│  d5-dog      │  ▸ assistant  [thinking]                     │ thinking     │
│  starsec     │  ▸ tool bash  ls -la            ✓ 42 ms      │ tokens/cost  │
│              │  ▸ assistant  streaming…                     │ git branch   │
├──────────────┤                                              │ changes ▸    │
│ sessions     │                                              │              │
│ ● fix/upload │  ┌────────────────────────────────────────┐  │              │
│ ● triage #482│  │ prompt…      [steer ▾] [model] [send]  │  │              │
│ ○ release    │  └────────────────────────────────────────┘  │              │
└──────────────┴──────────────────────────────────────────────┴──────────────┘
   status: 2 streaming · 1 waiting for input · pi 1.5.2
```

Left rail: projects (recent dirs) and sessions (pi session files, live status dot). Centre:
transcript plus composer with model/thinking pickers and a queue indicator. Right: context
usage, session actions, git changes. A bottom status bar reports pi version, process count, and
extension dialogs waiting for an answer.

Keyboard: `Ctrl+K` command palette, `Ctrl+N` new session, `Ctrl+W` close tab/session view,
`Ctrl+Shift+W` new worktree session, `Esc` = `clear_queue` + `abort` with the queued text
restored to the composer (same semantics as pi's TUI).

## 4a. Packaging and setup

- `uv tool install openpi` ships the whole app (web client included in the wheel). First run
  creates `~/.openpi/` (override `OPENPI_HOME`) and migrates any earlier XDG-state.
- `openpi setup` installs or updates pi (`pi update --self`); `openpi doctor` shows installed vs
  latest; `serve` only checks pi exists.
- `.github/workflows/` runs tests on push/PR and, on a `v*` tag, builds, publishes to PyPI
  (D5-Interactive org, `secrets.PYPI_TOKEN`), and cuts a GitHub release.

## 5. Milestones

Status: **M0, M1, M2 done** — including desktop client mode, per-device pairing tokens, and
relay E2E (TLS + CA pinning). The M1 gaps are also closed: image attachments (desktop + web),
tray notifications, and a `/` autocomplete popup. M3 (git/diff/worktrees) onward is untouched.

### M0 — protocol spine (½–1 day)

- `protocol/codec.py`: byte-level LF framing, CRLF tolerated, writes under a lock.
- `pi/process.py`: spawn `pi --mode rpc`, reader `QThread`, id-correlated requests,
  stderr ring buffer, orderly shutdown (close stdin → grace → terminate).
- `cli.py`: `openpi` (GUI, current folder or `--project PATH`), `openpi sessions` (disk index),
  `openpi doctor` (version, session dir, model count, thinking levels, live RPC probe).
- `config.py`: XDG state dir, atomic JSON settings.

**Done when:** `openpi doctor` prints a real pi version and model count; a live pytest spawns
`pi --mode rpc --no-session`, sends one prompt, prints deltas, and exits cleanly; unit tests
cover LF/CRLF/U+2028 framing and command-id correlation.

*Done. `pi/process.py` uses QProcess (see `.agents/decisions.md` #3) instead of a reader
thread.*

### M1 — chat control room (3–4 days)

- Session index: scan `~/.pi/agent/sessions`, header `cwd` (authoritative), display name from
  `session_info`, first user line, mtime; watched for changes; scanned off the GUI thread.
- Transcript rendering: coalesced streaming (append plain text at ~10 Hz, render markdown on
  `text_end`/idle), thinking blocks, tool call cards with args + result + duration, bash cards,
  error/abort markers, compaction and retry notices.
- Composer: prompt, steer/follow-up when streaming, images via file drop/paste, abort,
  queue chips from `queue_update`, `/` menu from `get_commands`.
- Model + thinking pickers from `get_available_models` / `get_available_thinking_levels`;
  `set_model`, `set_thinking_level`. Group by provider, show the routed physical model next to a
  virtual selection (see `.agents/pi-protocol.md`).
- Footer: `get_session_stats` (context gauge, tokens, cost), session name editing
  (`set_session_name`).
- Extension dialogs (`select`/`confirm`/`input`/`editor`) with local timeout handling, plus
  `notify` toasts and tray notification on `agent_settled` when the window is not focused.
- Session actions: new, resume, rename, close; `--approve`/`--no-approve` trust choice per
  project on first spawn.

**Done when:** three sessions stream at once in one window and switching costs no reload;
aborting one leaves the others running; an extension that calls `ctx.ui.confirm` gets a real
answer from the GUI; context gauge matches `get_session_stats`; killing pi externally shows a
disconnected state instead of a frozen transcript.

*Done, except images (RPC accepts them; the composer does not attach them yet), tray
notifications (taskbar alert only), and the context panel lives in the footer instead of a right
rail.*

### M2 — server and remote access (done)

- `openpi serve`: hub + HTTP/SSE server on a Qt core loop, token auth, per-session snapshots
  and block patches, extension dialogs over the socket, `openpi serve --relay host:port`.
- Web client (`server/web/index.html`): session picker, transcript, composer with steer, model
  and thinking pickers, dialogs, context/cost footer, reconnect banner. Mobile-first.
- `openpi relay`: public port for browsers, instance port for outbound registration, byte pipe
  so HTTP and SSE just work. No open port on the openpi machine.

**Done when:** a browser through the relay can open a session, prompt it, and watch the reply
stream; a lost connection reconnects and resyncs from a snapshot; the relay refuses to serve
when no instance is registered.

*Done and verified against a real pi process and a real model call (which failed; the failure
is rendered as an error notice). Desktop client mode (`openpi --connect`) is also done: the
desktop reuses `SessionPane` against a `RemoteSession` that speaks the SSE/HTTP protocol. Still
open in M2: per-device pairing tokens and E2E encryption over the relay.*

### M3 — git and branches (3 days)

- Diff pane: working tree and per-file diffs (`git -C <cwd> diff`), colourised unified hunks,
  stage/unstage, commit with an agent-written message (one-shot `pi -p` against the selected
  files, never auto-committed).
- Session tree: `get_tree` view, jump to a branch, fork (`fork`) and clone (`clone`) in place.
- Worktree sessions: create from branch or new branch, spawn in that path, archive (remove
  folder, keep branch and session), delete with optional branch removal.

**Done when:** a session opened in a worktree writes files there and the diff pane shows them;
forking a message creates a second branch visible in the tree and both remain openable;
archive and restore round-trip a worktree without losing the session file.

### M4 — orchestration (3 days)

- Multi-run: same prompt to N models, one session each, optional worktree per run, comparison
  columns, keep or discard.
- Scheduler: JSON task list in the state dir, daily/weekly/once, run while the app is open,
  recorded last run + created session; visible "off when closed" note.
- Diff walkthrough: one structured-output pass over a scoped diff producing ordered stops with
  a tag and an observation; cached by diff hash + model; displayed next to the diff.

**Done when:** a two-model run from one prompt produces two sessions with the same first
message and separate cwds; a scheduled task fires on time in a test clock; the walkthrough
renders numbered stops anchored to file+line and degrades to "not covered" for other hunks.

### M5 — polish (2 days)

Command palette, project actions (`run`/`stop` per project, plain argv), preview URL launcher
(system browser), export session (`export_html`), session search, light/dark themes, window
state persistence.

## 6. Dependencies

Runtime, existing: `pyqt6`, `click`, `msgspec`.
One addition: `markdown-it-py` (CommonMark → HTML for `QTextDocument`). No syntax-highlighting
package in v1; code blocks get a monospace style and a copy button.
No `qasync`: a `QThread` reader with Qt signals is simpler and keeps the GUI thread free.
Dev: `pytest` (`uv add --dev pytest`), Qt runs offscreen in CI (`QT_QPA_PLATFORM=offscreen`).

## 7. Testing

- Unit: framing codec (LF, CRLF, U+2028 inside a string, backpressure-style chunk splits),
  record structs, session index against fixture JSONL, git ops in a throwaway repo.
- Live contract test (marked `live`, skipped by default): spawn the real pi, assert
  `get_state`, `get_available_models`, one prompt to `agent_settled`, and clean shutdown. This
  is the test that catches pi protocol drift.
- Offscreen smoke: build the main window, feed a recorded event fixture, assert the transcript
  contains the expected text and tool card count.

## 8. Risks

| Risk | Mitigation |
|---|---|
| pi protocol/CLI drift | Pin a tested pi range in `openpi doctor`; parse unknown records tolerantly; live contract test |
| Qt streaming performance | Coalesce deltas, render markdown only on block end, cap rendered history, virtualise later |
| Many processes = many extensions loaded | Spawn lazily on open; LRU-close idle live sessions above a configurable cap (default 8) while keeping their files |
| Extension dialog answered after pi's timeout | Use the request's `timeout` to close the dialog locally and mark it expired |
| Project trust silently skipped in RPC mode | Explicit `--approve`/`--no-approve` per project; ask once, store the choice in openpi settings |
| Wrong project mapping from mangled session dirs | Always use the session header `cwd`, never the directory name |
| Cost surprises on multi-run | Show model cost per run in the picker; no default to expensive models |

## 9. Open decisions

1. **Relay encryption** — v1 pipes plaintext between relay and instance. Options: TLS on the
   relay, or an application-level session key. Needs a decision before a public relay.
2. **Desktop as a client** — done via `RemoteSession` (SSE + POST) reusing `SessionPane`.
3. **Live-process cap** — 8 open pi processes (fast switching, more memory) vs 3 (lighter).
   Default proposed: 8, configurable.
4. **Commit messages** — reuse the session's model (consistent with the session's context) or a
   separate cheap one-shot model (predictable cost)? Proposed: session model, with a fallback
   if the session is busy.
5. **Scheduler** — in-app only (honest limitation) or a `systemd --user` timer that reopens
   openpi headlessly? Proposed: in-app only for v1.

## 5b. UI modernization (current)

Design notes for the visual/UX sweep. Principles: one palette object drives every color (dark +
light from the same roles); font size is the zoom knob (Ctrl+/Ctrl-/Ctrl+0 change the app
font, so everything scales, no hardcoded px); nothing stretches off-screen — the model picker
is a searchable popup, not a wide combo; the sidebar is hideable and groups sessions by
project.

- **Theme** — `ui/theme.py` exposes `Theme(mode)`, a `palette()` with semantic roles
  (bg, surface, border, text, muted, accent, success, warning, danger, diff), and `qss()`
  generated from it. `apply(app)` sets the palette + QSS. Scrollbars, focus rings, selection,
  and radius are all in the QSS. Modes: dark, light, system (follows `QStyleHints.colorScheme`).
- **Zoom** — stored in settings; `Ctrl+=`/`Ctrl+-`/`Ctrl+0` scale the app font point size.
- **Settings** — `ui/settings.py` dialog with tabs: Appearance (theme, zoom), Providers
  (detect local servers + add/remove to pi's `~/.pi/agent/models.json`), Favorites
  (pinned providers/models). Persisted in `config.Settings`.
- **Provider autodetect** — `pi/providers.py` probes known local endpoints
  (LM Studio :1234, Ollama :11434, vLLM :8000, llama.cpp :8080, Colibri :2345) with `GET
  /v1/models`; `configure_provider()` merges an OpenAI-compatible endpoint into pi's
  `models.json`. Favorites are `provider` and `provider/model` strings stored in openpi settings
  (never in pi's files).
- **Model picker** — `ui/model_selector.py`: a fixed-width button that opens a popup with a
  filter box and a provider-grouped list; pinned models float to the top. Replaces the
  stretching `QComboBox`.
- **Sidebar** — project→sessions tree (`QTreeWidget`), collapsible, hideable via a hamburger
  toggle + `Ctrl+B`; state persists.

## 6. OpenChamber feature parity

Status legend: ✅ done · 🔜 planned (milestone) · ⏭️ pi owns it (openpi renders, never reimplements) · ✖️ non-goal.

| OpenChamber | openpi |
|---|---|
| Project + folder grouping | ✅ per-project sidebar tree |
| Session list, switch, live status | ✅ |
| Chat streaming (text / thinking / tool / bash) | ✅ |
| Composer, `/` commands, `@` files | ✅ `/` menu + autocomplete; 🔜 `@` file chips |
| Context gauge, tokens, cost | ✅ footer |
| Images in a prompt | ✅ desktop + browser |
| Permission modes (allow/deny/ask + classifier) | ⏭️ pi has no per-call approval; openpi renders `ctx.ui` dialogs |
| Notes / todos / plans | 🔜 M4 (repo markdown the agent already reads) |
| Memory | ⏭️ pi extensions (e.g. rpiv-todo); openpi renders their UI |
| Goals (audit loop, token budget) | 🔜 M4 (one-shot auditor process) |
| Leads / workflows (multi-agent) | ✖️ v1; revisit if goals succeed |
| Scheduled tasks / loops | 🔜 M4 (in-app scheduler, honest "off when closed" note) |
| Multi-run (one prompt, N models) | 🔜 M4 |
| Auto model routing (classifier) | ✖️ non-goal |
| Git: diff, stage, commit message by the agent | 🔜 M3 |
| Branch sessions (fork/clone/tree) | 🔜 M3 |
| Worktree sessions | 🔜 M3 |
| Changes walkthrough (LLM diff summary) | 🔜 M4 |
| Git hosts (GitHub/GitLab/Gitea/Gerrit) + issue context | 🔜 M3/M4 (local git first, then hosts) |
| Integrations catalog (~150 services) | ⏭️ pi MCP; 🔜 a read-only MCP/skills panel |
| Provider / MCP / skills management | ✅ local providers (LM Studio/Ollama/vLLM/llama.cpp/Colibri) + pi `models.json`; 🔜 MCP/skills list |
| Preview / dev servers | ✖️ non-goal |
| Project actions (run commands) | 🔜 M5 |
| Magic prompts / draft starters | 🔜 M5 |
| Themes | ✅ dark/light/system |
| Notifications | ✅ tray |
| Voice (TTS/STT) | ✖️ non-goal |
| Remote: pairing QR, relay, tunnels, mobile apps | ✅ token + device tokens + relay; ✖️ QR/mobile app |
| Desktop remote instances (SSH) | ✅ `--connect` (client of a server) |
| Embedded browser panel | ✖️ non-goal |
| Extension SDK (untrusted iframe panels) | ⏭️ pi in-process extensions via `ctx.ui`; ✖️ own sandbox |

## 7. Modernization roadmap

Done in the sweep: palette-driven theme (dark/light/system), Ctrl+/- zoom, hideable per-project
sidebar, searchable/pinnable model picker, settings dialog (appearance / providers / favorites),
styled scrollbars, and local-server autodetection.

Still open, in rough order:

1. **Command palette** (`Ctrl+K`) covering every action, and `@` file/agent chips in the composer.
2. **Chat polish** — per-message actions (copy, retry), fenced-code syntax highlighting, tighter
   message grouping, avatars.
3. **Narrow layouts** — the header and composer should reflow instead of crowd on small widths;
   test a few window sizes and HiDPI.
4. **Session search/filter** in the sidebar tree.
5. **Browser client parity** — bring the web UI's palette and controls in line with the desktop
   (it is still dark-only).
