# Read-Only Viewers

**Script:** [Read-Only Viewers (script)](viewers.py)

## Purpose
Three read-only Toplevel viewers + one pure helper, pulled out of
`gui/__init__.py` (root Rule #20 god-file refactor):

- `DocWindow` — the Markdown/prompt/image viewer (headings, code,
  bullets, bold, an optional saved-image section, a "Copy for AI"
  button), PLUS the optional Fixer-AI manual buttons (IMAGE FIX /
  WEBSITE FIX) shown only when the caller passed one or both
  zero-arg workers.
- `BeforeAfterWindow` — a tool job's before/after viewer (single-image
  Restore or whole-job RESTORE ALL).
- `_filmstrip_stages` — the pure, Tk-free per-image pipeline-stage
  list `StepRestoreWindow` renders (one `(label, path)` pair per named
  backed-up stage plus the current live file).
- `StepRestoreWindow` — the per-step restore filmstrip built from it,
  with a horizontal `ScrollFrame` and a **Restore to here** button per
  stage.

Also owns the shared `DOC_*`/`BEFORE_AFTER_*`/`STEP_RESTORE_*` sizing
constants (Rule #4) — `DOC_HEIGHT_FRAC`/`DOC_MAX_FRAC` are also read
by `gui.select_window.SelectWindow` (the "tall open" / "never bigger
than screen" clamps every doc-shaped window shares).

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`JOBTEMP_STEP_LABEL`, `STEP_RESTORE_CURRENT_LABEL`)
- [Dashboard Support Helpers](dash_helpers.md) — `_scaled_photo` (the
  transparency-checkerboard-composited thumbnail)
- [Logic](logic.md) — `_fix_result_ui` (`DocWindow`'s pure Fixer
  result-to-UI mapping)
- [Scroll (script)](scroll.py) — `ScrollFrame`
- [Theme (script)](theme.py) — `THEME_TOPLEVELS`, `skin_text`,
  `skin_toplevel`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`, `status`,
  `tk_font`
- `gui.dialogs.AI_POLL_MS` — `DocWindow._arm_fix_poll`'s OWN Fixer poll
  (unrelated to any AI dialog) reads the same cadence constant. A
  real-path `from .dialogs import AI_POLL_MS` would be circular
  (`gui.dialogs` imports `DocWindow` from THIS module for
  `AiSheetDialog._finish`'s "not loaded" viewer), so it reaches the
  constant through a deferred `import gui; gui.AI_POLL_MS` instead —
  the same late-binding idiom `gui.theme._pkg()` and
  `gui.api_panel`'s `_arm_probe_poll` already established

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `DocWindow`,
  `BeforeAfterWindow`, `StepRestoreWindow`, `_filmstrip_stages`
- [Dialogs](dialogs.md) — `AiSheetDialog._finish` opens a `DocWindow`
  when the AI-generated sheet still fails the contract after the
  repair round
- `PainterGui` (`gui/__init__.py`), `DashPanel`
  ([Dashboard Job Panel Base + Site Panel](dash_panels.md)),
  `ToolPanel`/`AiCheckPanel`
  ([Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md)) — open
  these viewers through a deferred `import gui; gui.DocWindow(...)` /
  `gui.StepRestoreWindow(...)` (never a module-level import), so
  `monkeypatch.setattr(gui, "DocWindow"/"StepRestoreWindow", fake)` in
  the test suite still reaches them regardless of which module the
  caller now lives in; `ToolPanel`'s own `BeforeAfterWindow` calls stay
  a plain real-path import (no test monkeypatches it)

## Classes

### DocWindow
See the Purpose section above.

### BeforeAfterWindow
See the Purpose section above.

### StepRestoreWindow
See the Purpose section above; built from `_filmstrip_stages`.

## Functions

### `_filmstrip_stages(temp, rel, live_path)`
Pure, Tk-free — see the Purpose section above and the function's own
docstring for the exact ordering contract `StepRestoreWindow._render`
relies on.

## Design Decisions
**`AI_POLL_MS` lives in `gui.dialogs`, not here.** `_AiDialog` (the
key wizard, the sheet generator) is the class that actually paces its
worker-queue poll loop with it, so it moved there rather than staying
behind in `gui/__init__.py` or duplicating into this module.
`DocWindow`'s own, unrelated Fixer poll reads the SAME constant via a
deferred `import gui` rather than a module-level import specifically
to avoid the cycle `gui.dialogs` (needs `DocWindow`) <-> `gui.viewers`
(would need `AI_POLL_MS`) — see the module docstring.
