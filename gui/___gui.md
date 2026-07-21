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

Step 2/8 moved the **toolkit** — the leaf widget/theme/icon helpers
with no dependency on the app's own panels or `PainterGui` itself.
Step 3/8 moved the **reusable widgets + pure logic + dashboard
helpers**: `FilterEditor`, `AspectRatioCanvas`, the Tk-free
module-level functions (`logic.py`), and the shared dashboard support
helpers (`dash_helpers.py`). Step 4/8 moved the **three
CONTROL-PANEL classes**: `AgentPanel` (`agent_panel.py`), the whole
`ToolSettingsPanel` family — base + `BgSettingsPanel`/
`CropSettingsPanel`/`UpscaleSettingsPanel`/`AspectSettingsPanel`/
`ImageCheckerSettingsPanel` (`tool_panels.py`) — and `ApiImageGenPanel`
+ `ApiImageAdapter` (`api_panel.py`). Step 5/8 moved the **VIEWER +
DIALOG Toplevels**: `SelectWindow` (`select_window.py`), `DocWindow`/
`BeforeAfterWindow`/`_filmstrip_stages`/`StepRestoreWindow`
(`viewers.py`), and `_ModalToolDialog`/`_AiDialog`/`AiKeyWizard`/
`AiSheetDialog` (`dialogs.py`) — including `AI_POLL_MS`, which follows
its real owner `_AiDialog` out of `gui/__init__.py` into
`gui/dialogs.py` (see that module's own Design Decisions). This step
(6/8) moved the **MENU + DASHBOARD-PANEL classes**: `MainMenu`/
`IconBar` (`menu.py`), `JobPanel`/`DashPanel` (`dash_panels.py`), and
`ToolPanel`/`AiCheckPanel`/`DashGrid` (`tool_dash.py`). This step
(7/8 — the critical one) split the god-class itself: `PainterGui`
(~3,350 lines, 94 methods) is now composed from FIVE responsibility
mixins, one file each — `BuildMixin` (`app_build.py`, the constructor +
widget construction), `ViewMixin` (`app_views.py`, the Main Menu /
running-view state machine), `SiteJobsMixin` (`app_jobs.py`, the site +
API-image run loop, dashboard dispatch, Checker AI, Fixer AI),
`ToolJobsMixin` (`app_tools.py`, the four standalone tools + the AI
image checker) and `SettingsMixin` (`app_settings.py`, queue/sheet
management, prerequisite actions, settings persistence) — combined by
inheritance in `app.py`'s `class PainterGui(BuildMixin, ViewMixin,
SiteJobsMixin, ToolJobsMixin, SettingsMixin):`, which also carries
`main()`. `__init__.py` is now a PURE re-export shell: `from .app
import PainterGui, main` plus every existing `from .submodule import
(...)` block, unchanged — no class or def body of its own.
[gui.md](../gui.md) (the pre-existing FEATURE-by-feature script doc,
one level up) now points readers at these five modules for where the
described behavior actually lives; step 8/8 is the final cross-project
verification pass (see `REFACTOR-GODFILES.md`, the owner's binding
plan, untracked).

## Files

### `app.py` — App (composition)
`class PainterGui(BuildMixin, ViewMixin, SiteJobsMixin, ToolJobsMixin,
SettingsMixin):` — no method bodies of its own, just the MRO glue —
plus `main()` and the `if __name__ == "__main__":` guard. See
[App (composition)](app.md).

### `app_build.py` — Build Mixin
`BuildMixin` — `PainterGui`'s constructor (the ONLY mixin with
`__init__`) and every `_build_*` widget-construction helper, the
global font-zoom/wheel-routing bindings, `_relayout_agents`, and the
maximize/restore cover + drag-resize event-buffering watcher. See
[Build Mixin](app_build.md).

### `app_views.py` — View Mixin
`ViewMixin` — the Main Menu / "main" / "running" three-way view switch,
the Main Menu tile router (shared with the running view's `IconBar`),
the running-view layout reconciler, the "which jobs are active"
queries, and the Controls collapse toggle. See [View Mixin](app_views.md).

### `app_jobs.py` — Site Jobs Mixin
`SiteJobsMixin` — the two browser-driven SITE jobs plus the paid-API
image job's shared run loop, the worker-queue pump/dispatch, the
per-job Pause toggle and dashboard-panel close, the quota auto-restart
timers, the post-save pipeline composer, the parallel Checker AI and
the Fixer AI (both its auto-dispatch half and its manual-button
worker builders). See [Site Jobs Mixin](app_jobs.md).

### `app_tools.py` — Tool Jobs Mixin
`ToolJobsMixin` — the four standalone tools' (BG removal / Crop /
Upscale / Aspect ratio) Start/worker/Stop, the AI image checker's own
job, and its two report-viewer actions (Send flagged to generator /
Clear flags). See [Tool Jobs Mixin](app_tools.md).

### `app_settings.py` — Settings Mixin
`SettingsMixin` — the Collections queue, the sheet parsing/planning
helpers shared by the site jobs, the dashboard row "Show" viewers, the
top-strip prerequisite button handlers, the AI features' key gate, and
the whole settings round-trip (collect/apply/migrate/save). See
[Settings Mixin](app_settings.md).

### `agent_panel.py` — Agent Panel
`AgentPanel` — one site's (ChatGPT/Gemini) OWN control panel:
background/style dropdowns, the three composable post-save switches,
Report/Safer retry/Continue nudge/Checker AI/Fixer AI, the Force
Aspect Ratio block, the collapsible pause/action-delay/upscale-gate
fine-tune, and its own Start/Pause/Stop. See
[Agent Panel](agent_panel.md).

### `api_panel.py` — API Panel
`ApiImageGenPanel` (the paid Gemini image-API job's settings panel —
mirrors `AgentPanel` since its input is the shared queued Collections
list, not a folder of images) and `ApiImageAdapter` (a `SiteDriver`-
shaped stand-in so that job reuses `_drive_site`/`run_sheet`
unchanged). See [API Panel](api_panel.md).

### `tool_panels.py` — Standalone-Tool Settings Panels
`ToolSettingsPanel` (the shared base: input picker, embedded
`FilterEditor`, an optional Advanced collapsible, Start/Pause/Stop)
plus its five concrete subclasses — `BgSettingsPanel`/
`CropSettingsPanel`/`UpscaleSettingsPanel`/`AspectSettingsPanel`/
`ImageCheckerSettingsPanel`. Also owns the two-column-dense layout
constants every control-panel family (this one, `AgentPanel`,
`ApiImageGenPanel`) shares. See
[Standalone-Tool Settings Panels](tool_panels.md).

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

### `filter_editor.py` — FilterEditor
The reusable stacked-filter widget (GUI rework Phase 4): removable
condition rows (kind/polarity combos + numeric fields) over
`painter.filters`, an "+ Add condition" button, and a save/load/delete
PRESET row. Depends on `gui.widgets` (`rounded_button`/`rounded_entry`/
`rounded_combo`, `INPUT_HEIGHT`).

### `aspect_canvas.py` — AspectRatioCanvas
A live, draggable preview of the target output ratio (GUI rework
Phase 5): a rectangle in a fixed square arena whose 4 edges reshape it
(LEFT/RIGHT change WIDTH, TOP/BOTTOM change HEIGHT), with a live
decimal + reduced-integer label underneath. Depends on `gui.theme`
(`skin_canvas`) and `gui.widgets` (`job_color`, `tk_font`, the live
`ACTIVE_THEME`).

### `logic.py` — Pure Logic Helpers
The Tk-free module-level functions: the shared-filter engine glue
(`_filter_files`, `_parse_condition_dicts`, the legacy
aspect-filter/upscale-gate migrations), the per-image post-save
pipeline runner (`_run_pipeline_steps`), the dashboard's per-scope stat
formatter (`_scope_stats`), the fixer auto-dispatch decision
(`_fixer_decision`), the manual-fix result-to-UI mapping
(`_fix_result_ui`), and small pure view-layout helpers
(`_visible_agent_columns`, `_menu_tile_columns`, `_next_view`). No Tk
dependency at all — every function is directly unit-testable.

### `dash_helpers.py` — Dashboard Support Helpers
Small helpers shared by two or more dashboard surfaces: the badge-dot
`PhotoImage` cache (`badge_dots`), the tool-panel timing summary line
(`fmt_time_summary`), the AI-check report/tag helpers shared by
`AiCheckPanel` and `DashPanel` (`ai_check_doc_md`/`ai_check_image_file`/
`ai_check_tag`), the shared `Treeview` builder (`build_job_tree`), and
the before/after transparency-checkerboard helpers (`_checkerboard`/
`_has_alpha`/`_scaled_photo`). Depends on `gui.theme`
(`TOOL_CHANGED_TAG`/`TOOL_SKIP_TAG`, `skin_tree`).

### `dash_panels.py` — Dashboard Job Panel Base + Site Panel
`JobPanel` (the shared per-JOB dashboard panel base — header,
close/pause, the folder>image tree-node plumbing) and `DashPanel`
(one generation site's live view — task/theme progress, the two-scope
stats table, the collections history tree, the per-step restore
viewer and the parallel Checker AI's per-row report). See
[Dashboard Job Panel Base + Site Panel](dash_panels.md).

### `tool_dash.py` — Tool + AI-Checker Dashboard Panels + Grid
`ToolPanel` (one standalone tool's live view — progress, metric,
before/after viewer + restore), `AiCheckPanel` (the AI checker's own
dashboard panel — flagged/OK/error counts, the defect viewer, resend/
clear actions) and `DashGrid` (the responsive up-to-6-cell job-panel
grid). Both panels subclass `JobPanel` from `dash_panels.py`. See
[Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md).

### `menu.py` — Main Menu + Icon Bar
`MainMenu` (the startup landing screen's responsive tile grid) and
`IconBar` (the compact top strip shown while a job is running, one
button per tile, lit while any of its job kinds is live). See
[Main Menu + Icon Bar](menu.md).

### `select_window.py` — Select-Images Window
`SelectWindow` — the per-site tick-list Toplevel over the queued
Collections (3-level tree: collection -> folder -> image), with the
chunked Expand-all and coalesced recount that keep a big queue
responsive. See [Select-Images Window](select_window.md).

### `viewers.py` — Read-Only Viewers
`DocWindow` (the Markdown/prompt/image viewer, plus its optional
Fixer-AI manual buttons), `BeforeAfterWindow` (a tool job's
before/after viewer), `_filmstrip_stages` (the pure per-image
pipeline-stage list) and `StepRestoreWindow` (the per-step restore
filmstrip built from it). Also owns the shared `DOC_*`/
`BEFORE_AFTER_*`/`STEP_RESTORE_*` sizing constants. See
[Read-Only Viewers](viewers.md).

### `dialogs.py` — Modal Dialogs
`_ModalToolDialog` (shared centre-on-parent placement), `_AiDialog`
(the worker-queue poll loop both AI dialogs share, and the owner of
`AI_POLL_MS`), `AiKeyWizard` (the guided Gemini-API-key onboarding)
and `AiSheetDialog` ('New collection (AI)…'). See
[Modal Dialogs](dialogs.md).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config` (every
  tunable), `aspect`/`filters`/`jobtemp`, `settings`, `sheet_parser`

### Used by
- [Main (Entry Point)](../main.md) — `from gui import PainterGui`

## Design Decisions

**Why a toolkit-first extraction order.** The five step-2 modules are
true leaves (icons) or near-leaves (widgets -> icons; theme -> widgets
+ icons; scroll -> theme; switch -> icons + theme + widgets) — nothing
in `PainterGui` or the panels needs to change to make room for them,
so that step carried zero risk to the app's actual behavior. Step 3
(this step) peeled the next layer: the two reusable widgets
(`FilterEditor`, `AspectRatioCanvas` — each only a near-leaf, depending
on the step-2 toolkit) plus the PURE module-level functions
(`logic.py`, no Tk at all) and the shared dashboard support helpers
(`dash_helpers.py`, depending on `gui.theme`) — again nothing in
`PainterGui` or the remaining panel classes needed to change, only
their imports. Later steps peel the control panels, the dashboards,
the menu/nav layer and finally `PainterGui` itself (split into
responsibility mixins — see `REFACTOR-GODFILES.md`, the owner's
binding plan, untracked).

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

**Step 4/8 — shared layout constants live in `tool_panels.py`, not
`__init__.py`.** `AgentPanel`, the `ToolSettingsPanel` family and
`ApiImageGenPanel` all read the SAME two-column-dense layout constants
(`DENSE_COL_GAP_PX`/`DENSE_COL_WRAP_PX`/`ASPECT_DIALOG_ENTRY_W`, plus
the Settings-gear caret glyphs `AgentPanel`/`ToolSettingsPanel` share).
Rather than leave them as bare `gui/__init__.py` module constants
(which `gui.agent_panel`/`gui.api_panel` could only reach through a
circular `from . import X`, since `__init__.py` imports THEM), they
now live in `gui/tool_panels.py` — a real leaf module both sibling
panel modules import from directly (`from .tool_panels import ...`),
with zero circular-import risk since `tool_panels.py` depends on
neither of them.

**`AI_POLL_MS` followed `_AiDialog` into `gui/dialogs.py`.** Step 4/8
left it behind in `gui/__init__.py` specifically because `_AiDialog`
(its only OTHER reader at the time) hadn't moved yet — relocating it
then would have just moved the same circular-import problem onto
`ApiImageGenPanel` instead. Now that `_AiDialog` itself has moved (this
step), the constant follows its real owner. Both `gui/api_panel.py`'s
`_arm_probe_poll` AND `gui/viewers.py`'s `DocWindow._arm_fix_poll` (an
unrelated Fixer-AI poll that happens to share the same cadence
constant) keep reaching it through a deferred `import gui; gui.
AI_POLL_MS` inside the method body (never at module level) — the
identical late-binding idiom `gui/theme.py`'s `_pkg()` established —
rather than a real-path `from .dialogs import AI_POLL_MS`. For
`gui.viewers` specifically a real-path import WOULD be circular:
`gui.dialogs` imports `DocWindow` FROM `gui.viewers` (for
`AiSheetDialog._finish`'s "not loaded" viewer), so `gui.viewers`
cannot import back from `gui.dialogs` at module level. By the time
either poll method actually runs (well after import time), the `gui`
package has always finished initializing.

**Step 5 — the viewer/dialog Toplevels' cross-import shape.**
`gui/select_window.py` imports `DOC_HEIGHT_FRAC`/`DOC_MAX_FRAC`
directly from `gui/viewers.py` (the module that names and owns the
`DOC_*` sizing family) — safe because `gui.viewers` has no dependency
back on `gui.select_window`. `gui/dialogs.py` imports `DocWindow`
directly from `gui/viewers.py` for the same reason (one-directional).
The only cycle risk in this step was `AI_POLL_MS` (see above), solved
with the same late-binding idiom rather than restructuring either
module.

**Step 6/8 — the dashboard panels' viewer calls stayed monkeypatchable
through `gui`, exactly like `smooth_transition`'s collaborators
above.** `DashPanel._show_check`/`_show_steps`
(`gui/dash_panels.py`) and `AiCheckPanel._on_activate`
(`gui/tool_dash.py`) all open a viewer Toplevel (`DocWindow`/
`StepRestoreWindow`) at the moment the owner double-clicks or clicks
a button — several tests patch these classes via
`monkeypatch.setattr(gui, "DocWindow", fake)` /
`monkeypatch.setattr(gui, "StepRestoreWindow", fake)`
(`test_gui_checker.py`, `test_gui_fixer.py`, `test_gui_pipeline.py`).
A real-path `from .viewers import DocWindow` at the top of either new
module would bind the REAL class at import time; the test's patch,
which only ever reaches the `gui` package's own attribute, would then
never be seen. Both methods instead do a deferred `import gui;
gui.DocWindow(...)` inside the method body — the same late-binding
idiom this file already documents for `smooth_transition`'s
collaborators and `AI_POLL_MS`'s readers. `ToolPanel`'s own
before/after viewer (`BeforeAfterWindow`) has no such test coverage
(confirmed by grep across `tests/*.py` before this split) and stays a
plain real-path import from `gui.viewers` — late-binding it too would
be indirection nothing depends on.

**Step 7/8 — every method assigned to exactly one mixin by
responsibility, never re-derived per file.** The 94 methods on the old
`PainterGui` were grepped once (`^    def `) and each assigned to
`BuildMixin`/`ViewMixin`/`SiteJobsMixin`/`ToolJobsMixin`/
`SettingsMixin` by what it does, not by where it happened to sit in
the 3,350-line file — e.g. `_close_panel`/`_tool_panel_key` went to
`SiteJobsMixin` (their heaviest readers, `_dispatch`/
`_toggle_pause_job`, both live there) even though a dashboard-panel
"close" sounds view-ish; `_on_root_configure`/`_resize_settled`/
`_clamp_geometry` stayed in `BuildMixin` (they are window/geometry
plumbing armed once at the tail of `__init__`, not a view switch) even
though they run throughout the app's life. Each mixin's own `.md`
records exactly which ambiguous methods it claimed and why, so the
assignment is auditable per file, not just asserted here.

**Step 7/8 — one MORE late-binding case, found only by running the
full test suite after the mechanical move.** The 4 known
`monkeypatch.setattr(gui, ...)` targets going in
(`DocWindow`, `StepRestoreWindow`, `_snapshot_overlay`,
`_fade_out_overlay`) were joined by a 5th discovered only when
`test_gui_pipeline.py::test_compose_post_save_all_four_on_orders_
bg_crop_aspect_upscale` failed post-split:
`monkeypatch.setattr(gui, "_gate_and_upscale", fake)`, reached from
`SiteJobsMixin._compose_post_save`'s `post_save` closure. Multi-line
`monkeypatch.setattr(\n    gui, "name", ...\n)` calls do not show up in
a single-line grep for `setattr(gui, "` — a multiline-aware search
(or, as here, simply running the tests) is required to find every
such target before trusting a split is complete. Fixed the same way as
every other case: a deferred `import gui` inside the closure, `gui.
_gate_and_upscale(...)` instead of a top-level `from .logic import
_gate_and_upscale`.

**Step 7/8 — `PainterGui` itself is now just MRO glue.** `app.py`
holds `class PainterGui(BuildMixin, ViewMixin, SiteJobsMixin,
ToolJobsMixin, SettingsMixin):` with no method bodies of its own, plus
`main()`. `BuildMixin` is first in the MRO (and the only base with
`__init__`), so `PainterGui(root)` still runs exactly one constructor;
every other mixin's methods reach the SAME instance's attributes via
`self.`, unchanged from when they were one class's methods. Verified:
`python -c "import gui; print(gui.PainterGui.__mro__)"` shows all five
mixins in declaration order, and the full suite (617 passed, 1
skipped) plus the GUI-heavy files individually (260 passed) pass
unmodified.
