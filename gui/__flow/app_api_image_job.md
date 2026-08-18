# API Image Job — Flow

**About:** [description](../__about/app_api_image_job.md)

## Algorithm — `_start_api_image` (the paid-API job's whole start)

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A(["Start clicked on the API Image GEN panel"]) --> B{"panel.access_gated?"}
    B -- yes --> B1[["show AI_IMAGE_GATE_MESSAGE, do nothing —
    defense in depth beside the panel's own guard"]]
    B -- no --> C["read the panel's settings ONCE:
    output folder, queue, prompt suffix, pacing"]
    C --> D{"queue empty / no output folder?"}
    D -- yes --> D1[["loud messagebox, no worker"]]
    D -- no --> E["_compose_post_save: the SAME pipeline
    closure the browser sites use"]
    E --> F["build ApiImageAdapter — a SiteDriver-shaped
    stand-in: attach/close/await_done no-op,
    extract_image makes the real ai.generate_image call"]
    F --> G["spawn the worker thread"]
    G --> H["run_sheet(...) — the SAME loop, so pacing,
    post-save, the dashboard and the report
    are ONE code path, not two"]
    H -->|"TerminalState (zero quota)"| I["PERMANENT stop — the paid key
    has no free-tier quota to wait for"]
    H -->|"success / other errors"| J["log, continue the queue"]
    I --> K
    J --> K["finally: post __worker_done__ (ALWAYS)"]
    K --> L["_update_status, _sync_running_state"]
```

Every message this worker posts — progress, status, the finish tag —
lands in the ONE queue drained by [Queue Pump](app_dispatch.md); the
worker never touches a widget itself.

The adapter's own contract (what `submit_prompt` / `submit_with_image` /
`extract_image` do, and how a free-tier-exhausted 429 becomes
`driver.TerminalState`) lives with the adapter, in
[API Panel](../__about/api_panel.md).
