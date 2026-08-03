# Doc Window

**Script:** [Doc Window (script)](../doc_window.py) ·
**Flow:** [diagram](../__flow/doc_window.md)

## Purpose
`DocWindow` — the readable, selectable in-app viewer for Markdown, for
people who do not want a code editor: light formatting (headings,
code, bullets, bold), an optional saved-image section, a "Copy (for
AI)" button, and the optional Fixer-AI manual buttons (IMAGE FIX /
WEBSITE FIX) shown only when the caller passed one or both zero-arg
workers. Since GUI rework Phase F4f it backs the SHEET- and
FOLDER-level dashboard rows only — IMAGE-level rows open
[Image Viewer](image_viewer.md) instead (verified against the current
caller, `SettingsMixin._show_node_inner` in `app_settings.py`: the
`"image"` branch opens `ImageViewer`, the `"folder"` branch opens the
folder excerpt through `DocWindow`, and the remaining — collection —
branch opens the whole file through `DocWindow`).

Split out of the former `gui/viewers.py` (root Rule #20 god-file
refactor, 2026-07-30 — one window family per module).

Its own width follows the [Viewer Shared Rules](viewer_shared.md)
`DOC_*` family: IMAGE mode (a single image's prompt viewer, when
`image_path` is given) sizes to the image's native width plus padding
so the picture shows large and the prompt wraps into that same
column; TEXT mode (instructions / a whole collection file / a folder
excerpt) sizes to a portrait A4 proportion so a long one-line prompt
wraps into a readable column instead of stretching across the screen.
Height is fitted to the ACTUALLY-RENDERED content, measured once the
window is first mapped (unmapped, the Text reports zero height) — see
the [flow diagram](../__flow/doc_window.md).

## Connections
### Uses
- [Viewer Shared Rules](viewer_shared.md) — the `DOC_*` sizing family,
  `_copy_to_clipboard`, `_readonly_text_keys`
- [Dashboard Support Helpers](dash_helpers.md) — `_scaled_photo` (the
  transparency-checkerboard-composited thumbnail)
- [Logic](logic.md) — `_fix_result_ui` (the pure Fixer result-to-UI
  mapping `_apply_fix_result` applies)
- [Theme](theme.md) — `THEME_TOPLEVELS`, `skin_text`, `skin_toplevel`
- [Themed Widget Toolkit](widgets.md) — `rounded_button`, `status`,
  `tk_font`
- `gui.dialogs.AI_POLL_MS` — `_arm_fix_poll`'s OWN Fixer poll
  (unrelated to any AI dialog) reads the same cadence constant. A
  real-path `from .dialogs import AI_POLL_MS` would be circular
  (`gui.dialogs` imports `DocWindow` FROM this module, for
  the retired `AiSheetDialog` once did), so it reaches the
  constant through a deferred `import gui; gui.AI_POLL_MS` instead —
  the same late-binding idiom `gui.theme._pkg()` and
  `gui.api_panel`'s `_arm_probe_poll` already established

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `DocWindow`
- [Settings Mixin](app_settings.md) — `_open_instructions`,
  `_show_node_inner` (the collection-level branch), and
  `_show_folder_excerpt` all open it through a deferred
  `import gui; gui.DocWindow(...)`
- [Dashboard Job Panel Base + Site Panel](dash_panels.md) — `DashPanel`
  opens it the same deferred way
- [Tool + AI-Checker Dashboard Panels + Grid](tool_dash.md) —
  `ToolPanel`/`AiCheckPanel` open it the same deferred way
- All four deferred-import call sites exist so
  `monkeypatch.setattr(gui, "DocWindow", fake)`
  (`test_gui_checker.py`, `test_gui_fixer.py`) reaches the class
  actually constructed, regardless of which module the caller lives in
- [Checker/Fixer Mixin](app_checker_fixer.md) — `_build_fix_workers`
  builds the zero-arg IMAGE FIX / WEBSITE FIX workers this window runs
  on a background thread and polls for

## Classes
### DocWindow
See the Purpose section above and the class's own docstring for the
two width modes, the Markdown subset it renders (`# `/`## `/`### `
headings, fenced code blocks, `- `/`* ` bullets, `**bold**` spans),
and the fix-button contract. Key methods: `_apply_width` (mode-based
width, before render), `_fit_height` (post-map content-height fit),
`_render`/`_insert_inline` (the tiny Markdown-subset renderer),
`_run_fix`/`_arm_fix_poll`/`_poll_fix`/`_apply_fix_result` (the
Fixer-AI worker-thread + poll loop).

## Design Decisions
**`AI_POLL_MS` lives in `gui.dialogs`, not here.** `_AiDialog` (the key
wizard, the sheet generator) is the class that actually paces its
worker-queue poll loop with it, so it moved there rather than staying
behind in `gui/__init__.py` or duplicating into this module — hence
the deferred `import gui` in `_arm_fix_poll`, which breaks what would
otherwise be a `gui.dialogs` <-> `gui.doc_window` cycle.
