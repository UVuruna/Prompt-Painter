# Queue Pump (PainterGui mixin)

**Script:** [Queue Pump (script)](../app_dispatch.py) ·
**Flow:** [diagram](../__flow/app_dispatch.md)

## Purpose
`QueuePumpMixin` — the worker-queue pump and its dispatch table, one of
`PainterGui`'s responsibility slices (see [GUI (folder)](../___gui.md)
for the whole composition).

Every background worker in this app — the site run loops, the API image
job, the standalone tools, the Checker AI and the Fixer AI — speaks to
the window through ONE `queue.Queue`, and never touches a widget itself.
This module is the other end of that pipe: `_drain_queue` runs on the tk
loop every 120 ms and drains everything waiting; `_dispatch` applies
exactly one message, on the main thread.

**The message tags ARE the table:**

| Tag | Applied as |
|-----|-----------|
| `__status__` | the status bar's text |
| `__event__` | the addressed dashboard panel's own `handle(...)`, plus the two AI hooks that hang off it |
| `__terminal__` | quota — handed to `_handle_terminal`'s auto-restart timers |
| a per-site finish tag | the panel's `finish()`, the tool panel's run state, `_update_status`, `_sync_running_state` |
| a bare string | a log line |

Two hooks hang off `__event__` rather than off the runner, which is what
kept `painter/runner.py` unchanged when each landed: an `item_progress`
event spawns the parallel Checker AI (`_maybe_spawn_checker`, GUI rework
Phase 16) and unticks the saved item in Select (F3, the `_vN` landmine —
the selection is LIVE, so a restart re-submits only the REMAINDER); the
checker's own `item_checked` result, posted back onto this SAME queue,
spawns the Fixer AI (`_maybe_spawn_fixer`, Phase 20).

**Mid drag-resize, `__event__` messages are BUFFERED** rather than
applied (owner 2026-07-20): a dashboard event re-renders tree rows and
live labels per frame on top of the drag's own relayout work.
`_resize_settled` flushes them in order afterwards.

**Why it is its own module.** Split from `gui/app_jobs.py` on 2026-08-18
(audit [AUDIT-OOP-2026-08-18](../../docs/AUDIT-OOP-2026-08-18.md) → R5),
the exact three-way split the structure ratchet had already named. The
tag chain moved VERBATIM — turning it into a literal table is a separate
change with its own risk, and that refactor changed no behaviour.

No `__init__` here — every attribute it reads is set by
`BuildMixin.__init__`, and `_handle_terminal` / `_tool_panel_key`
([Site Jobs](app_jobs.md)) and `_maybe_spawn_checker` /
`_maybe_spawn_fixer` ([Checker & Fixer](app_checker_fixer.md)) resolve
through the shared `PainterGui` MRO onto their sibling mixins.

## Connections

### Uses
- [Config (subfolder)](../../painter/config/___config.md) —
  `DEGRADE_CONTINUE`, `DEGRADE_WAIT`
- [Site Jobs](app_jobs.md) — `_handle_terminal`, `_tool_panel_key`,
  `_update_status`, through the shared MRO
- [Checker & Fixer](app_checker_fixer.md) — `_maybe_spawn_checker`,
  `_maybe_spawn_fixer`
- [Dashboard Panels](dash_panels.md) — each panel's `handle(...)`

### Used by
- [GUI (folder)](../___gui.md) — `gui/app.py` composes it into
  `PainterGui`
- every worker in the app, indirectly — this is the one way a background
  thread reaches the window

## Classes

### QueuePumpMixin
`_drain_queue`, `_dispatch`. Never instantiated alone.
