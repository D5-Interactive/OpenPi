# OpenPi — agent instructions

Desktop control room for the pi coding agent. PySide6 + click + msgspec, Python 3.14, managed by
`uv`.

Read [`.agents/README.md`](.agents/README.md) first; it routes you to protocol, architecture,
UI, and decision notes. The roadmap is [`docs/plan.md`](docs/plan.md).

## Rules

- Use `uv` for everything: `uv sync`, `uv run openpi`, `uv add <pkg>`, `uv run pytest`. Never
  `pip`.
- Do not start a milestone that is not in the plan without saying so first.
- pi is the single writer of sessions and settings. openpi talks to it through
  `pi --mode rpc`; read session JSONL, never rewrite it, never edit `~/.pi/agent/*.json`.
- After changing anything protocol-facing, run the live contract test
  (`uv run pytest -m live`) against the installed pi and note its version.
- Home is `~/.openpi/` (`OPENPI_HOME` overrides); `openpi setup` installs/updates pi.
- Releases: `v*` tag matches `pyproject` version; the workflow publishes to PyPI with
  `secrets.PYPI_TOKEN`. Bump the version before tagging.
- Commits in this repo use the D5-Interactive subject format:
  `[ o7 ]: <TITLE> | <CONDENSED DESCRIPTION> | <CONDENSED CHANGES>`.
- Tests stay headless: `QT_QPA_PLATFORM=offscreen` is set by the test fixtures.

## Layout

```
src/openpi/          application code (see .agents/architecture.md for the module map)
tests/               pytest, no network, offscreen Qt
docs/plan.md         milestones and acceptance criteria
docs/research/       OpenChamber research the plan is based on
.agents/             durable notes for agents
```
