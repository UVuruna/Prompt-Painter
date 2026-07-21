# Settings Mixin

**Script:** [Settings Mixin (script)](app_settings.py)

## Purpose
`SettingsMixin` — the sixth of `PainterGui`'s six mixins (root Rule
#20 god-file refactor, step 7/8 — a sixth mixin, `CheckerFixerMixin`,
was split out of `SiteJobsMixin` in step 8/8; see [GUI (folder)](___gui.md) and
[App (composition)](app.md)). Owns the Collections queue (Add…/Add
folder…/Remove/Clear — `_queue_sheets`/`_add_sheets`/
`_add_sheets_folder`/`_remove_sheet`/`_clear_sheets`), the sheet
parsing/planning helpers shared by the site jobs (`_parse_all`/
`_out_base`/`_done_on_disk`/`_plan`), the dashboard row "Show" viewers
(`_show_node`/`_show_folder_excerpt`), the top-strip PREREQUISITE
button handlers (`_open_chrome`/`_check_sheets`/`_select_images`/
`_open_instructions`/`_new_collection_ai`/`_open_key_wizard`), the AI
features' key gate (`gemini_key`/`set_gemini_key`/`_ensure_ai_key`/
`add_generated_sheet`) and the whole settings round-trip
(`_collect_settings`/`_apply_settings`/the two one-time settings
migrations for the retired Upscale/Aspect dialogs/`_wire_persistence`/
`_schedule_save`/`_save_now`/`_on_close`).

No `__init__` here — every attribute it reads (`self._sheets`, `self.
sheet_list`, `self.out_var`, `self.agents`, `self._tool_panels`, `self.
_filter_presets`, `self._settings`, `self._gemini_key`, ...) is set by
`BuildMixin.__init__`.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`DEFAULT_OUT_DIR`, `FILTER_PRESETS_SETTING`, `GEMINI_KEY_SETTING`,
  `SITES`, `UPSCALE_ASPECT_MAX`, `UPSCALE_ASPECT_MIN`,
  `UPSCALE_MIN_SIDE_DEFAULT`, `dest_for`, `iter_md_files`,
  `PROJECT_ROOT`); `settings` (`save_settings`); `sheet_parser`
  (`Sheet`, `SheetError`, `parse_sheet`); `ai` (imported locally, the
  key gate)
- [Pure Logic (script)](logic.md) — `_migrate_legacy_aspect_filter`,
  `_migrate_legacy_upscale_gate`, `_parse_condition_dicts`
- [Modal Dialogs](dialogs.md) — `AiKeyWizard`, `AiSheetDialog`
- [Select-Images Window](select_window.md) — `SelectWindow`
- [Themed Widget Toolkit](widgets.md) — `folder_of`, plus the live
  `widgets.FONT_BASE`/`widgets.ACTIVE_THEME` globals persisted by
  `_collect_settings` (module-attribute access, never a frozen `from`
  import)
- [Read-Only Viewers](viewers.md) — `DocWindow`, through a DEFERRED
  `import gui`, never a module-level import (see Design Decisions)

### Used by
- [App (composition)](app.md) — `PainterGui(..., SettingsMixin)`
- [Build Mixin](app_build.md) — `__init__` calls `_apply_settings`/
  `_wire_persistence` at startup and binds `WM_DELETE_WINDOW` to
  `_on_close`
- [Site Jobs Mixin](app_jobs.md) — `_start_site`/`_start_api_image`
  call `_parse_all`/`_out_base`/`_done_on_disk`/`_plan`
- [Tool Jobs Mixin](app_tools.md) — `_start_tool_from_panel`/
  `_start_ai_check` call `_out_base`; `_resend_flagged` calls
  `_parse_all`

## Design Decisions
- **`_open_instructions`/`_show_node`/`_show_folder_excerpt` reach
  `DocWindow` through a deferred `import gui`, not a top-of-module
  `from .viewers import DocWindow`.** `tests/test_gui_checker.py` and
  `tests/test_gui_fixer.py` do `monkeypatch.setattr(gui, "DocWindow",
  fake)` and expect these methods to call the PATCHED class — a
  real-path import would bind the real class at `app_settings.py`'s
  own import time, and the test's patch on the `gui` package object
  would never be seen. This is the SAME late-binding idiom already
  used throughout `gui/` (see [GUI (folder)](___gui.md)'s own Design
  Decisions for `DashPanel`/`AiCheckPanel`'s identical `DocWindow`/
  `StepRestoreWindow` calls). `_show_node`'s two `DocWindow` call
  sites (the "image" and final "else" branches) share ONE `import gui`
  hoisted right after its initial queue-membership guard, rather than
  repeating the import per branch (Rule #5) — importing an
  already-loaded module is cheap either way (Python caches it in
  `sys.modules`), so hoisting costs nothing and avoids the
  duplication.
- **No `__init__` here (Rule #5)** — see [Build Mixin](app_build.md).
- **The queue/sheet-management helpers (`_parse_all`/`_out_base`/
  `_done_on_disk`/`_plan`/`_log`/`_select_var`) live here, not in
  `SiteJobsMixin`, even though `_start_site` is their heaviest
  caller.** They are the SAME helpers `_check_sheets`/`_select_images`
  (this mixin's own top-strip prerequisite handlers) already call, and
  they read/write the Collections-queue state (`self._sheets`, `self.
  sheet_list`) this mixin's Add…/Remove/Clear also own — keeping them
  together avoids splitting one cohesive "queue + sheet" concern
  across two files for the sake of one caller elsewhere (Rule #5;
  every other mixin reaches them the normal way, `self._parse_all()`).
