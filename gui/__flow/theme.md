# The Theme Engine — Flow

**About:** [description](../__about/theme.md)

## Algorithm — `apply_theme(name, animate)`

```mermaid
%%{init: {'flowchart': {'subGraphTitleMargin': {'top': 0, 'bottom': 35}}}}%%
flowchart TB
    A(["apply_theme(name, animate)"]) --> B{"animate AND<br/>a root window exists?"}
    B -- no (startup) --> C["_apply_theme_now(name) — instant"]
    B -- yes (the switch click) --> D["smooth_transition(root,<br/>mutate=_apply_theme_now,<br/>icon=big sun/moon)"]
    D --> E["_snapshot_overlay: grab window,<br/>composite icon, force-paint FIRST"]
    E --> F["mutate() runs HIDDEN behind the cover"]
    F --> G["root.update_idletasks() — settle"]
    G --> H["_fade_out_overlay: alpha 1.0 -> 0.0,<br/>ease-out, then destroy"]
```

## Pseudocode — `_apply_theme_now` (the coherent flip itself)

```
FUNCTION apply_theme_now(name):
    widgets.ACTIVE_THEME = name            # the live global, module-attr write
    ttkbootstrap.Style().theme_use(THEMES[name].ttkname)
    setup_style()                          # re-derive the few named ttk styles
    customtkinter.set_appearance_mode(THEMES[name].mode)   # every CTk tuple flips
    recolor_tk_registry()                  # re-walk THEMED_TK, prune dead widgets
    FOR EACH open Toplevel in THEME_TOPLEVELS:
        top.apply_theme()                  # per-widget foregrounds ttk can't reach
```

No window is ever torn down — worker threads, dashboard counters and
quota countdowns all survive untouched.

## Algorithm — the plain-tk skin registry

```mermaid
flowchart LR
    A["skin_text(widget) / skin_listbox / skin_canvas / skin_tree / skin_toplevel"] --> B["colour the widget from the ACTIVE palette NOW"]
    B --> C["append (widget, role) to THEMED_TK"]
    D["a theme flip"] --> E["recolor_tk_registry(): walk THEMED_TK"]
    E --> F{"widget still alive?"}
    F -- TclError --> G["drop it — pruned"]
    F -- alive --> H["re-apply that role's skin from the new palette"]
```
