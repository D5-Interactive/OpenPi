# UI guidelines (PySide6)

## Threading

- GUI thread: every widget, every model, every palette lookup.
- `PiProcess` reads stdout via `QProcess` signals; records are split on LF from a byte buffer.
  Never assume one signal carries one record, and never touch widgets from a worker.
- File scans, git commands, and diffs go through `QThreadPool` + `QRunnable` with a result
  signal. A synchronous `subprocess.run` on the GUI thread is a bug, even if it feels fast.
- Writes to pi are small JSON lines from the GUI thread under a `threading.Lock`. If a write
  ever blocks, the lock owner logs and the UI shows a degraded state — do not add a writer
  thread until there is evidence it is needed.

## Widget choices

| Need | Use | Not |
|---|---|---|
| Transcript | `QScrollArea` + a column of widgets, one per message | one giant `QTextBrowser` |
| Streaming text block | `QLabel`: plain text while streaming, `markdown-it-py` HTML once the block ends | re-parsing markdown per delta |
| Tool call | `QFrame` with header (name, status, duration) and a collapsible body | dumping JSON into the transcript |
| Session list | `QListWidget` (fine at this scale); move to `QListView` + model if it grows | a widget per session |
| Composer | `QPlainTextEdit` with `Ctrl+Enter` to send, `Enter` for newline (configurable) | `QLineEdit` |
| Diff | `QPlainTextEdit` (read-only) with `QTextCharFormat` per line | QWebEngine |

Code and diffs are monospace and horizontally scrollable. A truncation marker with "show full
output" is better than silently clipping.

## Streaming performance

The event stream is delta-heavy: one long reply can be thousands of `text_delta` records.

1. Coalesce deltas into a buffer; flush to the label at ~10 Hz (a `QTimer`), not per record.
2. Render with `setPlainText` while streaming, then swap to markdown HTML once on
   `text_end` / `message_end`.
3. Keep at most ~300 rendered messages; older ones collapse to "n earlier messages" with the
   full history available through the tree view.
4. Re-rendering the whole transcript on every update is the usual cause of a janky chat window.
5. Rebuild combo boxes only when their source list changes, never on every state signal.

## State and honesty

- Every data surface renders `loading`, `ready`, or `error`. Empty is a `ready` state with zero
  items, never the initial state.
- Session status comes from events (`isStreaming`, `tool_execution_*`, `queue_update`,
  `agent_settled`), never from "last message looks finished".
- After a disconnect, keep the transcript and mark it stale. Do not clear it.

## Styling

- One palette module (`ui/theme.py`) exposing roles (background, surface, border, text, muted,
  accent, success, warning, danger, diff-add, diff-del) and a QSS string built from them.
  Widgets use `setObjectName` + QSS classes; no inline `setStyleSheet` per widget.
- Dark theme first, light theme from the same roles. Respect the system colour scheme when the
  user has not chosen one (`QStyleHints.colorScheme`).
- Keep line height generous (1.4) and body text at the system font; never hardcode pixel sizes.

## Keyboard and accessibility

- Every action reachable by keyboard. Palette (`Ctrl+K`) covers anything not on a shortcut.
- Focus rings visible on the composer, list views, and diff pane. Tab order follows reading
  order.
- `Esc` in the composer clears the queue and aborts, restoring queued text — mirror pi's TUI
  semantics, and document it in the shortcut sheet.
- Announce state changes in the status bar text, not only by colour dots.
