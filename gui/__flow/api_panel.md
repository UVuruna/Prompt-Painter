# API Panel — Flow

**About:** [description](../__about/api_panel.md)

## Layout

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    H["🖼️ icon + 'API Image GEN — settings' header"]
    subgraph BODY["two-column-dense body"]
        direction LR
        subgraph LEFT["left column"]
            D["description line"]
            BS["Background / Style dropdowns"]
            SW["BG removal / Crop / Force Aspect / Upscale<br/>(all default ON)"]
            RK["Report txt / Keep every pipeline step"]
            PC["pause range Spinner pair"]
            GATE["Check API access button<br/>+ status line"]
            MOD["Refresh models button<br/>+ Image/Vision/Text dropdowns"]
            D --> BS --> SW --> RK --> PC --> GATE --> MOD
        end
        subgraph RIGHT["right column"]
            FA["Force Aspect Ratio target<br/>W:H entries + AspectRatioCanvas"]
            UG["Upscale gate<br/>min-side Spinner + FilterEditor"]
            FA --> UG
        end
    end
    BTN["Start · Pause · Stop row"]
    H --> BODY --> BTN
```

**"Check API access" probe** (`_probe_access`): a background thread
makes one cheap `ai.generate_image` call → posts `("ok"|"gated"|
"error", text)` onto `_probe_q` → `_poll_probe` (armed via
`self.after(AI_POLL_MS, ...)`) drains it on the main thread →
`_apply_probe_result` flips `access_gated` and re-styles Start.
`_refresh_models` follows the identical shape over its own
`_models_q`/poll pair, ending in `_populate_model_dropdowns` instead
of a gate flag.

Pseudocode for the gate that actually blocks a run:

```
on Start clicked:
    IF panel.access_gated:
        refuse — show AI_IMAGE_GATE_MESSAGE, spawn nothing
    ELSE:
        spawn _drive_site worker with a fresh ApiImageAdapter()
        # a REAL PaidFeatureRequired hit mid-run still maps to
        # TerminalState inside extract_image — the probe is a
        # convenience, never the only guard
```
