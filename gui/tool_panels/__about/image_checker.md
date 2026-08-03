# Image Checker Settings Panel

**Script:** [Image Checker Settings Panel (script)](../image_checker.py) ·
**Flow:** [diagram](../__flow/image_checker.md)

## Purpose

Faza 4 (owner 2026-08-03, UV tačka 5): the VISION model pick
lives on THIS panel now — a shared
[Model Picker Row](../../__about/model_picker.md) at the top of
`_build_extra` (capable-only list, curated hint, immediate
persist); the run still resolves via `ai.model_for("vision")`,
which reads the same override. The footer names "the picked
Vision model above" instead of a hardcoded constant.

`ImageCheckerSettingsPanel` — the AI image checker's own settings
panel (GUI rework Phase 15): the same input-picker + Filter +
Start/Pause/Stop chrome every standalone tool has, plus its own
optional prompt-sheet source (F6) and an informational footer (model,
pacing, where flags persist). No engine knobs (`HAS_ADVANCED = False`)
— the checker is read-only. Its Start bypasses `build_func`/
`_launch_tool_worker` entirely, wired straight to `PainterGui.
_start_ai_check` instead (a fundamentally different worker shape — no
JobTemp backup, since the run never modifies a file).

Split out of the single-file `gui/tool_panels.py` (root Rule #20,
2026-07-30).

## Connections

### Uses
- [Base Tool Settings Panel](base.md) — the shared chrome
- [Layout Constants](layout.md) — `DENSE_COL_WRAP_PX`
- [Themed Widget Toolkit](../../__about/widgets.md) — `rounded_button`
- [Config (subfolder)](../../../painter/config/___config.md) —
  `AI_CALL_PAUSE_S`, `GEMINI_VISION_MODEL`, `STATE_DIRNAME` (the
  footer's model/pacing/flags note)

### Used by
- [Tool Panels (subfolder)](../___tool_panels.md) — re-exported as
  `ImageCheckerSettingsPanel`
- [Tool Jobs Mixin](../../__about/app_tools.md) — the AI image-checker job
  (`SLOT = "aicheck"`)

## Classes

### ImageCheckerSettingsPanel
`SLOT = "aicheck"`, `HAS_ADVANCED = False`. `_picker_title_suffix`
overrides the base's "runs IN PLACE" wording to `"(read-only)"` — a
vision pass must never claim to write anything (root Rule #1).

One asymmetry from its four siblings: this panel's `MENU_TILES` id
(`"image_checker"`) differs from its own `SLOT`/`JOB_ORDER` kind
(`"aicheck"`) — the checker already existed as the dashboard's own job
kind (`AiCheckPanel`, owner 2026-07-20) before this panel did, so its
slot name predates and is independent of the tile system. `PainterGui.
_tool_panel_key` (backed by `config.tile_for_kind`) is the one
translation point bridging the two spaces.

F6 (owner E2): a SECOND, OPTIONAL picker (`_build_extra`) — a
prompt-sheet `.md` FILE or a FOLDER of them, mirroring the Collections
queue's own Add…/Add folder… pair. Empty (the default,
`sheets_path() -> None`) keeps the images-only, quality-only check.
When given, `PainterGui._run_ai_check_job` pairs each checked image to
its own sheet PROMPT via `ai.drop_and_site_for` and checks only the
matched subset — the picked path itself is handed over UNRESOLVED (a
folder is only walked on the worker thread, never on the Tk one).

**Stop reuses `PainterGui._stop_tool` UNCHANGED** — that method is
already fully generic over any slot with a `_tool_workers`/
`_stop_events` entry, so a near-identical `_stop_ai_check` would only
duplicate it (Rule #5).

#### Key methods
- `_build_extra` — the optional Sheet file… / Sheets folder… picker.
- `sheets_path() -> Path | None` — the picked prompt-sheet source;
  `PainterGui._start_ai_check` reads this alongside `resolve_input()`/
  `get_conditions()` and hands it to `_run_ai_check_job` unresolved.
- `_build_footer` — the model + pacing + flags-location note.
