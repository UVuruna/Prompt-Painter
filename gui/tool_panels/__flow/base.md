# Base Tool Settings Panel — Flow

**About:** [description](../__about/base.md)

## Layout

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    H["🖼️ icon + '{JOB_LABEL} — settings' header"]
    subgraph BODY["two-column-dense body"]
        direction LR
        subgraph LEFT["left column"]
            P["Folder… / Files… buttons<br/>+ picked-input label"]
            F["FilterEditor<br/>'which images this run touches'"]
            P --> F
        end
        subgraph RIGHT["right column"]
            E["_build_extra (subclass hook)<br/>always-visible primary control"]
            A["Advanced collapsible<br/>_build_advanced — only if HAS_ADVANCED"]
            FT["_build_footer (subclass hook)<br/>short note"]
            E --> A --> FT
        end
    end
    BTN["Start · Pause · Stop row<br/>(run-state styling)"]
    H --> BODY --> BTN
```

**Advanced toggle** (`_toggle_advanced`): flips
`_advanced_collapsed_var`, then `smooth_transition` covers the mutate
— `_apply_advanced_visibility` packs/unpacks `_advanced_box` and
relabels the gear button, then `_on_layout_change()` fires so the
outer `ScrollFrame` can refit.
