# Site Jobs Mixin — Flow

**About:** [description](../__about/app_jobs.md)

## Algorithm — `_drive_site` (one worker thread's whole run)

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A(["worker thread starts"]) --> B["ensure Chrome + attach driver<br/>(browser sites only; API adapter no-ops)"]
    B --> C["FOR EACH queued sheet, in order"]
    C --> D{"stop requested?"}
    D -- yes --> Z1["break — remaining sheets NOT run"]
    D -- no --> E["run_sheet(...)<br/>pause/stop checked between ITEMS"]
    E -->|"TerminalState (quota)"| F{"retry_after_s known?"}
    F -- yes --> G["schedule auto-restart<br/>(reset + random 30-120s)"]
    F -- no --> H["PERMANENT stop —<br/>e.g. API Image GEN's zero quota"]
    G --> Z2["break site loop"]
    H --> Z2
    E -->|"DriverError"| Z3["log, break — progress saved,<br/>fix cause and restart"]
    E -->|"success"| C
    C -->|"all sheets done"| Y["log summary"]
    Z1 --> FIN
    Z2 --> FIN
    Z3 --> FIN
    Y --> FIN["finally: driver.close()<br/>post __worker_done__ (ALWAYS)"]
```

## Pseudocode — `_compose_post_save` (the pipeline composer)

```
FUNCTION compose_post_save(key, panel=None):
    panel = panel OR self.agents[key]
    read panel's do_bg / do_crop / do_aspect / do_upscale switches ONCE
    IF none are on: RETURN None
    IF postprocess deps missing: RETURN the problem string
    read upscale params/conditions, force-aspect W:H, bg fine-tune ONCE

    RETURN post_save(path):
        steps = []
        IF do_bg: append ("REMOVE BG", remove_background)
        IF do_crop: append ("CROP", crop_transparent)
        IF do_aspect: append ("ASPECT", change_aspect)
        IF do_upscale: append ("UPSCALE", gate_and_upscale)
        RETURN run_pipeline_steps(path, steps, temp, keep_all_steps, on_cap)
```

Steps ALWAYS run in this fixed order — BG → Crop → Aspect(force) →
Upscale — regardless of which subset is ticked; with Force Aspect off
(the default) this is byte-identical to the pre-pipeline behavior.

## Algorithm — `_toggle_pause_job` (one handler, every `JOB_ORDER` kind)

```mermaid
flowchart TB
    A(["btn_pause clicked for kind"]) --> B["flip kind's threading.Event<br/>+ membership in _paused"]
    B --> C["AgentPanel.set_paused (if a site)"]
    C --> D["DashPanel/ToolPanel.set_paused<br/>(every kind has one)"]
    D --> E["that kind's settings panel<br/>.set_paused (if it has one)"]
    E --> F{"now paused AND<br/>view == 'running'?"}
    F -- yes --> G["reveal this kind's own<br/>inline settings surface"]
    F -- no --> H["no layout change"]
```

The actual wait is a shared, public function
(`painter.runner.wait_while_paused`) polled between items by three
independent call sites: `_drive_site` (via `run_sheet`), `_run_tool_job`,
and `_run_ai_check_job` — a Stop always wins over a pending Pause at
every one of them.
