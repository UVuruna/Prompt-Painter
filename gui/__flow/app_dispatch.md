# Queue Pump — Flow

**About:** [description](../__about/app_dispatch.md)

## Algorithm — one queue, one dispatch table

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A(["_drain_queue — every 120 ms on the tk loop"]) --> B{"a message waiting?"}
    B -- no --> Z["re-arm after 120 ms"]
    B -- yes --> C{"drag-resize active
    AND tag is __event__?"}
    C -- yes --> D["buffer it in _pending_events —
    _resize_settled flushes in order
    (owner 2026-07-20)"]
    D --> B
    C -- no --> E["_dispatch(msg)"]
    E --> B

    E --> T{"tag"}
    T -- "__status__" --> T1["status_var.set(text)"]
    T -- "__event__" --> T2["panels.get(site).handle(event)"]
    T -- "__terminal__" --> T3["_handle_terminal(site, retry_after_s)
    — the quota auto-restart timers"]
    T -- "a finish tag" --> T4["panel.finish() unless a restart
    is pending, tool panel run-state off,
    _update_status, _sync_running_state"]
    T -- "a bare string" --> T5["_log(text)"]

    T2 --> H1{"event type"}
    H1 -- item_progress --> H2["_maybe_spawn_checker
    + untick the saved item in Select
    (F3 — the selection is LIVE)"]
    H1 -- item_checked --> H3["_maybe_spawn_fixer"]
    H1 -- anything else --> H4["nothing beyond the panel"]
```

`panels.get(...)` — never `panels[...]` — is the deliberate guard for a
late event arriving after its panel was closed.

The two AI hooks hang off `__event__` rather than off the runner, which
is exactly what kept `painter/runner.py` unchanged when each landed: the
parallel Checker AI rides the SAME `item_progress` event the dashboard
row was just built from, and the Fixer AI rides the checker's own
`item_checked` result, posted back onto this same queue.

Pseudocode (language-neutral):

    FUNCTION drain_queue():
        WHILE the queue is not empty:
            msg = queue.get_nowait()
            IF resize_active AND msg is an __event__ tuple:
                pending_events.append(msg)      # flushed by _resize_settled
                CONTINUE
            dispatch(msg)
        after(120 ms, drain_queue)               # re-arm

    FUNCTION dispatch(msg):
        IF msg is not a tuple: log(str(msg)); RETURN
        SWITCH msg[0]:
            "__status__":   status_var.set(msg[1])
            "__event__":    panel = panels.get(msg[1])
                            IF panel: panel.handle(msg[2])
                                      IF type == item_progress:
                                          maybe_spawn_checker(...)
                                          untick the saved item in Select
                                      ELIF type == item_checked:
                                          maybe_spawn_fixer(...)
            "__terminal__": handle_terminal(msg[1], msg[2])
            a finish tag:   finish the panel unless a restart is pending,
                            then update_status + sync_running_state
