# OpenChamber: research notes

Target: <https://openchamber.dev/> and <https://docs.openchamber.dev/> (all 40+ doc pages),
plus the GitHub repo layout. Captured 2026-11-25, OpenChamber 2.8.0. Purpose: what openpi
should copy, what it should not, and why.

## 1. What it is

A visual workspace around OpenCode. OpenCode is the agent; OpenChamber is the screen: project
and session management, streaming chat with tool activity, diff review, git, terminals,
scheduled tasks, goals, and remote access. MIT, TypeScript monorepo, Bun, Node ≥ 24.14.

Four deliveries over one server: Electron desktop (mac/win/linux), CLI-served web app + PWA,
VS Code extension (talks to OpenCode directly, no server features), and mobile shells
(Capacitor) that connect to an existing server.

**Runtime model.** The server (Express 5 + Vite SPA) starts and supervises a *managed OpenCode
server* child process on an allocated local port, bound to `127.0.0.1`. It will instead attach
to an external `OPENCODE_HOST`/`OPENCODE_PORT`, or a shared `opencode serve --service` daemon.
Health checks every 15 s, 20 consecutive failures → restart; UI shows a restarting state and
queues requests. Transport: REST under `/api/*` for commands, plus SSE from OpenCode
translated and re-fanned as WebSocket frames (`/api/event/ws`, `/api/global/event/ws`) with
15 s heartbeats, cursor replay, and a 16 MiB buffer that closes slow clients with `1013`.

**Persistence.** No SQL for app state: one data dir (`~/.config/openchamber`) with atomic JSON
files for settings, auth/pairing, projects, extensions, notes/todos/plans, scheduled tasks,
goals. Conversation history belongs to OpenCode, not OpenChamber. Chat-only (no-repo) sessions
get their own folder.

*Lesson for openpi:* the client/server split exists because OpenChamber must serve browsers
and phones. pi has no server, so openpi does not need one — it can spawn pi per session and be
the only owner of UI state.

## 2. Object model

- **Project** — a tracked folder; switching project switches cwd, sessions, git, notes.
  Settings: name, colour, icon, env vars, optional environment command (`direnv export json`)
  whose output feeds git/terminals/actions but not the agent.
- **Session/chat** — a conversation. Two homes: project sessions (cwd = project or a worktree)
  and repo-less "Chats" (one folder per day). Worktree sessions are one sidebar row per
  worktree, auto-named after the agent's task.
- **Work** — a sidebar unit, not a session: a worktree plus all its sessions, or a project
  session plus its subagents/forks/reviews. "In work" is live state, not derived from history;
  it stays until the user marks it done. Chats, archived, scheduled runs, and review sessions
  are excluded.
- **Folder** — server-side session grouping, shared across devices; collapse state per device.
- **Note / Todo / Plan** — note = markdown card, first line is the title; todo = checklist item
  with optional plan link and dependency locks; plan = markdown file whose progress is parsed
  from a `## Steps` heading and `- [ ]` items. Stored locally by default, or in
  `.openchamber/notes-todos.json` / `.openchamber/plans` opt-in. Loops live in
  `.agents/loops/*.md` (cron in frontmatter, disabled by default).
- **Goal** — one per session: objective plus optional token budget. A separate cheap model
  audits each reply against it (keep going / done / blocked), with hard stops on budget,
  continuation cap, and errors.
- **Lead** — a session that owns a direction of work, spawns child sessions, reviews their
  reports, archives them, and keeps a brief that is re-injected when the conversation is
  compacted.
- **Workflow** — an agent-written JS script that names agents per phase, runs in the
  background behind an approval card, concurrency 8, 200 agents per run, resumable.

## 3. Chat surface

Composer with model/agent/thinking pickers, `@` file/agent mentions, `#` snippets, `$` skills,
`/` commands at position 0. Context gauge in the composer (green / amber ~75% / red), tool
activity inline, permission prompts inline. After 60 s idle an optional small model writes a
recap plus a suggested next message. Queue/steering exists in OpenCode; the UI surfaces it.

**Permissions** are OpenCode rules (`allow`/`deny`/`ask`). Three modes decide who answers
"ask": *Ask every time*, *Safety net* (a classifier model decides risk with a 4 s budget;
never auto-allows on failure), *Accept everything*. Mode is server state, inherited by
subagents, per-session override via a shield button. pi has no per-tool approval, so openpi
renders only extension dialogs and cannot copy this model.

## 4. Git

The UI does staging, per-file diffs, branches, push/pull/fetch, history, stash, worktree
management; the *agent* only writes text: commit messages (from the current session's model),
PR titles/bodies, conflict resolution (proposes per-file strategy, waits for confirmation).

Worktrees: one `git worktree` per branch, created from a new branch, existing branch, PR, or
issue; base defaults to the remote default branch; project `setupWorktree` commands run right
after creation; folder name or branch name as label; quick worktree uses a placeholder branch
renamed to the agent's task name while unpushed. Archive removes the folder but keeps branch,
sessions, and uncommitted work restorable; delete optionally removes local and remote branch.
Git-ignored files are not kept.

**Changes walkthrough**: an LLM pass with structured output over a scoped diff (uncommitted /
staged / unstaged / branch / PR). Output is an ordered list of *stops* anchored to exact code,
each tagged Key change / Context, with optional observations (Decision, Cost, Limitation,
Difference, Untested). Unanchored hunks are reported as "not covered"; moved code becomes
"Outdated". Cached by diff content + language + model; regenerate or re-author.

## 5. Orchestration

- **Scheduled tasks**: daily/weekly/once/cron, prompt may be a slash command, provider/model/
  agent, optional "run as goal". Fires only while the server is running; records last run,
  success, error, and the session it created. Loop files (cron only) live in the repo and are
  off by default until approved; a changed schedule/model/prompt needs re-approval.
- **Multi-run**: one prompt to N models; each run gets its own session and optionally its own
  worktree + branch; compare side by side; "fusion" merges the answers into one.
- **Agent control tool**: an in-agent tool (`openchamber`, `openchamber_schedule`) that lists
  projects and models, creates/follows up/fork sessions, creates worktree sessions, lists
  recent sessions with status, and schedules tasks. Cannot delete anything or run shell.
- **Auto model routing**: classification provider picks a category (Trivial / Research /
  Implement / Hard) per message with a confidence; falls back under 60% confidence, >4 s, or
  error. Categories are editable with their own model, thinking level, agent.

## 6. Hosts, integrations, models

Git hosts: GitHub/GHE, GitLab, Gitea, Forgejo/Codeberg, Gerrit — inferred from the remote,
multiple accounts per host, existing `gh` sessions reusable. Attaching an issue or PR to a
message is always manual (composer `+` or paste URL); it becomes a chip on the next message.
Integrations catalog (~150 services) installs a service's MCP server at user scope with one
click. MCP servers: local command+env or remote URL+headers, personal/project scope.
Providers writable from the UI: API key or device flow; custom OpenAI-compatible endpoints
(id, baseUrl, key, model ids, reasoning levels, headers, mTLS).

## 7. Remote access and security

- Pairing is token-based per device (QR, single-use, expiring); the UI password is a different
  credential. Scopes: this computer / LAN / anywhere.
- Private Relay: both sides dial out, relay forwards E2E-encrypted frames without keys.
- Tunnels: cloudflare, ngrok, tailscale serve/funnel; one per instance; still enforce the
  connect token.
- Default bind loopback. Reverse proxy must pass WebSocket, disable SSE buffering, gzip in
  exactly one layer, forward `Host`/`X-Forwarded-*`, and be listed in trusted proxies.
- Desktop extras: remote instances over SSH (managed or external, with `-L`/`-R`/`-D`
  forwarding), an embedded Chromium browser panel the agent can drive (open/read/click/type,
  no arbitrary JS), and auto-update from GitHub releases.
- Enterprise policy file forces loopback, disables tunnels, restricts extensions, hides
  catalogs.

## 8. Extensions

Extensions are untrusted iframe panels: a `package.json` `openchamber` manifest
(`apiVersion: 1`) plus a classic IIFE bundle in `panel/main.js` — the host never builds.
Contributions: panel, attach/dialog, full page, status section, file editors, message/session
actions, commands, custom tool renderers, provider logos, link resolution, mentions, blocks
with answer forms, marks, integrations, host services with cron, session-event hooks.
Capabilities (`prompt`, `sessions`, `files`, `model`, `shells`, `microphone`) are granted once
at install and re-prompted when they grow. The host API (`connectHost()`) pushes context
(theme tokens, session, device, surface) and lets a panel toast, open URLs, compose prompts,
start sessions in worktrees, make host-proxied requests with an injected token, touch files
inside granted globs (2 MiB atomic), call a `generate` LLM helper, and use per-extension
storage with quotas. A service host can start/send/stop sessions and answer permission forms.

*Relevance:* openchamber needed this because OpenCode has no UI extension points. pi extensions
already run in-process and can call `ctx.ui`; openpi's job is to render those requests, not to
invent a second extension model.

## 9. Repo architecture (what the source says)

`packages/web` (Express server + ~60 feature runtimes + CLI + Vite SPA), `packages/ui` (React
19, zustand stores, a sync layer that turns SSE into normalized per-directory/session stores,
Tailwind 4 + Radix, CodeMirror 6, sql.js, streamdown), `packages/sdk` (zod schemas, iframe
protocol, host/guest clients), `packages/electron`, `packages/vscode`, `packages/mobile`,
`packages/extensions` (built-ins + registry).

Notable client rules worth stealing conceptually:
- Three-state snapshots (`loading` / `ready` / `error`) — a failed fetch must never look empty.
- Live activity comes from the live channel, not from history; idle after error keeps a failed
  outcome.
- Delta coalescing server-side; cursor replay on reconnect; `replayReset` drops local cache.
- Under a stalled stream the UI still stays usable and shows a restarting state.

## 10. What transfers to pi

| OpenChamber | pi | openpi |
|---|---|---|
| Server spawns/supervises `opencode serve` | RPC child process per session | Spawn `pi --mode rpc` per session; no server |
| REST + WS event fan-out | JSONL stdin/stdout events | Direct pipe; framing rules in `.agents/pi-protocol.md` |
| Sessions in OpenCode storage | JSONL session files with a tree | Read-only index; all writes via RPC |
| Permissions with allow/deny/ask + classifier | No per-tool approval | Render extension dialogs only; project trust at spawn |
| Worktree = session cwd | `--session` keeps its own cwd | `git worktree` + spawn in that dir |
| Multi-run over models | Cheap to spawn | N processes, side-by-side compare |
| Scheduled tasks while server runs | Nothing | Scheduler inside the app, same limitation |
| Goals with an audit model | Nothing built in | One-shot auditor process, or later |
| Extensions with iframe sandbox | In-process extensions with `ctx.ui` | Render `extension_ui_request`; no sandbox to build |
| Remote/mobile/relay | None | Out of scope |
| Notes/todos/plans in a private store | Agent reads repo files | Use repo markdown only |
