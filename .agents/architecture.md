# openpi architecture

A control room for the **pi** coding agent: a PySide6 desktop app and a background web server
that share one runtime design. pi has no server; openpi drives `pi --mode rpc` child processes
and reads pi's session files. If anything here contradicts `pi-protocol.md`, the protocol file
wins — it is sourced from pi's own docs.

Topology:

```
browser ──HTTP/SSE──▶ openpi serve ──JSONL──▶ pi --mode rpc   (one process per session)
   ▲                     ▲
   └──relay byte pipe────┘        desktop app ──HTTP/SSE──▶ (--connect) or in-process (default)
```

## Module map (as built)

```
src/openpi/
  __init__.py            exports main
  cli.py                 click group: GUI (default), `sessions`, `doctor`
  config.py              Settings struct, XDG state dir, atomic JSON writes
  protocol/codec.py      LF framing helpers
  protocol/records.py    msgspec Structs for state, models, stats, commands, UI requests
  pi/process.py          PiProcess(QObject): QProcess spawn, LF split from a byte buffer, send
  pi/session.py          PiSession: process + State + Transcript + stats/models/commands
  pi/transcript.py       pure reducer: pi events/entries -> blocks (user, text, thinking, tool…)
  pi/index.py            read-only scan of ~/.pi/agent/sessions for the rail
  pi/doctor.py           one-shot RPC probe behind `openpi doctor`
  pi/providers.py        local-server autodetect + pi `models.json` configuration
  ui/window.py           MainWindow: hideable project→session tree, pane stack, theme/zoom
  ui/pane.py             SessionPane: header controls, transcript, composer, footer
  ui/transcript.py       BlockWidget + TranscriptView (incremental, capped at 200 blocks)
  ui/composer.py         input box, send/stop, queue count, `/` command menu
  ui/dialogs.py          extension_ui_request dialogs (select/confirm/input/editor)
  ui/theme.py            Palette per mode, generated QSS, zoom (Ctrl+/-), module color aliases
  ui/model_selector.py   searchable, provider-grouped, favorite-pinning model picker
  ui/settings.py         settings dialog: appearance, providers, favorites
  ui/markdown.py         markdown-it-py -> Qt rich text
  ui/tasks.py            thread + signal helper for scans
  server/hub.py          SessionHub: owns sessions, snapshots, block patches, cross-thread calls
  server/http.py         HTTP + SSE API, token auth, static web client
  server/serve.py        `openpi serve`: QCoreApplication + hub + HTTP + optional relay client
  server/client.py       RemoteClient + RemoteSession: the desktop as a client of a server
  server/web/index.html  browser client (no build step, vanilla JS)
  relay.py               `openpi relay` + RelayClient: outbound byte-pipe relay
tests/                   codec, records, index, transcript, process, session, UI, hub, http,
                         relay, live contract
```

## Hard invariants

1. **One process per open session.** No shared daemon, no multiplexing. Switching sessions
   never kills anything: every open `PiSession` keeps streaming. That is the product.
2. **All Qt widget access happens on the GUI thread.** `PiProcess` uses `QProcess`, so records
   arrive as Qt signals on the GUI thread with no reader thread. Keep file scans off the GUI
   thread (`ui/tasks.py`).
3. **Framing is LF-only.** Split bytes on `b"\n"`, strip one trailing `\r`. Never use text-mode
   readline or treat U+2028 as a boundary.
4. **stdout is protocol, stderr is logs.** stderr becomes a `failed` signal; never parsed as
   JSON.
5. **Gate "done" on `agent_settled`, never on prompt acceptance.** `prompt` only reports
   acceptance (`disposition`).
6. **Transcript is a pure reducer.** `pi/transcript.py` has no Qt import; widgets reconcile by
   block uid. A message is only re-rendered from its final `message_end` payload.
7. **Never invent a permission gate.** pi does not ask per tool call. Project trust is decided at
   spawn time (`--approve` / `--no-approve`), extension dialogs are rendered as they come.
8. **Cap the process count.** Opening is lazy; the cap (default 8) is not enforced yet — see
   `docs/plan.md` risks.
9. **HTTP threads never touch Qt objects.** `SessionHub.call(fn)` posts work to the Qt thread
   and waits; `post(fn)` is fire-and-forget. Event fan-out goes through `queue.Queue` per SSE
   subscriber, pushed from the Qt thread.
10. **The server owns the transcript.** Clients receive blocks, not raw pi events, so the web
    client never re-implements the reducer. Patches are `{upsert: [...], order?: [...],
    state?/stats?/busy?/queued?}` keyed by block uid. The wire contract is
    `.agents/server-api.md`; `RemoteSession` is the desktop side of it.
11. **The relay is a byte pipe, not an HTTP proxy.** Instance holds one control socket out;
    every browser connection triggers `GO <id>` and a `DATA` dial-back. Keep it dumb so HTTP,
    SSE, and keep-alive behave normally.

## Session lifecycle

```
spawn  -> pi --mode rpc [--session <path>] --approve|--no-approve
       -> get_state + get_entries + get_session_stats + models + thinking levels + commands
       -> live events append to the transcript
close  -> close stdin; pi disposes; kill only after a grace period
```

- New session: spawn without `--session`; `--name` or `set_session_name` names it later.
- Reopen: `--session <path>` runs in the session's own cwd, not the launcher's cwd.
- Fork/clone/switch go through RPC so the process and its extensions stay alive.
- Backfill uses `get_entries` (includes pre-compaction history). `get_messages` is the compacted
  model view; openpi uses it only through `get_session_stats`.

## Data ownership

- pi owns sessions, models, settings, extensions, MCP, skills. openpi never rewrites session
  JSONL, `~/.pi/agent/settings.json`, or model catalogs.
- openpi owns only its own UI state in `~/.openpi/` (override with `OPENPI_HOME`):
  settings, pairings, the server token, TLS material, and reserved `extensions/`/`skills/`
  dirs — projects, last project, trust decisions, live cap, later window
  geometry. Atomic write (tmp + `os.replace`).
- Renames go through RPC (`set_session_name`); that is the only session write openpi performs.

## Where openpi deliberately differs from openchamber

- One server token, no per-device pairing, no push notifications, no mobile app shell.
- No websocket: SSE + POST is enough for one-way streams and survives dumb proxies.
- The relay does not end-to-end encrypt frames yet (see decisions #12).
- No permission mode / classifier: pi has no per-call approval to classify.
- Notes/todos/plans live in the repo the agent can already read, not a private store.
- No extension SDK. pi extensions already exist; openpi renders what they ask for.
