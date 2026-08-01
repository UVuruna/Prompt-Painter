# Agent Panel — Flow

**About:** [description](../__about/agent_panel.md)

## Layout

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    H["🖼️ site logo + name + cooldown info"]
    subgraph PIPE["Pipeline group"]
        direction TB
        BG["BG removal switch<br/>ExpandableSwitch → mode/tolerance/reach"]
        CR["Crop switch (plain)"]
        FA["Force aspect ratio switch<br/>ExpandableSwitch → W:H + AspectRatioCanvas"]
        UP["Upscale switch<br/>ExpandableSwitch → min-side + FilterEditor"]
        KA["Keep every pipeline step (plain)"]
        BG --> CR --> FA --> UP --> KA
    end
    subgraph RUN["Run behavior group"]
        direction TB
        RB["Report / Safer retry / Continue nudge (plain)"]
        CK["AI checker switch<br/>ExpandableSwitch → prompt-match toggle<br/>+ Fixer AI (auto-fix + api/website mode)"]
        PC["Pacing section<br/>ExpandableSection → pause range,<br/>action-delay range, on-degrade"]
        RB --> CK --> PC
    end
    subgraph PROMPT["Prompt group"]
        direction TB
        BGD["Background dropdown + custom colour wheel"]
        ST["Style dropdown"]
        NC["New chat mode dropdown"]
        HL["F7 Helpers row (no_mirror / no_empty_space / no_grainy)"]
        BGD --> ST --> NC --> HL
    end
    BTN["Start · Pause · Stop row"]
    H --> PIPE --> RUN --> PROMPT --> BTN
```

**`_stack_groups`** grids the three groups as one vertical stack — the
panel's width is its LEFT-column parent's, never the window's.

**Restore-time hush (`apply_settings`):** a Tk write-trace cannot tell
a restore `.set()` from a click, so the whole round-trip runs under
`quiet_restore(*self._expanders())` — otherwise every ON switch would
auto-expand its sub-panel on every app open instead of staying compact.

Pseudocode for the per-switch expander contract (`ExpandableSwitch`,
shared by BG removal / Force aspect ratio / Upscale / AI checker):

```
ON switch flips true (a real click, not a restore):
    build the sub-panel body once (build_sub), if not built yet
    auto-expand it (reveal the body, rotate the caret open)
switch flips false:
    fold the body away (hide it, rotate the caret closed)
    the sub-panel's OWN state (FilterEditor rows, canvas ratio) is
        NOT torn down — it is just hidden, so re-enabling shows the
        same fine-tune again
caret click (independent of the switch's own on/off):
    toggle body visibility only — does not touch the switch itself
```
