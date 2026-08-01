# Tool + AI-Checker Dashboard Panels + Grid — Flow

**About:** [description](../__about/tool_dash.md)

## ToolPanel zones

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    HDR["JobPanel header (logo + name + Close)"]
    PB["progress bar"]
    MV["metric line: avg N% <tool metric> · X changed, Y skipped"]
    TV["time line: total + per-image average"]
    subgraph TREE["collection → folder → image tree"]
        direction TB
        COLS["Before/After columns<br/>(dimensional tools only — BG removal drops them)"]
        ROWS["CHANGED rows (striking) /<br/>SKIPPED rows (muted)"]
        COLS --> ROWS
    end
    HDR --> PB --> MV --> TV --> TREE
```

Double-click routing (`_on_activate`):

```
image row    → before/after viewer for THIS image, Restore reverts it
folder node  → before/after viewer for THIS FOLDER's changed images,
               RESTORE ALL reverts only this folder
top node     → before/after viewer for the WHOLE job's changed images,
               RESTORE ALL reverts everything
```

## AiCheckPanel zones

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    HDR["JobPanel header (logo + name + Close)"]
    PB["progress bar"]
    MV["metric line: N flagged · M OK · (K error(s))"]
    TV["time line: total + per-image average"]
    subgraph TREE["folder → image tree"]
        direction TB
        DR["Defects / Time / First-defect columns"]
        RW["flagged rows (striking, defect count) /<br/>OK rows (muted) / error rows"]
        DR --> RW
    end
    ACT["Send flagged to generator · Clear flags"]
    HDR --> PB --> MV --> TV --> TREE --> ACT
```

## DashGrid — two modes (F4e)

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    IN(["relayout() — active panel set changed,<br/>or set_mode() flipped, or a resize settled"]) --> M{"mode"}
    M -- GRID --> W["columns = fit(window width / DASH_CARD_MIN_W),<br/>clamped to [1, DASH_GRID_MAX_COLS, active count]"]
    W --> ROWMAJOR["place panels row-major in JOB_ORDER"]
    M -- SLIDER --> ONE["clamp slider_idx to [0, active count - 1]"]
    ONE --> SHOW["show ONLY that one panel, full width,<br/>with a prev/next arrow row above it"]
    ROWMAJOR --> EMPTY{"no active panels?"}
    SHOW --> EMPTY
    EMPTY -- yes --> PH["muted placeholder:<br/>'No jobs yet …'"]
```
