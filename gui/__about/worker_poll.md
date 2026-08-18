# Worker Queue Poll

**Script:** [Worker Queue Poll (script)](../worker_poll.py)

## Purpose
`poll_worker_queue(widget, q, on_result, *, poll_ms, after_attr)` — the
ONE home for the worker-thread → tk main-loop handoff every AI panel and
dialog in this GUI performs.

A background thread may never touch a widget, so each job puts its
result on a private `queue.Queue` and the tk loop drains it on a
`widget.after` tick. The function arms that tick, re-arms itself while
the queue is empty, and hands the first message to `on_result` on the
main thread — where touching a widget is legal.

The pending `after` id is written back ONTO THE WIDGET under
`after_attr` (`None` while a tick is executing), so a host that cancels
its own loop on teardown keeps working exactly as before. A widget
destroyed mid-work ends the loop silently: once the window is gone the
worker's message is moot.

**Why a free function and not a mixin.** Six methods across five
classes carried the identical eight-statement loop —
`ApiImageGenPanel._poll_probe` and `._poll_models`, `_AiDialog._poll`,
`ModelPickerRow._poll`, `SheetGenPanel._poll`, `DocWindow._poll_fix` —
and three of them were RATCHETED as an accepted clone in
`tests/clone_ratchet.json`. [API Panel](api_panel.md) used to defend
them: the hosts' base classes differ (`ttk.Frame` panels vs. the
`tk.Toplevel`-derived `_AiDialog`), so no mixin could hold them all.
That objection was true of a mixin and false of a FREE FUNCTION, which
needs no shared base at all. The owner accepted reversing the note on
2026-08-18 (`docs/AUDIT-OOP-2026-08-18.md` → R3), and the clone ratchet
went to empty.

**What each host keeps.** Its own queue, its own cadence constant
(`AI_POLL_MS` / `MODEL_PICKER_POLL_MS` / `SHEETGEN_POLL_MS`) and its own
one-line arming method (`_arm_poll` / `_arm_probe_poll` /
`_arm_fix_poll`). Those genuinely differ, and they are what makes each
loop that host's own.

## Connections

### Uses
Nothing but `queue` and `tkinter` — no project import, so any widget
can call it without an import cycle.

### Used by
- [Modal Dialogs](dialogs.md) — `_AiDialog._arm_poll`
- [API Panel](api_panel.md) — `ApiImageGenPanel._arm_probe_poll`
- [Model Discovery](model_discovery.md) — `ModelDiscovery.start`
- [Model Picker Row](model_picker.md) — through `ModelDiscovery`
- [Sheet Generator Panel](sheetgen_panel.md) — `SheetGenPanel._arm_poll`
- [Doc Window](doc_window.md) — `DocWindow._arm_fix_poll`

## Classes
This module has no classes — one module-level function.
