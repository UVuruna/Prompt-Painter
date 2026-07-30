# Doc Window

**Script:** [Doc Window (script)](doc_window.py)

## Purpose
`DocWindow` — the readable, selectable in-app viewer for Markdown, for
people who do not want a code editor: light formatting (headings,
code, bullets, bold), an optional saved-image section, a "Copy (for
AI)" button, and the optional Fixer-AI manual buttons (IMAGE FIX /
WEBSITE FIX) shown only when the caller passed one or both zero-arg
workers. Since GUI rework Phase F4f it backs the sheet- and
folder-level dashboard rows only — image-level rows open
[Image Viewer](image_viewer.md) instead.

Split out of `gui/viewers.py` (root Rule #20 god-file refactor,
2026-07-30 — one window family per module).

Its own width follows the [Viewer Shared Rules](viewer_shared.md)
`DOC_*` family: IMAGE mode (a single image's prompt viewer) sizes to
the image's native width plus padding, TEXT mode to a portrait A4
proportion so a 200-word one-line prompt wraps into a readable column
instead of stretching the window across the screen.

## Connections

### Uses
- [Viewer Shared Rules](viewer_shared.md) — the `DOC_*` sizing family,
  `_copy_to_clipboard`, `_readonly_text_keys`
- [Dashboard Support Helpers](dash_helpers.md) — `_scaled_photo` (the
  transparency-checkerboard-composited thumbnail)
- [Logic](logic.md) — `_fix_result_ui` (the pure Fixer result-to-UI
  mapping `_apply_fix_result` applies)
- [Theme (script)](theme.py) — `THEME_TOPLEVELS`, `skin_text`,
  `skin_toplevel`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`, `status`,
  `tk_font`
- `gui.dialogs.AI_POLL_MS` — `_arm_fix_poll`'s OWN Fixer poll
  (unrelated to any AI dialog) reads the same cadence constant. A
  real-path `from .dialogs import AI_POLL_MS` would be circular
  (`gui.dialogs` imports `DocWindow` from THIS module for
  `AiSheetDialog._finish`'s "not loaded" viewer), so it reaches the
  constant through a deferred `import gui; gui.AI_POLL_MS` instead —
  the same late-binding idiom `gui.theme._pkg()` and
  `gui.api_panel`'s `_arm_probe_poll` already established

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `DocWindow`
- [Dialogs](dialogs.md) — `AiSheetDialog._finish` opens one when the
  AI-generated sheet still fails the contract after the repair round
- `PainterGui` ([Settings Mixin](app_settings.md)), `DashPanel`
  ([Dashboard Job Panel Base + Site Panel](dash_panels.md)),
  `ToolPanel`/`AiCheckPanel`
  ([Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md)) — all
  open it through a deferred `import gui; gui.DocWindow(...)` (never a
  module-level import), so `monkeypatch.setattr(gui, "DocWindow",
  fake)` in the test suite still reaches them regardless of which
  module the caller lives in
- [Checker/Fixer Mixin](app_checker_fixer.md) — builds the zero-arg
  IMAGE FIX / WEBSITE FIX workers this window runs on a background
  thread and polls for

## Classes

### DocWindow
See the Purpose section above and the class's own docstring for the
two width modes, the Markdown subset it renders, and the fix-button
contract.

## Design Decisions
**`AI_POLL_MS` lives in `gui.dialogs`, not here.** `_AiDialog` (the key
wizard, the sheet generator) is the class that actually paces its
worker-queue poll loop with it, so it moved there rather than staying
behind in `gui/__init__.py` or duplicating into this module — hence
the deferred `import gui` in `_arm_fix_poll`, which breaks what would
otherwise be a `gui.dialogs` ⇄ `gui.doc_window` cycle.
