# Themed Widget Toolkit

**Script:** [Themed Widget Toolkit (script)](../widgets.py) ·
**Flow:** [diagram](../__flow/widgets.md)

## Purpose
The dark-palette rounded CTk control factories every panel builds
from — buttons, entries, combos, the compact `[-][entry][+]`
`Spinner`, the on/off switch — plus the status/job-colour lookups,
the font-zoom registry, Start/Stop button styling, the folder-
grouping helpers shared by the dashboard tree and the Select window,
and the Advanced-override numeric field parsers. Split out of the
former single-file `gui.py` (root Rule #20 god-file refactor, step
2/8) — the toolkit's near-leaf module: its only dependency on another
`gui` submodule is `gui.icons.icon` (`rounded_button`'s optional
icon).

**The never-clip primitives** (owner 2026-08-03, slika 1 — "ni pod
kojim uslovima ne smeš da sečeš elemente da oni izlaze iz vidokruga"):
`FlowRow` lays its children out left-to-right with `place` and WRAPS
the overflow onto further rows instead of letting it fall off the
right edge, reporting its widest child as its own requested width so
the computed window minsize never drops below one whole element; it
re-runs on the next idle until a pass reproduces the previous one, so
a child whose real size is only known after realization can never
leave the last row half-hidden. CustomTkinter widgets must go through
`FlowRow.cell()`/`FlowRow.switch()` — CTk rescales `place`
coordinates, which would push a measured row past the edge it was
measured for; `add()` refuses them loudly. `fit_switch`/
`refit_switches` re-width a `CTkSwitch` to its own measured label
(CTk fixes the frame at `width` and turns propagation off, so
"Continue nudge" used to render as "Continue n"). `ExpanderAccordion`
enforces one-open-fine-tune-per-panel, and `ExpandableSwitch` takes an
optional `sub_host` so that fine-tune opens full-width below a whole
band instead of indented under its own switch.

Two smooth-field fixes live here alongside the factories:
`_untheme_inner_entry` unsubscribes the plain `tkinter.Entry` inside
every `CTkEntry`/`CTkComboBox` from ttkbootstrap's automatic re-style
publisher and drops its `highlightthickness=1` ring — without it,
ttkbootstrap re-themes that inner widget right after CTk builds it,
showing a lighter square ring inside the rounded field. `EdgeIconButton`
re-grids `CTkButton`'s internal 5x5 layout so an icon pins to the left
edge while the text centers in the remaining width, independent of
either.

Owns the two LIVE mutable globals every theme flip / zoom rewrites:
`ACTIVE_THEME` (the current theme name, rebound by `gui.theme.
_apply_theme_now`) and `FONT_BASE` (the current zoom root size,
rebound by this module's own `set_font_base`). Every OTHER module
that needs the CURRENT value reads it as `widgets.ACTIVE_THEME` /
`widgets.FONT_BASE` — a module-attribute access — never as a bare
imported name, which would freeze a stale copy at import time.

## Connections

### Uses
- [Config (subfolder)](../../painter/config/___config.md) — `THEMES`,
  `button_fill_pair`/`button_text_pair`/`job_color_pair`/
  `status_pair`/`theme_pair`
- [Icon Loading + Switch Art](icons.md) — `icon()` (the optional icon
  drawn on a `rounded_button`; `icon_px` sizes it — the FUNCTIONALITY
  marks pass `config.JOB_ICON_PX`, bigger than the default action
  glyph, because they carry a picture, owner 2026-08-04). Since 2026-08-04 the button
  hands `icon()` its OWN `text_color` pair as the tint, so a
  monochrome mark is always the same colour as the label beside it —
  white on a solid fill, the accent on an outline kind, in either
  theme. Without it QtSvg painted every `currentColor` mark BLACK,
  which disappeared on the dark outline buttons. Coloured marks
  (`jobs/`, `files/`) ignore the tint.

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports the full API
  (`gui.rounded_button`, `gui.status`, `gui.job_color`, `gui.
  set_font_base`, ...)
- [The Theme Engine](theme.md) — `status`, `tk_font`, `TREE_ROW_
  FACTOR` (for its own `setup_style`)
- [DayNightSwitch](switch.md) — the live `ACTIVE_THEME` global via
  module-attribute access

## Classes

### EdgeIconButton
A `CTkButton` whose icon pins to the left edge while the text centers
in the remaining width — for stacked equal-width buttons (Add…/
Remove/Clear), where the default centered icon+text block makes the
icons jitter with the text length.

### Spinner
A compact `[-][entry][+]` numeric field as ONE rounded unit (root
Rule #5 — the pace/action-delay fields are its instances): direct
typing stays allowed (validated on Start), the +/- buttons step the
value by a configurable amount, never below 0.

### ExpandableSwitch
A switch whose FINE-TUNE lives in an indented sub-panel right below
it (owner's UI-SKETCH, 2026-07-29 — the primitive that replaced the
per-agent Settings gear). The mechanic, in the owner's own words:

```
switch OFF          -> the sub-panel does not exist (no caret)
switch turned ON    -> auto-expands ONCE, indented below (caret ▾)
caret ▸/▾ clicked   -> folds / unfolds by hand, switch untouched
switch turned OFF   -> hides the sub-panel entirely
```

`build_sub(frame)` builds the content — LAZILY on the first expand,
or at construction with `eager=True` for content whose STATE has to
outlive its visibility (a `FilterEditor` condition stack, an
`AspectRatioCanvas` two-way binding). `build_sub=None` renders a
plain switch. Every expand/collapse calls `on_layout_change` AFTER
the pack/forget, so an outer `ScrollFrame` can re-fit content whose
height just changed several parents below it.

With a `sub_host` (the setup panels' full-width band host) a COLLAPSE
also resets `sub_host`'s requested height to 1 — Tk's `pack` leaves a
container's requested size at its LAST slave's when that slave is
removed, so an emptied host kept the fine-tune's height as DEAD SPACE
below the band (owner 2026-08-04, slika 1+2). Propagation takes the
height back over the moment any fine-tune re-opens into the host.

An already-ON switch starts COLLAPSED — the auto-expand is a live
click reaction. Since Tk write-traces cannot tell a settings-restore
`.set()` from a click, the restoring host wraps its round-trip in
`quiet_restore` (below).

### ExpandableSection
The switch-LESS variant — a clickable label + ▸/▾ caret over the same
indented sub-panel — for fine-tune that belongs to no single switch
(the UI-SKETCH's **Pacing** row: pause range, action delay,
on-degrade). Starts collapsed, content built eagerly.

### quiet_restore (context manager)
Restores settings into any number of `ExpandableSwitch` variables
without a single auto-expand: a restored-ON switch stays folded (so a
panel always opens compact — the live-window defect it was written
for had every ON switch unfolding at startup), while a restored-OFF
switch still hides an open sub-panel. Released on the way out even if
the restore raises.

### wrap_bar_label (function)
Wires a top-bar's hint/subtitle `ttk.Label` to wrap into whatever width
the bar has left over, LIVE (THE SPACE & LEGIBILITY LAW, rules/GUI.md —
ladder step 2, reflow before raising a minimum). Added 2026-08-06 (the
layout-audit rollout, MIGRATE-LAYOUT.md): `DocWindow`, `BeforeAfterWindow`,
`StepRestoreWindow` and `SelectWindow` each pair a hint/subtitle Label with
action buttons on one packed row; several of their PRODUCTION hint strings
(not test-invented — e.g. `BeforeAfterWindow`'s MULTI-mode subtitle,
`SelectWindow`'s legend line) are long enough to force the row past the
window's own declared minimum width. `wrap_bar_label(bar, label, *reserved)`
binds the bar's `<Configure>` to recompute the label's `wraplength` from
`event.width` minus the reserved buttons' own live `winfo_reqwidth()` — so
the wrap always tracks the REAL current window width, never a guessed
constant. Shared by all four callers (Rule #5) rather than reimplemented
per window.

### Field parsers
One per numeric field SHAPE, all sharing the same "raise `ValueError`
naming the field that failed" contract so a panel's Start reports
which box is wrong: `_parse_fraction` (0 < x ≤ 1 — the safety-guard
ceilings), `_parse_nonneg_int` (≥ 0), `_parse_int_range` (that plus an
inclusive bound — the 0-255 alpha fields), and `_parse_percent`
(0-100 %, FRACTIONS ALLOWED — the BG panel's custom-colour tolerance,
whose worked example lands on 6.67, so whole-percent rounding would
quietly move the colour key by a level).

## Design Decisions
- **Button semantic kinds draw from theme pairs, never a hardcoded
  colour.** `secondary`/`success`/`danger`/`info` (solid), their
  `-outline` variants, `link` (borderless accent) and `expander`
  (flat ▶/▼ section header) each resolve through `THEMES`'s
  `BUTTON_FILL`/`BUTTON_TEXT` pairs (owner 2026-07-19 — the DAY shade
  differs from NIGHT per kind, and `secondary` is a light sand fill
  with dark text on day rather than the dark warm-grey that read
  brown on the cream window). Every factory pins `bg_color` to the
  active window background so a rounded control's corners never show
  a foreign CTk gray on a ttk parent.
- See [GUI (folder)](../___gui.md)'s own "Design Decisions" section
  for the full reasoning behind the `ACTIVE_THEME`/`FONT_BASE`
  module-attribute pattern — it applies identically here, since this
  is the module that OWNS both globals.
