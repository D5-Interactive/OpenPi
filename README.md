# openpi

A control room for the [pi](https://github.com/earendil-works/pi) coding agent: a desktop app,
a background web server, and a relay so the same sessions are reachable from a phone.

PySide6 + click + msgspec. It drives `pi --mode rpc` child processes and reads pi's own session
files. No database, no account, no extension sandbox.

## Status

M0 (protocol spine), M1 (desktop chat control room), and M2 (web server + relay) are built:
session list, live multi-session streaming, markdown transcript, tool cards, model/thinking
pickers, extension dialogs, context/cost footer, project trust, a browser client, and a
self-hosted relay. M3 (git, branches, worktrees) is next — see [`docs/plan.md`](docs/plan.md).

## Install

```bash
uv tool install openpi              # from PyPI (once published)
# or from source:
uv tool install git+https://github.com/D5-Interactive/OpenPi
```

First run creates `~/.openpi/` (override with `OPENPI_HOME`) for `settings.json`, `pairings.json`,
the server token, TLS material, and reserved `extensions/`/`skills/` dirs.

`openpi setup` checks pi and installs or updates it (`pi update --self`), so the desktop and
server always drive a current pi.

## Quickstart (from a checkout)

```bash
uv sync
uv run openpi                    # open the app in the current folder
uv run openpi --project ~/repo   # open a specific folder
uv run openpi --connect http://host:7717 --token …   # attach to a server
uv run openpi --connect https://… --tls-ca server.crt # attach over TLS (pinned cert)
uv run openpi token new --name phone                   # issue a revocable device token
uv run openpi doctor             # pi binary, version, session dir, models
uv run openpi sessions           # list pi sessions from disk
uv run pytest                    # 55 tests, headless
uv run pytest -m live            # plus the real-pi contract tests
```

## Remote access

```bash
# on the machine with the repos
uv run openpi serve                       # http://127.0.0.1:7717/?token=…
uv run openpi serve --tls                  # HTTPS (self-signed cert), end-to-end through the relay
uv run openpi serve --host 0.0.0.0        # LAN
uv run openpi serve --relay relay.example.com:7719 --relay-token …   # behind NAT

# on a small public host
uv run openpi relay --token … --public-port 7718 --instance-port 7719
```

The server prints the URL with its token (stored in `~/.openpi/server-token`).
Issue per-device tokens with `openpi token new`; they're revocable and reloaded live. The relay
is a byte pipe, so `--tls` gives end-to-end encryption: the desktop pins the cert with
`--tls-ca`, the browser accepts it once.

Requires `pi` on `PATH` (tested against 1.5.2). Override with `OPENPI_PI_BINARY=/path/to/pi`.

## What it does

- Keep every opened session streaming in the background; switching costs nothing.
- Render text, thinking, tool calls, bash output, compaction, and retries as they happen.
- Answer extension dialogs (`ctx.ui.select/confirm/input/editor`) with real Qt dialogs.
- Show context, token, and cost usage from pi's own numbers.
- Review a working-tree diff, stage, and commit with an agent-written message (M2).
- Branch sessions (`fork`/`clone`), and run sessions inside `git worktree`s (M2).
- Send one prompt to several models and compare, side by side (M3).

It deliberately does **not** reimplement permissions, provider config, MCP, skills, notes, or a
plugin sandbox: pi already has those.

Not there yet: git/diff pane, branch tree, worktrees, multi-run, scheduled tasks.

## Releasing

Tag a version that matches `pyproject.toml` and push it; `.github/workflows/release.yml` runs
the tests, builds, publishes to PyPI under the D5-Interactive org (`secrets.PYPI_TOKEN`), and
creates the GitHub release:

```bash
uv run pytest                    # sanity first
# bump version in pyproject.toml, then:
git tag v0.1.0 && git push --tags
```

## Docs

- [`docs/plan.md`](docs/plan.md) — milestones, risks, open decisions
- [`docs/research/openchamber.md`](docs/research/openchamber.md) — what OpenChamber does and
  what transfers
- [`.agents/pi-protocol.md`](.agents/pi-protocol.md) — pi RPC/JSONL/session-file reference used
  by the client
- [`.agents/architecture.md`](.agents/architecture.md) — module map and invariants
