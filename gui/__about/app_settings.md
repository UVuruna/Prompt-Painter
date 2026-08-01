# Settings Mixin

**Script:** [Settings Mixin (script)](../app_settings.py) ·
**Flow:** [diagram](../__flow/app_settings.md)

## Purpose
`SettingsMixin` — the sixth of `PainterGui`'s six mixins (root Rule
#20 god-file refactor, step 7/8; see [GUI (folder)](../___gui.md) and
[App (composition)](../app.py)). Owns the Collections queue (Add…/Add
folder…/Remove/Clear — `_queue_sheets`/`_add_sheets`/
`_add_sheets_folder`/`_remove_sheet`/`_clear_sheets`), the sheet
parsing/planning helpers shared by the site jobs (`_parse_all`/
`_out_base`/`_done_on_disk`/`_plan`), the dashboard row "Show" viewers
(`_show_node`/`_show_folder_excerpt`), the top-strip prerequisite
button handlers (`_check_sheets`/`_select_images`/`_open_instructions`/
`_new_collection_ai`/`_open_key_wizard` — `_open_chrome` was retired in
F4g, Chrome is ensured automatically at Start), the AI features' key
gate (`gemini_key`/`set_gemini_key`/`_ensure_ai_key`/
`add_generated_sheet`) and the whole settings round-trip
(`_collect_settings`/`_apply_settings`/the two one-time migration
helpers/`_schedule_save`/`_save_now`/`_on_close`).

**F4h (owner 2026-07-29): `_show_node` is GUARDED end to end** — a
viewer failure (any exception) logs the full traceback and shows a
dialog instead of killing the app, so a recurrence pins itself
(instrumented, deliberately NOT declared "fixed" per root Rule #25,
since the crash it targets was never actually reproduced).

**GUI rework Phase F4f (owner G6/G7): image-level "Show" opens
`ImageViewer`, not `DocWindow`.** `_show_node_inner` still opens
`DocWindow` for the collection and folder levels, but a clicked IMAGE
row opens [Image Viewer](image_viewer.md) over the WHOLE collection's
items (`_image_viewer_entries` — sheet order, each `dest` resolved via
`dest_for`, except the CLICKED item, which uses the dashboard row's own
ACTUAL saved `rel` — honoring a `_vN` redo) so its Prev/Next can walk
the collection in one window. Three small adapter methods bridge
`ImageViewer`'s generic `check_lookup`/`steps_lookup`/`restore_cb`
callbacks onto the SAME `DashPanel._check_results`/`JobTemp` data the
Check…/Steps… surfaces already use — one shared data source, two
launch surfaces (Rule #5). `_image_viewer_on_deleted` (owner G7) only
LOGS a delete — no cheap rel→tree-node index survives a collection
switch to live-patch the dashboard row, so building that plumbing for
a cosmetic gap was deliberately skipped (root Rule #15).

## Connections

### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`DEFAULT_OUT_DIR`, `FILTER_PRESETS_SETTING`, `GEMINI_KEY_SETTING`,
  `SITES`, `UPSCALE_ASPECT_MAX`, `UPSCALE_ASPECT_MIN`,
  `UPSCALE_MIN_SIDE_DEFAULT`, `dest_for`, `iter_md_files`,
  `PROJECT_ROOT`, `DASH_MODES`, `JOBTEMP_STEP_LABEL`); `settings`
  (`save_settings`); `sheet_parser` (`Sheet`, `SheetError`,
  `parse_sheet`); `ai` (imported locally, the key gate)
- [Pure Logic](logic.md) — `_migrate_legacy_aspect_filter`,
  `_migrate_legacy_upscale_gate`, `_parse_condition_dicts`
- [Modal Dialogs](dialogs.md) — `AiKeyWizard`, `AiSheetDialog`
- [Select-Images Window](select_window.md) — `SelectWindow`
- [Widgets](widgets.md) — `folder_of`, plus the live
  `widgets.FONT_BASE`/`widgets.ACTIVE_THEME` globals persisted by
  `_collect_settings` (module-attribute access, never a frozen `from`
  import)
- [Doc Window](doc_window.md) — `DocWindow`, through a DEFERRED
  `import gui`, never a module-level import (see Design Decisions)
- [Image Viewer](image_viewer.md) — `ImageViewer` (a plain real-path
  import: no test monkeypatches it)
- [Restore Viewers](restore_windows.md) — `_filmstrip_stages`
- [Viewer Shared Rules](viewer_shared.md) — `_restore_step`

### Used by
- [App (composition)](../app.py) — `PainterGui(..., SettingsMixin)`
- [Build Mixin](app_build.md) — `__init__` calls `_apply_settings`/
  `_wire_persistence` at startup and binds `WM_DELETE_WINDOW` to
  `_on_close`
- [Site Jobs Mixin](app_jobs.md) — `_start_site`/`_start_api_image`
  call `_parse_all`/`_out_base`/`_done_on_disk`/`_plan`
- [Tool Jobs Mixin](app_tools.md) — `_start_tool_from_panel`/
  `_start_ai_check` call `_out_base`; `_resend_flagged` calls
  `_parse_all`

## Classes

### SettingsMixin
Key methods: `_queue_sheets`/`_add_sheets`/`_add_sheets_folder`/
`_remove_sheet`/`_clear_sheets` (the Collections queue), `_parse_all`/
`_out_base`/`_done_on_disk`/`_plan` (sheet parsing/planning shared with
the job mixins), `_show_node`/`_show_node_inner`/`_show_folder_excerpt`
(dashboard row viewers), `_image_viewer_entries`/
`_image_viewer_check_lookup`/`_image_viewer_steps_lookup`/
`_image_viewer_restore_cb`/`_image_viewer_on_restored`/
`_image_viewer_on_deleted` (F4f's `ImageViewer` wiring),
`_ensure_ai_key`/`set_gemini_key`/`gemini_key` (the AI key gate),
`_collect_settings`/`_apply_settings`/`_migrate_upscale_panel_settings`/
`_migrate_aspect_panel_settings` (the settings round-trip + its two
one-time migrations), `_wire_persistence`/`_schedule_save`/`_save_now`/
`_on_close`.

## Design Decisions
- **`_open_instructions`/`_show_node`/`_show_folder_excerpt` reach
  `DocWindow` through a deferred `import gui`, not a top-of-module
  `from .doc_window import DocWindow`.** `tests/test_gui_checker.py`
  and `tests/test_gui_fixer.py` do `monkeypatch.setattr(gui,
  "DocWindow", fake)` and expect these methods to call the PATCHED
  class — a real-path import would bind the real class at
  `app_settings.py`'s own import time, and the test's patch on the
  `gui` package object would never be seen. This is the SAME
  late-binding idiom already used throughout `gui/` (see [GUI (folder)](../___gui.md)'s
  own Design Decisions for `DashPanel`/`AiCheckPanel`'s identical
  `DocWindow`/`StepRestoreWindow` calls). `_show_node`'s two `DocWindow`
  call sites (the "image" and final "else" branches) share ONE `import
  gui` hoisted right after its initial queue-membership guard, rather
  than repeating the import per branch (Rule #5).
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
- **Settings.json is always a FULL overwrite, never a merge**
  (`_save_now`/`_collect_settings`) — so any state that should survive
  a save (a filter preset, a migrated field) MUST live in a
  `PainterGui` in-memory attribute, not only on disk momentarily; every
  migration helper in this file follows the same "read the old key
  once, write only the new shape, never rewrite the old key" contract
  so stale keys naturally drop off disk over time.
