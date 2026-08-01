# GUI Package Index

**Script:** [GUI Package Index (script)](../__init__.py)

*(Tier note: Standard, not Trivial — at 286 lines it is over the
60-line Trivial cap, but it is 100% mechanical re-export code with no
logic of its own; no `__flow` diagram accompanies it, per the
Algorithmic-only flow rule.)*

## Purpose
A PURE re-export shell: `from .app import PainterGui, main` plus one
explicit `from .submodule import (...)` block per extracted submodule,
unchanged — so every existing `gui.X` / `from gui import X` call site
across the whole package split (root Rule #20 god-file refactor, see
[GUI (folder)](../___gui.md)'s intro for the full 8-step split
history) kept working with zero caller changes.

**Two mutable-global EXCEPTIONS to the re-export pattern.**
`ACTIVE_THEME` and `FONT_BASE` are deliberately NOT re-exported as
bare names here, even though `widgets.py` (where they live) IS
imported from below. Both are REBOUND — not just mutated — at
runtime: a theme flip reassigns `ACTIVE_THEME`, a zoom reassigns
`FONT_BASE`. A plain `from .widgets import ACTIVE_THEME` would bind a
snapshot of whatever the name pointed to AT IMPORT TIME and never see
a later flip/zoom — a real, silent correctness bug, not a style
nitpick. Every place in this codebase that needs the LIVE value reads
it off `widgets.ACTIVE_THEME` / `widgets.FONT_BASE` (a
module-attribute access, e.g. `gui/theme.py`'s `_apply_theme_now` and
`gui/switch.py`'s `DayNightSwitch.__init__`) instead of importing the
bare name.

**Four orphaned imports were removed in the final split step** (`math`,
`webbrowser`, `from types import SimpleNamespace`, `from PIL import
Image`) — confirmed by grep that nothing in `__init__.py` calls them
any more (their last real callers had moved into `app_build.py`/
`app_settings.py`/`dialogs.py`/etc. in earlier steps) AND that no
other `gui/` module or test reaches them as `gui.math`/`gui.webbrowser`/
`gui.SimpleNamespace`/`gui.Image`. Every OTHER import in this file
stays even if a linter flags it "unused" — that is EXPECTED for a
re-export shell (the name must stay reachable as `gui.X`), not
evidence of dead code.

## Connections
### Uses
Every submodule of `gui/`, one `from .X import (...)` block each:

- [App (composition)](../app.py) — `PainterGui`, `main`
- [Widgets (Themed Widget Toolkit)](widgets.md) — the CTk control
  factory / font-zoom / expander bare names (NOT `ACTIVE_THEME`/
  `FONT_BASE` — see Purpose)
- [Agent Panel](agent_panel.md) — `AgentPanel`
- [API Panel](api_panel.md) — `ApiImageAdapter`, `ApiImageGenPanel`
- [Dashboard Support Helpers](dash_helpers.md) — the checkerboard/
  scaled-photo/AI-check-doc helpers, `badge_dots`, `build_job_tree`,
  `fmt_time_summary`
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) —
  `DashPanel`, `JobPanel`
- [Modal Dialogs](dialogs.md) — `AI_POLL_MS`, `AiKeyWizard`,
  `AiSheetDialog`, `_AiDialog`, `_ModalToolDialog`
- [FilterEditor](filter_editor.md) — `FilterEditor`
- [Icons](icons.md) — the SVG/PIL icon-loading and switch-art internals
- [Logic](logic.md) — the pure Tk-free module-level helpers
- [Main Menu + Icon Bar](menu.md) — `IconBar`, `MainMenu`
- [Scroll](scroll.md) — `WHEEL_DELTA_UNIT`, `ScrollFrame`
- [Select-Images Window](select_window.md) — `SelectWindow`
- [DayNightSwitch](switch.md) — `DayNightSwitch`
- [Theme](theme.md) — the Day/Night flip engine, the plain-tk skin
  registry, `THEME_TOPLEVELS`, `smooth_transition`
- [Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md) —
  `AiCheckPanel`, `DashGrid`, `ToolPanel`
- [Tool Panels (subfolder)](../tool_panels/___tool_panels.md) —
  `AspectSettingsPanel`, `BgSettingsPanel`, `CropSettingsPanel`,
  `ImageCheckerSettingsPanel`, `ToolSettingsPanel`,
  `UpscaleSettingsPanel`
- [Doc Window](doc_window.md) — `DocWindow`
- [Image Viewer](image_viewer.md) — `ImageViewer`
- [Restore Viewers](restore_windows.md) — `BeforeAfterWindow`,
  `StepRestoreWindow`, `_filmstrip_stages`
- `painter` (project root) — `config` (the whole tunable-constant
  surface), `aspect`, `jobtemp`, `settings.load_settings`/
  `save_settings`, `sheet_parser.Sheet`/`SheetError`/`parse_sheet` —
  no `.md` doc target from here; see the [Painter (folder)](../../painter/___painter.md)
  entry point for the full breakdown

### Used by
- `main.py` (project root) — `from gui import PainterGui`. No
  `main.md` exists yet for this project-root script, so this is
  documented in prose rather than as a broken link.
- Every test and caller that reaches a moved class/function as
  `gui.X` instead of importing the owning submodule directly — the
  entire reason this file is a re-export shell rather than a bare
  `from .app import PainterGui, main`

## Classes
None — no class or function body of its own; see the Purpose section.

## Design Decisions
See [GUI (folder)](../___gui.md)'s own "Design Decisions" section —
in particular "The two mutable-global exceptions to the re-export
pattern" and "Step 8/8 — the four `gui/__init__.py` imports removed
were genuinely orphaned by earlier moves, not a drive-by cleanup",
which this file's Purpose section above summarizes.
