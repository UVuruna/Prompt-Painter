# Pure Logic Helpers — Flow

**About:** [description](../__about/logic.md)

## Pipeline-step runner (`_run_pipeline_steps`)

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    START(["for each ENABLED step, in fixed<br/>BG → Crop → Aspect → Upscale order"]) --> FIRST{"is this the<br/>FIRST enabled step?"}
    FIRST -- yes --> ORIG["backup PRE-state as 'original'<br/>(always taken, deduped against<br/>this step's own named backup)"]
    FIRST -- no --> KEEP{"keep_all_steps ON<br/>AND not over_cap?"}
    KEEP -- yes --> NAMED["backup PRE-state under<br/>this step's own name"]
    KEEP -- no, over cap --> CAP["on_cap() fires once<br/>(loud, persistent banner)"]
    KEEP -- no, owner's choice --> SILENT["skip silently —<br/>not a disk emergency"]
    ORIG --> RUN["run the step's fn(path)"]
    NAMED --> RUN
    CAP --> RUN
    SILENT --> RUN
    RUN --> NOOP{"result == 'done'?"}
    NOOP -- no, a no-op --> DROP["drop this step's OWN named<br/>backup right back (never 'original')"]
    NOOP -- yes --> NEXT(["append 'label: status',<br/>advance to next enabled step"])
    DROP --> NEXT
```

Pseudocode:

```
took_original = False
FOR EACH (label, step_name, fn) IN steps:   # already fixed pipeline order
    backed_up_as = NONE
    IF temp is attached:
        IF NOT took_original:
            temp.backup(path, step="original")   # ALWAYS, cap or not
            took_original = True
        ELSE IF NOT keep_all_steps:
            pass                                  # owner's choice, silent
        ELSE IF NOT temp.over_cap():
            temp.backup(path, step=step_name)
            backed_up_as = step_name
        ELSE:
            on_cap()                               # loud, once
    status = fn(path)
    IF backed_up_as is set AND status != "done":
        temp.drop(step=backed_up_as)               # no-op — nothing to restore
    record "label: status"
RETURN joined "label: status, label: status, ..."
```

## View-transition state machine (`_next_view`)

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    IN(["current view, active_count,<br/>menu_requested"]) --> MENU{"menu_requested?"}
    MENU -- yes --> ZERO{"active_count == 0?"}
    ZERO -- yes --> TOMENU(["→ menu"])
    ZERO -- no --> REFUSE(["→ current (refused,<br/>however many jobs still run)"])
    MENU -- no --> ANY{"active_count > 0?"}
    ANY -- yes --> TORUN(["→ running<br/>(auto-enter, and STAYS running<br/>as jobs finish one by one)"])
    ANY -- no --> SAME(["→ current, unchanged<br/>(idle on menu/main)"])
```

Pseudocode:

```
IF menu_requested:
    RETURN "menu" IF active_count == 0 ELSE current   # refused otherwise
IF active_count > 0:
    RETURN "running"     # 0 -> >=1 auto-enters; stays "running" all
                          # the way down to 0 — only an EXPLICIT later
                          # Menu click (case above) ever leaves it
RETURN current
```
