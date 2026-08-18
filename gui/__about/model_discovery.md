# Model Discovery

**Script:** [Model Discovery (script)](../model_discovery.py)

## Purpose
`ModelDiscovery` — the shared "Refresh models" job: ONE
`ai.list_models()` call on a worker thread, driving a button and a
status label, handing the discovered list back on the tk main loop.

Two hosts run it: [`ApiImageGenPanel`](api_panel.md) (its Image picker,
composed with the access gate and the "show all (debug)" switch) and
[`ModelPickerRow`](model_picker.md) (the reusable text/vision row).
Their `_refresh_models`/`_refresh` and `_apply_models_result`/
`_apply_result` pairs were TWO of the three ratcheted clone groups in
`tests/clone_ratchet.json` (audit `docs/AUDIT-OOP-2026-08-18.md` → R3).

The only real differences between the two hosts are which button and
status var they drive, the found-text wording (`"{n} model(s)
discovered."` vs. `"{n} model(s)."` — each host's own wording, kept)
and what each does with the list — so those four are constructor
arguments.

**The queue stays with the host.** It is the host's own worker channel,
and its tests read it directly (`panel._models_q.get_nowait()`,
`row._q.get_nowait()`) to run a discovery synchronously without Tk's
event loop.

**The cadence is a `start()` argument, not stored.** One host reads it
LATE — a deferred `import gui` for `AI_POLL_MS`, which lives in
[Modal Dialogs](dialogs.md), to avoid a module-level cycle — so the
value is only known at call time. See `ApiImageGenPanel._refresh_models`.

An `ai.AiError` (including `NoKey`) is shown VERBATIM in the status
label: that message IS the existing key-gate text, so there is no
second copy of it to keep in sync.

## Connections

### Uses
- [Worker Queue Poll](worker_poll.md) — `poll_worker_queue` (the tick
  that drains the host's queue)
- [Painter (folder)](../../painter/___painter.md) — `painter.ai`
  (`list_models`, `AiError`), imported inside the worker so a GUI
  import never drags the AI client in

### Used by
- [API Panel](api_panel.md) — `ApiImageGenPanel`'s Image picker
- [Model Picker Row](model_picker.md) — the text/vision row

## Classes

### ModelDiscovery
`start(poll_ms)` disables the button, sets "Discovering models …",
spawns the daemon thread and starts the poll. `apply(msg)` re-enables
the button, then either shows the error verbatim or reports the count
and hands the list to the host's `on_models`.
