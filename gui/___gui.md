# gui/

The owner's front door — the tkinter window `main.py` opens with no
arguments. Built for unattended batches: queue the collections, press
a site's Start, go ride a bike.

Being split out of one 11,764-line `gui.py` file into a package (root
Rule #20 god-file split, step 2/8 — the config split, step 1/8, is
[Config (subfolder)](../painter/config/___config.md)). `__init__.py`
re-exports the full public (and much of the private) API of every
submodule extracted so far — one explicit `from .widgets import
(...)` block per submodule — so every existing `gui.X` / `from gui
import X` call site kept working UNCHANGED across the split.

This step moved only the **toolkit** — the leaf widget/theme/icon
helpers with no dependency on the app's own panels or `PainterGui`
itself. The god-class `PainterGui` (~3,350 lines), the dashboards,
the tool/agent panels, `SelectWindow`, the AI dialogs and the viewers
all still live in `__init__.py`, unmoved — [gui.md](../gui.md) (the
pre-existing script doc, one level up, beside this folder) still
documents that remaining content; it migrates into further submodules
in later steps of the same refactor.

## Files

### `widgets.py` — Themed Widget Toolkit
Status/job-colour lookups (`status`, `job_color`), the font-zoom
registry (`font_size`/`tk_font`/`ctk_font`/`set_font_base`,
`FONT_ROLES`), the dark-palette rounded CTk control factories
(`rounded_button`/`rounded_entry`/`rounded_combo`/`rounded_switch`,
`Spinner`, `EdgeIconButton`), Start/Stop button styling
(`style_action_button`/`_style_icon_bar_button`), the folder-grouping
helpers shared by the dashboard tree and the Select window
(`folder_of`/`rels_in_folder`), and the Advanced-override numeric
field parsers (`_parse_fraction`/`_parse_nonneg_int`/
`_parse_int_range`). The toolkit's one non-leaf dependency:
`rounded_button` draws its optional icon via `gui.icons.icon`.

Owns the two LIVE mutable globals every theme flip / zoom rewrites —
`ACTIVE_THEME` and `FONT_BASE`. Every OTHER module that needs the
CURRENT value reads it off `widgets.ACTIVE_THEME` / `widgets.
FONT_BASE` (a module-attribute access, e.g. `gui/theme.py`'s
`_apply_theme_now` and `gui/switch.py`'s `DayNightSwitch.__init__`) —
never `from .widgets import ACTIVE_THEME`, which would freeze a stale
copy at import time and silently stop tracking flips/zooms.

### `icons.py` — Icon Loading + Switch Art
SVG-first icon loading (`icon`, `_svg_to_pil`, `ICON_DIR`) via Qt's
`QSvgRenderer` (PySide6), PNG as the fallback for icons with no svg
and for svgs QtSvg's Tiny profile can't render; and the Day/Night
switch's hand-rendered art — anti-aliased radial-gradient sun/moon
knobs (`_render_sun_knob`/`_render_moon_knob`, craters + terminator
shading + surface mottling) and the track-pill rasterizer
(`_render_switch_track`), all built on the same SVG->PIL path. The
toolkit's LEAF module — no dependency on any other `gui` submodule.

### `theme.py` — The Theme Engine
The coordinated ttk/CTk/plain-tk Day/Night flip (`apply_theme`/
`_apply_theme_now`), the plain-tk skin registry (`skin_text`/
`skin_listbox`/`skin_canvas`/`skin_tree`/`skin_toplevel` +
`recolor_tk_registry`, for the Text/Listbox/Canvas/Toplevel colours
CTk's automatic tuple resolution can't reach), and the shared
snapshot-cover transition (`smooth_transition`) that hides every big
repaint — the theme flip itself, the Controls collapse, each agent's
Settings gear, a window maximize/restore. Depends on `gui.widgets`
(`status`, `tk_font`/`TREE_ROW_FACTOR` for `setup_style`, and the live
`ACTIVE_THEME`/`FONT_BASE` globals) and `gui.icons` (the big sun/moon
cover icon rendered behind the flip).

### `scroll.py` — ScrollFrame
A vertically (optionally also horizontally) scrollable frame:
self-healing fill-height (a periodic poll catches a content-height
change no caller remembered to `refresh()`), a resize-debounced
re-fit (a window drag applies its width/height/scrollregion pass ONCE,
on settle, not per frame), and mouse-wheel binding scoped to hover.
Depends on `gui.theme` (`skin_canvas`).

### `switch.py` — DayNightSwitch
The mini Day/Night toggle, top-right: an anti-aliased PIL-composited
image pill (dark starfield + moon / sky + sun) ported from the
owner's website switch. A click flips the theme synchronously (via
`gui.theme.apply_theme`, riding the shared snapshot-cover transition)
while the knob itself slides as a smoothstep-eased flourish. Depends
on `gui.widgets` (the live `ACTIVE_THEME`), `gui.icons` (the knob/track
renderers) and `gui.theme` (`apply_theme`, `skin_canvas`).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config` (every
  tunable), `aspect`/`filters`/`jobtemp`, `settings`, `sheet_parser`

### Used by
- [Main (Entry Point)](../main.md) — `from gui import PainterGui`

## Design Decisions

**Why a toolkit-first extraction order.** The five modules above are
true leaves (icons) or near-leaves (widgets -> icons; theme -> widgets
+ icons; scroll -> theme; switch -> icons + theme + widgets) — nothing
in `PainterGui` or the panels needs to change to make room for them,
so this step carries zero risk to the app's actual behavior. Later
steps peel the reusable widgets (`FilterEditor`, `AspectRatioCanvas`),
the control panels, the dashboards, the menu/nav layer and finally
`PainterGui` itself (split into responsibility mixins — see
`REFACTOR-GODFILES.md`, the owner's binding plan, untracked).

**The two mutable-global exceptions to the re-export pattern.**
`__init__.py`'s re-export blocks make every moved name reachable as
`gui.X` again — EXCEPT `ACTIVE_THEME` and `FONT_BASE`, which are
deliberately NOT re-exported as bare names. Both are rebound (not just
mutated) at runtime — a theme flip reassigns `ACTIVE_THEME`, a zoom
reassigns `FONT_BASE` — and a plain `from .widgets import ACTIVE_THEME`
elsewhere would capture a snapshot at import time that never again
sees a later flip/zoom (a real, silent correctness bug, not a style
nitpick). Every place that needs the LIVE value — inside `gui/theme.py`,
`gui/switch.py`, and the remaining `__init__.py` code — reads it off
`widgets.ACTIVE_THEME` / `widgets.FONT_BASE` (a module-attribute
access) instead.

**`smooth_transition`'s collaborators stay monkeypatchable through
`gui`.** `gui/theme.py`'s `smooth_transition` calls `_snapshot_overlay`
and `_fade_out_overlay` through a small `_pkg()` indirection
(`import gui; return gui`) rather than its own module globals — so
`monkeypatch.setattr(gui, "_snapshot_overlay", fake)` (existing tests,
written against the one-file `gui.py`) stays effective post-split.
Without it, a test's patch on the `gui` package's re-exported COPY of
the name would never reach `theme.py`'s own global lookup, silently
un-patching the collaborator. Every real (non-test) caller sees
identical behavior either way, since `gui.X` and `gui.theme.X` are the
same function object unless a test overrides one of them.
