# server API (openpi serve ↔ clients)

The contract between `openpi serve`, the browser client, and the desktop client
(`openpi --connect`). One server owns the sessions; clients attach over HTTP + SSE. If the
server's Python types drift from this, update this file in the same change.

## Auth

Two token classes. Sent as an `X-Openpi-Token` header on POST/GET, or as `?token=` for
EventSource (which cannot set headers).

- **Admin token** — `~/.openpi/server-token` (or `$OPENPI_HOME`), printed on start. Opens
  everything and manages pairings.
- **Device tokens** — issued per device (`openpi token new`), stored in
  `~/.openpi/pairings.json`, revocable. Accepted for all session endpoints, refused
  for the pairing endpoints below. The server reloads them on change, no restart.

## Endpoints

| Method | Path | Body | Result |
|---|---|---|---|
| GET | `/` | — | the browser client (no token needed) |
| GET | `/api/state` | — | `{cwd, sessions:[{key,cwd,file,title,busy}]}` |
| POST | `/api/open` | `{cwd?, session?}` | `{key}` — new session, or reopen `session` path |
| GET | `/api/sessions/{key}/events` | — | SSE stream (see below) |
| POST | `/api/sessions/{key}/prompt` | `{message, behavior?}` | `{ok}` |
| POST | `/api/sessions/{key}/steer` | `{message}` | `{ok}` |
| POST | `/api/sessions/{key}/follow_up` | `{message}` | `{ok}` |
| POST | `/api/sessions/{key}/abort` | — | `{ok}` |
| POST | `/api/sessions/{key}/clear_queue` | — | `{ok}` |
| POST | `/api/sessions/{key}/rename` | `{name}` | `{ok}` |
| POST | `/api/sessions/{key}/model` | `{provider, id}` | `{ok}` |
| POST | `/api/sessions/{key}/thinking` | `{level}` | `{ok}` |
| POST | `/api/sessions/{key}/stats` | — | `{ok}` (forces a stats refresh) |
| POST | `/api/sessions/{key}/answer` | `{id, value?, confirmed?, cancelled?}` | `{ok}` — answers an extension dialog |
| POST | `/api/pairings` | `{name?}` (admin) | `{id, name, token}` |
| GET | `/api/pairings` | — (admin) | `{pairings:[{id,name}]}` (no tokens) |
| DELETE | `/api/pairings/{id}` | — (admin) | `{ok}` |

Errors are `{error: str}` with an HTTP status (400 bad action, 401 bad token, 404 unknown
session, 503 hub busy).

## Event stream (SSE)

`text/event-stream`, one JSON object per `data:` line, `: ping` every 15 s, `Connection: close`,
`X-Accel-Buffering: no`. First event is a `snapshot`, then `patch`es as the transcript/state
changes, plus `ui` and `notify`.

```
snapshot = {t:"snapshot", key, blocks:[Block], state, stats, busy, queued:[s,f],
            models:[{id,provider,name}], levels:[str], commands:[{name,description}]}
patch    = {t:"patch", key, upsert?:[Block], order?:[uid], state?, stats?, busy?, queued?}
ui       = {t:"ui", key, request:{id,method,title,message,options,placeholder,prefill,timeout}}
notify   = {t:"notify", key, message, kind}
```

`Block = {uid, kind:user|text|thinking|tool|bash|notice, text, name, args, result, is_error,
duration_ms, meta}`. `order` is the full block-id list and appears only when it changed; `upsert`
carries blocks whose content changed or are new. `state = {name, thinking, model:{id,provider,
name}|null, is_streaming}`; `stats = {cost, context:{tokens,window,percent}|null}`.

Clients keep `uid → Block` and an order list, apply `upsert` then `order`, and render. The
server never sends raw pi events, so the browser does not re-implement compaction or tool-result
linking.

## Invariants

- Only `GET /` is unauthenticated. Everything under `/api/` needs an admin or device token.
- TLS: `openpi serve --tls` serves HTTPS with a self-signed cert (`.agents/pi-protocol.md`
  unrelated; see `server/tls.py`). The desktop client trusts it with `--connect https://… --tls-ca
  server.crt`; the relay pipes ciphertext, so this is the end-to-end encryption path.
- SSE streams are per-session and start with a full snapshot, so a dropped connection is
  resync-safe on reconnect.
- All commands are marshalled onto the server's Qt thread; a slow hub returns 503 rather than
  hanging.
- Extension dialogs are answered by POST `answer` with the `request.id`; pi resolves a timed-out
  dialog itself, so a late answer is ignored server-side.
