# Decisions

Settled choices with the reason. Add an entry when a choice is made, not while it is being
discussed. Supersede by editing and marking `superseded by #n`.

**1. ~~No server, no HTTP API~~ — superseded by #12 (2026-11-25).**
The original call was desktop-only. Remote access is now a requirement, so the server exists.
Kept here so the reversal is visible.

**2. One pi process per open session (2026-11-25).**
Isolation and parallelism come free, and a crash costs one session. Accept the memory cost and
cap live processes (default 8) rather than multiplexing sessions through one process, which pi
does not support anyway.

**3. `QProcess` instead of a reader thread or `qasync` (2026-11-25).**
QProcess delivers stdout bytes as Qt signals on the GUI thread, so there is no thread lifetime
to manage and no async/await leaking into widget code. Keep a `bytearray` buffer and split on LF
yourself — QProcess gives you chunks, not records.

**4. `markdown-it-py` as the only added runtime dependency (2026-11-25).**
The transcript has to render CommonMark with fenced code. Hand-rolling that is a bug factory.
No highlighter in v1: monospace plus a copy button is enough.

**5. pi owns persistence; openpi reads session files and never writes them (2026-11-25).**
Display names, forks, and compactions all go through RPC so pi stays the single writer. The
session index is read-only and re-scanned on file change.

**6. No permission layer (2026-11-25).**
pi has no per-tool approval to gate. Rendering extension dialogs and deciding project trust at
spawn (`--approve` / `--no-approve`) is the honest maximum. A fake approval gate would train
users to trust a control that does not exist.

**7. UI state under `~/.openpi/` (2026-11-25).**
Window geometry, project list, drafts, scheduler tasks. Not in `~/.pi`, which belongs to pi and
is read by other tools. Atomic tmp+rename writes.

**8. Use the session header `cwd` for project mapping (2026-11-25).**
Session directories are mangled paths (`--home-user-repo--`) and can collide after renames or
for paths with dashes. The header is authoritative.

**9. ~~Out of scope: web, mobile, relay~~ — superseded by #12 (2026-11-25).**
Web, relay, and remote access are in v1. Still out: extension SDK, voice, native mobile apps.

**10. Transcript blocks are plain dataclasses; widgets reconcile by uid (2026-11-25).**
The reducer (`pi/transcript.py`) is Qt-free and tested headless. The view owns one widget per
block and updates it in place; only `message_end` replaces a message's blocks, so streaming is
linear work per delta instead of a full re-render.

**11. The GUI opens a folder with `--project`, not a bare positional (2026-11-25).**
A click group with an optional positional argument swallows subcommand names
(`openpi doctor` became a path). An option keeps `openpi`, `openpi doctor`,
`openpi sessions` unambiguous.

**12. A server with one shared token, not per-device pairing (2026-11-25).**
`openpi serve` owns the sessions; clients attach over HTTP + SSE. One bearer token (query for
EventSource, header for POST) is the whole auth model until there is more than one user. Device
tokens and QR pairing are the upgrade path, not v1.

**13. SSE + POST instead of WebSocket (2026-11-25).**
The data flow is one-way (events down, commands up). SSE works through relays, proxies, and
`EventSource` with no client library, and POST is trivial to test with curl. WebSocket buys
nothing here until there are binary attachments or sub-100ms steering.

**14. Clients receive blocks, not pi events (2026-11-25).**
The hub diffs the transcript and sends block upserts plus an order list. The browser renders
blocks and never re-implements compaction, message merging, or tool-result linking. Cost: the
patch is computed server-side per change — cheap over ~200 blocks.

**15. Relay is a byte pipe (2026-11-25).**
Browsers speak HTTP to a public port; the relay asks the instance to dial back per connection
and pipes bytes. No HTTP parsing, no WebSocket on the relay, no open port at home. Consequence:
the relay can read traffic, so v1 is for self-hosted relays or a trusted network. E2E is an open
decision (plan §9.1).

**16. `openpi doctor` and the live pytest are the protocol contract (2026-11-25).**
pi's RPC is the only integration surface; a pi upgrade must be caught by `pytest -m live`, not by
a user's broken transcript.

**17. PySide6, not PyQt6 (2026-11-25).**
PySide6 is the official Qt for Python binding. The code uses only the source-compatible
surface (scoped enums, `Signal`/`Slot`, `QProcess`), so the two are interchangeable here; the
binding is chosen once and everything else is bound to it. Any new import must come from
`PySide6.*`, and `pytest` must stay green after `uv add pyside6`.

**18. The desktop is a client when it connects, not a second runtime (2026-11-25).**
`openpi --connect` reuses `SessionPane`/`TranscriptView`/`dialogs` against a `RemoteSession`
that mirrors `PiSession`'s signals and methods over SSE + POST. No UI branch per backend: the
window picks a session factory, the pane does not know which. This finishes the "one runtime,
several clients" model.

**19. Admin token + revocable device tokens, no per-token scopes (2026-11-25).**
One shared admin token was the top security gap. Now device tokens are issued by id+name and
revocable from the CLI (`openpi token new|list|revoke`) or the admin HTTP endpoints; the server
reloads `pairings.json` on change. Tokens are all-or-nothing (any token = shell), which is the
right first step; per-token scopes stay out until there is a use for them.

**20. E2E through the relay is TLS at the instance, trusted by CA pinning (2026-11-25).**
`openpi serve --tls` serves HTTPS with a self-signed cert; the relay stays a byte pipe, so it
carries only ciphertext. The desktop client pins the cert with `--tls-ca` (real verification);
the browser sees a one-time self-signed warning unless the cert is installed. No new framing or
crypto in the relay itself.

**21. Home directory is `~/.openpi/`, not the XDG state dir (2026-11-25).**
`OPENPI_HOME` overrides the default `~/.openpi`, which holds `settings.json`, `pairings.json`,
`server-token`, `server.crt`/`server.key`, and reserved `extensions/`/`skills/` dirs. On first
run, pre-existing state under `~/.local/state/openpi/` is copied in. `ensure_home()` runs from
the click group on every invocation; `openpi setup` does it explicitly.

**22. pi is installed/updated by `openpi setup`, not silently by the server (2026-11-25).**
`setup` installs pi with its official installer (`pi.dev/install.sh`) and updates it with
`pi update --self`, falling back to a global npm install. `serve` only checks that pi exists;
`doctor` reports the installed vs latest version. Auto-updating pi behind a running server is
too surprising to do unprompted.

**23. Releases publish on a version tag; the token is the PyPI secret (2026-11-25).**
`.github/workflows/release.yml` runs tests, checks the `v*` tag matches `pyproject` version,
builds with `uv build`, publishes with `uv publish --token "$PYPI_TOKEN"` (org-scoped token for
`pypi.org/org/D5-Interactive/`), then cuts the GitHub release. `ci.yml` runs tests on push/PR.

**24. One palette drives every color; zoom scales the app font (2026-11-25).**
`ui/theme.py` exposes a `Palette` per mode (dark/light/system) and generates the QSS from it.
Widgets read module-level color aliases (`theme.ACCENT`, `theme.CODE_BG`, …) that `apply()`
refreshes, so a mode switch re-renders. Zoom changes the QApplication font point size, so every
widget scales together and nothing hardcodes pixel sizes beyond base spacing.

**25. Favorites live in openpi settings, never in pi's files (2026-11-25).**
Pinned providers (`favorite_providers`) and models (`favorite_models` = `provider/id`) are stored
in `settings.json` and float to the top of the model picker. pi has no notion of openpi's UI
preferences, so they stay out of `models.json`/`settings.json` under `~/.pi/agent`.

**26. Provider setup writes pi's `models.json` (extends #5, 2026-11-25).**
`pi/providers.py` detects running local servers and, on save, merges an OpenAI-compatible
endpoint into `~/.pi/agent/models.json` — the one file pi documents for user-managed compatible
endpoints. Sessions, catalogs, and pi's own `settings.json` remain read-only to openpi.
