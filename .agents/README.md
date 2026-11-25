# .agents/

Durable working notes for agents changing this repo. Read the file that matches your task
before you edit code.

| File | Read it when |
|---|---|
| [`pi-protocol.md`](pi-protocol.md) | touching anything that talks to pi: spawn flags, RPC commands, events, framing, session files |
| [`architecture.md`](architecture.md) | adding modules, changing threading, deciding where state lives |
| [`ui-guidelines.md`](ui-guidelines.md) | building Qt widgets, streaming text, styling, keyboard handling |
| [`server-api.md`](server-api.md) | changing the HTTP/SSE surface the web client and `--connect` consume |
| [`decisions.md`](decisions.md) | wondering why something is the way it is, or wanting to change a settled choice |

Ground rules:

- `docs/plan.md` is the roadmap. If a change is not in the current milestone, say so instead of
  quietly expanding scope.
- pi owns sessions, models, settings, and extensions. openpi reads session JSONL and writes
  only through RPC. Never patch `~/.pi/agent/settings.json`.
- Any claim about pi's protocol comes from the installed docs, not from memory:
  `~/.pi/agent/install/releases/<version>/node_modules/@earendil-works/pi-coding-agent/docs/`.
- `.agents/skills/` is pi's own discovery path for project skills. Do not put openpi notes
  there — this directory holds markdown only.
- The cited pi version is whatever `pi --version` reports on this machine; protocol details in
  `pi-protocol.md` were verified against 1.5.2. Re-check `rpc-commands.md` after a pi upgrade.
