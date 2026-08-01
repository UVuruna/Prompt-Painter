# Image Checker Settings Panel — Flow

**About:** [description](../__about/image_checker.md)

## Layout

Fills the [Base Tool Settings Panel](../__flow/base.md)'s
`_build_extra` and `_build_footer` zones; `HAS_ADVANCED = False` so
there is no Advanced gear at all:

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    subgraph EXTRA["_build_extra — optional F6 sheet source"]
        S1["Sheet file… / Sheets folder… buttons"]
        S2["picked-path label<br/>(none = quality-only check)"]
        S1 --> S2
    end
    FOOT["_build_footer — model + pacing + flags-location note"]
    EXTRA --> FOOT
```

Start is wired straight to `PainterGui._start_ai_check`, bypassing
`build_func` — no engine-callable zone exists on this panel.
