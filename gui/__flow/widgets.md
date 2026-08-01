# Themed Widget Toolkit — Flow

**About:** [description](../__about/widgets.md)

## Font-zoom rescale (`set_font_base`)

```mermaid
flowchart TB
    A([set_font_base: size]) --> B[clamp size to FONT_MIN..FONT_MAX]
    B --> C{size == current FONT_BASE?}
    C -- yes --> Z1[["return False — no-op"]]
    C -- no --> D[FONT_BASE = size]
    D --> E[for each role in _TK_FONTS: f.configure size = font_size role]
    E --> F[for each role in _CTK_FONTS: f.configure size = font_size role]
    F --> G[Treeview style rowheight = FONT_BASE * TREE_ROW_FACTOR]
    G --> Z2[["return True — every live font/style updated in place"]]
```

Every role's font is a single SHARED `tk.font.Font` / `ctk.CTkFont`
object reused by every widget/style/tag that asked for that role — a
`.configure(size=...)` on the shared object propagates to all of them
automatically, so the loop above is the ENTIRE rescale; no widget walk
is needed.

## ExpandableSwitch — click vs. restore

The tricky part: a Tk variable write-trace cannot tell "the owner
clicked the switch" from "a settings restore just called `.set()`" —
both fire the same trace callback. The `quiet` flag (set only through
`quiet_restore`) is what tells them apart.

```mermaid
flowchart TB
    A([variable write fires _on_switch]) --> B{variable is True?}
    B -- yes, turning ON --> C{self.quiet?}
    C -- yes: a restore --> D[just redraw the caret — stay folded]
    C -- no: a live click --> E[toggle open_=True — auto-expand once]
    B -- no, turning OFF --> F{sub-panel currently open?}
    F -- yes --> G[toggle open_=False — always hides, restore or not]
    F -- no --> D
```

Pseudocode for `toggle(open_)`, the shared pack/unpack the click and
the restore-driven OFF path both fund into:

    FUNCTION toggle(open_wanted):
        IF build_sub is None: RETURN                 # plain switch, no sub
        IF open_wanted AND NOT variable.get(): RETURN # sub only exists while ON
        IF open_wanted AND NOT built:
            build_sub(sub_frame)                       # lazy first build
            built = True
        IF open_wanted == currently_open:
            render_caret(); RETURN                     # nothing changed
        currently_open = open_wanted
        IF open_wanted: sub_frame.pack(indented)
        ELSE:           sub_frame.pack_forget()
        render_caret()
        on_layout_change()      # tells an outer ScrollFrame to re-fit

`quiet_restore(*switches)` is a context manager: set `.quiet = True` on
every switch passed in, `yield`, then always reset it to `False` in a
`finally` — so a restore that raises partway through still leaves
every switch back in live-click mode.
