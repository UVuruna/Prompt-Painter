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
`ToolPanel`/`AiCheckPanel`/`DashGrid` (`tool_dash.py`). Step 7/8 split
the god-class itself: `PainterGui` (~3,350 lines, 94 methods) was
composed from FIVE responsibility mixins, one file each — `BuildMixin`
(`app_build.py`, the constructor + widget construction), `ViewMixin`
(`app_views.py`, the Main Menu / running-view state machine),
`SiteJobsMixin` (`app_jobs.py`, the site + API-image run loop,
dashboard dispatch, Checker AI, Fixer AI), `ToolJobsMixin`
(`app_tools.py`, the four standalone tools + the AI image checker) and
`SettingsMixin` (`app_settings.py`, queue/sheet management,
prerequisite actions, settings persistence) — combined by inheritance
in `app.py`'s `PainterGui`, which also carries `main()`. `__init__.py`
became a PURE re-export shell: `from .app import PainterGui, main`
plus every existing `from .submodule import (...)` block, unchanged —
no class or def body of its own.

**Step 8/8 (finalize) — one more mixin split, plus cross-project
verification.** `app_jobs.py` had grown to 1334 lines post-step-7/8 —
past the ~1000-line Rule #20 budget on its own. Its parallel Checker AI
and Fixer AI methods (`_maybe_spawn_checker`/`_run_checker_one`/
`_maybe_spawn_fixer`/`_run_fixer_api`/`_queue_website_fix`/
`_backup_before_fix`/`_run_image_fix`/`_run_website_fix`/
`_build_fix_workers`) moved byte-for-byte into a SIXTH mixin,
`CheckerFixerMixin` (`app_checker_fixer.py`) — `SiteJobsMixin` keeps
the run loop, the queue pump/dispatch and the post-save composer.
`PainterGui` is now `class PainterGui(BuildMixin, ViewMixin,
SiteJobsMixin, CheckerFixerMixin, ToolJobsMixin, SettingsMixin):` (see
[App (composition) (script)](app.py)). Also removed four now-orphaned top-level
imports from `gui/__init__.py` (`math`, `webbrowser`,
`from types import SimpleNamespace`, `from PIL import Image` — none
used by the file, none referenced as `gui.X` anywhere in `gui/` or
`tests/`, so none were re-export dependencies either) and ran the full
cross-project verification pass this step exists for (see
`REFACTOR-GODFILES.md`, the owner's binding plan, untracked). (The
pre-existing FEATURE-by-feature root `gui.md` this paragraph used to
point readers at was folded into the per-file `__about/`/`__flow/`
docs below and deleted in the 2026-08-01 MD-First 2.0 migration — see
the Files table.)

**Second god-file round (owner approved 2026-07-30) — and the guard
that keeps it honest.** Feature work had pushed several modules back
over the budget (`gui/tool_panels.py` 1283, `gui/viewers.py` 1185,
`gui/app_jobs.py` 1122, `gui/agent_panel.py` 1023). The owner approved
splitting the three worst files in the codebase and adding the
mandatory STRUCTURE LAW guard (root Rule #20 point 3) —
`tests/test_structure_law.py` (renamed from `test_structure.py` in the
2026-08-01 MD-First 2.0 migration), which FAILS the suite for any file
over ~1000 lines that is not a documented, owner-approved RATCHET
entry; the ratchet list may only shrink. `gui/viewers.py` split first,
into [Viewer Shared Rules](__about/viewer_shared.md),
[Doc Window](__about/doc_window.md),
[Restore Viewers](__about/restore_windows.md) and
[Image Viewer](__about/image_viewer.md).

## Files

| File | Tier | One line |
|------|------|----------|
| `__init__.py` | Standard | pure re-export shell (`from .app import PainterGui, main` + one block per submodule) — [about](__about/__init__.md) |
| `app.py` | Trivial | `PainterGui`'s MRO glue over the six mixins, plus `main()` — [script](app.py) |
| `app_build.py` | Algorithmic | Build Mixin — constructor, widget construction, font-zoom/wheel bindings, maximize/restore cover — [about](__about/app_build.md) · [flow](__flow/app_build.md) |
| `app_views.py` | Algorithmic | View Mixin — Main Menu/running-view state machine, tile router, Controls collapse — [about](__about/app_views.md) · [flow](__flow/app_views.md) |
| `app_jobs.py` | Algorithmic | Site Jobs Mixin — site + API-image run loop, worker pump/dispatch, quota auto-restart — [about](__about/app_jobs.md) · [flow](__flow/app_jobs.md) |
| `app_checker_fixer.py` | Algorithmic | Checker/Fixer Mixin — parallel Checker AI + Fixer AI (auto-dispatch and manual) — [about](__about/app_checker_fixer.md) · [flow](__flow/app_checker_fixer.md) |
| `app_tools.py` | Algorithmic | Tool Jobs Mixin — the four standalone tools + the AI image checker job — [about](__about/app_tools.md) · [flow](__flow/app_tools.md) |
| `app_settings.py` | Algorithmic | Settings Mixin — Collections queue, prerequisite actions, settings round-trip — [about](__about/app_settings.md) · [flow](__flow/app_settings.md) |
| `agent_panel.py` | Algorithmic | `AgentPanel` — one site's own control panel (Pipeline/Run behavior/Prompt groups) — [about](__about/agent_panel.md) · [flow](__flow/agent_panel.md) |
| `api_panel.py` | Algorithmic | `ApiImageGenPanel` + `ApiImageAdapter` — the paid Gemini image-API job's panel — [about](__about/api_panel.md) · [flow](__flow/api_panel.md) |
| `widgets.py` | Algorithmic | themed widget toolkit — rounded CTk factories, font-zoom registry, `ACTIVE_THEME`/`FONT_BASE` — [about](__about/widgets.md) · [flow](__flow/widgets.md) |
| `icons.py` | Algorithmic | SVG-first icon loading + the Day/Night switch's hand-rendered sun/moon art — [about](__about/icons.md) · [flow](__flow/icons.md) |
| `theme.py` | Algorithmic | the theme engine — ttk/CTk/plain-tk Day/Night flip, plain-tk skin registry, `smooth_transition` — [about](__about/theme.md) · [flow](__flow/theme.md) |
| `scroll.py` | Algorithmic | `ScrollFrame` — self-healing fill-height, resize-debounced re-fit — [about](__about/scroll.md) · [flow](__flow/scroll.md) |
| `switch.py` | Algorithmic | `DayNightSwitch` — the top-right toggle, PIL-composited art + smoothstep slide — [about](__about/switch.md) · [flow](__flow/switch.md) |
| `filter_editor.py` | Algorithmic | `FilterEditor` — the reusable stacked-condition widget + preset row — [about](__about/filter_editor.md) · [flow](__flow/filter_editor.md) |
| `aspect_canvas.py` | Algorithmic | `AspectRatioCanvas` — the live draggable target-ratio preview — [about](__about/aspect_canvas.md) · [flow](__flow/aspect_canvas.md) |
| `logic.py` | Algorithmic | Tk-free module-level functions — filter engine glue, pipeline runner, fixer decision table — [about](__about/logic.md) · [flow](__flow/logic.md) |
| `dash_helpers.py` | Standard | shared dashboard helpers — badge dots, AI-check report/tag helpers, checkerboard — [about](__about/dash_helpers.md) |
| `dash_panels.py` | Algorithmic | `JobPanel` base + `DashPanel` — one generation site's live dashboard view — [about](__about/dash_panels.md) · [flow](__flow/dash_panels.md) |
| `tool_dash.py` | Algorithmic | `ToolPanel` + `AiCheckPanel` + `DashGrid` — the tool/checker dashboard panels and grid — [about](__about/tool_dash.md) · [flow](__flow/tool_dash.md) |
| `menu.py` | Algorithmic | `MainMenu` + `IconBar` — the startup's fixed 4×2 tile grid and the HOME-led nav strip (setup + running views) — [about](__about/menu.md) · [flow](__flow/menu.md) |
| `prompt_image.py` | Algorithmic | `PromptImageSection` — the PROMPT+IMAGE mode's Reference folder + live eligibility view (faza 2) — [about](__about/prompt_image.md) |
| `select_window.py` | Algorithmic | `SelectWindow` — the per-site tick-list Toplevel over the queued Collections — [about](__about/select_window.md) · [flow](__flow/select_window.md) |
| `viewer_shared.py` | Standard | `DOC_*` window-sizing family + tiny shared viewer helpers — [about](__about/viewer_shared.md) |
| `doc_window.py` | Algorithmic | `DocWindow` — the Markdown/prompt/image viewer + Fixer-AI manual buttons — [about](__about/doc_window.md) · [flow](__flow/doc_window.md) |
| `restore_windows.py` | Algorithmic | `BeforeAfterWindow` + `StepRestoreWindow` — the before/after and per-step restore viewers — [about](__about/restore_windows.md) · [flow](__flow/restore_windows.md) |
| `image_viewer.py` | Algorithmic | `ImageViewer` — the portrait Prev/Next/Delete viewer for image-level rows — [about](__about/image_viewer.md) · [flow](__flow/image_viewer.md) |
| `dialogs.py` | Algorithmic | `_ModalToolDialog`/`_AiDialog`/`AiKeyWizard`/`AiSheetDialog` — modal dialogs — [about](__about/dialogs.md) · [flow](__flow/dialogs.md) |
| `tool_panels/` | — | the standalone-tool settings panels package — [Tool Panels (subfolder)](tool_panels/___tool_panels.md) |

`ToolSettingsPanel` and its five concrete subclasses
(`BgSettingsPanel`/`CropSettingsPanel`/`UpscaleSettingsPanel`/
`AspectSettingsPanel`/`ImageCheckerSettingsPanel`) live in the
`tool_panels/` subpackage (its own god-file split, 2026-07-30) — see
that folder's own doc for its file table. F6 (REWORK.md, owner E2):
`ImageCheckerSettingsPanel` gains a SECOND, optional picker
(`sheets_path()`) — a prompt-sheet `.md` file or a folder of them —
that `PainterGui._run_ai_check_job` uses to pair each checked image
with its own sheet prompt.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config` (every
  tunable), `aspect`/`filters`/`jobtemp`, `settings`, `sheet_parser`

### Used by
- [Main (Entry Point)](../__about/main.md) — `from gui import PainterGui`

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
`ApiImageGenPanel` all read the SAME layout constants
(`DENSE_COL_GAP_PX`/`DENSE_COL_WRAP_PX`/`ASPECT_DIALOG_ENTRY_W`, plus
the caret glyphs the collapsible sections share).
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
`_arm_probe_poll` AND `gui/doc_window.py`'s `DocWindow._arm_fix_poll`
(an unrelated Fixer-AI poll that happens to share the same cadence
constant) keep reaching it through a deferred `import gui; gui.
AI_POLL_MS` inside the method body (never at module level) — the
identical late-binding idiom `gui/theme.py`'s `_pkg()` established —
rather than a real-path `from .dialogs import AI_POLL_MS`. For
`gui.doc_window` specifically a real-path import WOULD be circular:
`gui.dialogs` imports `DocWindow` FROM `gui.doc_window` (for
`AiSheetDialog._finish`'s "not loaded" viewer), so `gui.doc_window`
cannot import back from `gui.dialogs` at module level. By the time
either poll method actually runs (well after import time), the `gui`
package has always finished initializing.

**Step 5 — the viewer/dialog Toplevels' cross-import shape.**
`gui/select_window.py` imports `DOC_HEIGHT_FRAC`/`DOC_MAX_FRAC`
directly from `gui/viewer_shared.py` (the leaf that names and owns the
`DOC_*` sizing family — since the 2026-07-30 split it has no `gui`
imports at all, so it can never take part in a cycle).
`gui/dialogs.py` imports `DocWindow` directly from
`gui/doc_window.py`, one-directional for the same reason.
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

**Step 8/8 — `app_jobs.py` split again, into `SiteJobsMixin` +
`CheckerFixerMixin`.** Post-step-7/8, `app_jobs.py` alone was 1334
lines — past the ~1000-line Rule #20 budget even after the god-CLASS
split. The split line was chosen by dependency direction, not by
line-count halving: `_dispatch` (in `SiteJobsMixin`) calls
`self._maybe_spawn_checker`/`self._maybe_spawn_fixer`, but NOTHING in
the checker/fixer methods calls back into a `SiteJobsMixin`-only
helper — every attribute they read (`self.agents`, `self.panels`,
`self._job_temps`, `self._q`, `self._running`, `self._log`,
`self._dashgrid`) is generic `PainterGui` state both mixins already
share via `BuildMixin.__init__`. So the two halves separate with ZERO
new coupling: `_dispatch` still calls those two methods by name, now
resolved through the six-mixin MRO instead of a same-class lookup —
identical at runtime either way. Imports were re-partitioned to match
(`AI_CHECK_INSTRUCTIONS`/`dest_for`/`_fixer_decision`/`PurePosixPath`
moved to `app_checker_fixer.py`; `SiteJobsMixin` kept none of them,
confirmed by grep before the move, not assumed). Verified the same way
as step 7/8: `gui.PainterGui.__mro__` shows all six mixins, the full
suite (617 passed, 1 skipped) and the four checker/fixer/pipeline/
running-view test files individually (147 passed) pass unmodified, and
a headless smoke build (menu view, `_collect_settings()`, `destroy()`)
raises nothing.

**Step 8/8 — the four `gui/__init__.py` imports removed were
genuinely orphaned by earlier moves, not a drive-by cleanup.** `math`,
`webbrowser`, `from types import SimpleNamespace` and `from PIL import
Image` were flagged because `__init__.py` is a re-export SHELL (every
name a `from .submodule import (...)` block pulls in stays reachable
as `gui.X` on purpose) — these four are different: nothing in
`__init__.py` calls `math.*`/`webbrowser.*`/`SimpleNamespace`/`Image`
any more (their last real callers moved into `app_build.py`/
`app_settings.py`/`dialogs.py`/etc. in earlier steps), AND no other
`gui/` module or `tests/*.py` file reaches them as `gui.math`/
`gui.webbrowser`/`gui.SimpleNamespace`/`gui.Image` (confirmed by grep
across both trees before removing) — so, unlike every other name in
the file, they were never serving as part of the package's public
re-export surface. Every OTHER `gui/__init__.py` import stayed exactly
as before, including ones `pyflakes` also flags "unused" — that flag
is EXPECTED for a re-export shell and is not, by itself, evidence of
dead code.
