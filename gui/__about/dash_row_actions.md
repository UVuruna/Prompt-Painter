# Dashboard Row Actions

**Script:** [Dashboard Row Actions (script)](../dash_row_actions.py)

## Purpose
`RowActionsMixin` — what a selected dashboard ROW can OPEN. Split out
of `dash_panels.py` under THE STRUCTURE LAW (owner 2026-08-11): the
live progress panel's job is to SHOW a run as it happens, while these
three are what the owner reaches for once a row is already there.
Different responsibility, different lifetime — they read finished
state off disk and open windows, they never touch the event stream.

| Action | Trigger | Opens |
|--------|---------|-------|
| `_show_selected` | double-click on a row | the image viewer, via the panel's `_on_show` callback with the row's `_node_info` dict |
| `_show_steps` | the "Steps…" button | `StepRestoreWindow` over the row's per-step `JobTemp` backups |
| `_show_check` | the "Check…" button | `DocWindow` with the parallel Checker AI's report for that image |

## Why a mixin
It is mixed into `DashPanel` AHEAD of `JobPanel`, so it may rely on
the panel's own attributes (`tree`, `_node_info`, `out_base`,
`slot_key`, `_check_results`, `_on_show`, `jobtemp`) without
redeclaring them. It is never instantiated alone.

## Late binding, deliberately
`DocWindow`/`StepRestoreWindow` are reached through a deferred
`import gui` INSIDE the methods, never a module-level
`from .viewers import ...` — the established idiom here (see
`gui.viewers`'s own `AI_POLL_MS` read). Several tests
(`test_gui_checker.py`, `test_gui_pipeline.py`, `test_gui_fixer.py`)
`monkeypatch.setattr(gui, "DocWindow", fake)` and expect the PATCHED
class to fire; a top-of-module import would bind the real class at
import time and never see the patch.

## Empty-hands cases are informational, never errors
No row selected, no `JobTemp`, no kept stages, no check result yet —
each shows a `messagebox.showinfo` saying what to do instead
("turn on this site's 'AI checker' switch before Start"), because
none of them is a fault: they are the owner asking a question the
data cannot answer yet.

---

- [Dashboard Job Panel Base + Site Panel](dash_panels.md) — the panel this mixes into
- [GUI folder](../___gui.md) — the folder index
