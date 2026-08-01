# Geometry Settings Panels — Flow

**About:** [description](../__about/geometry.md)

## Layout

Three independent panels, each filling the
[Base Tool Settings Panel](../__flow/base.md)'s `_build_extra` /
`_build_advanced` / `_build_footer` zones differently:

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    subgraph CROP["CropSettingsPanel — Advanced only, no _build_extra"]
        CA["clean-border-halo switch"]
        CB["margin px"]
        CC["ink alpha (0-255)"]
        CD["min ink px"]
    end
    subgraph UPSCALE["UpscaleSettingsPanel — _build_extra only, HAS_ADVANCED=False"]
        UA["min side spinner (px)<br/>+ note: Filter below decides which images qualify"]
    end
    subgraph ASPECT["AspectSettingsPanel — _build_extra + _build_footer, HAS_ADVANCED=False"]
        AA["W / H entries"]
        AB["AspectRatioCanvas<br/>(live drag, two-way synced)"]
        AC["⚠ non-proportional-stretch warning (footer)"]
        AA <--> AB
    end
```

`CropSettingsPanel` has no `_build_extra` (its body is the base chrome
alone, plus Advanced); `UpscaleSettingsPanel`/`AspectSettingsPanel`
have no Advanced collapsible at all (`HAS_ADVANCED = False`) — their
one primary control is always visible instead.
