# Image Checker Settings Panel

**Script:** [Image Checker Settings Panel (script)](image_checker.py)

## Purpose
The AI image checker's settings panel — no engine knobs, just the
base's own picker + an optional unseeded `FilterEditor` and an
informational footer (model, pacing, where flags persist). Its Start
bypasses `build_func`/`_launch_tool_worker` entirely, wired straight
to `PainterGui._start_ai_check` instead (a fundamentally different
worker shape — no JobTemp backup, since the run is read-only).


Split out of the single-file `gui/tool_panels.py` (root Rule #20,
2026-07-30).

## Connections

### Uses
- [Base Tool Settings Panel](base.md) — the shared chrome
- [Layout Constants](layout.md) — `DENSE_COL_WRAP_PX`
- [Themed Widget Toolkit](../widgets.md) — `rounded_button`
- [Config (subfolder)](../../painter/config/___config.md) —
  `AI_CALL_PAUSE_S`, `GEMINI_VISION_MODEL`, `STATE_DIRNAME` (the
  footer's model/pacing/flags note)

### Used by
- [Tool Panels (subfolder)](___tool_panels.md) — re-exported
- [Tool Jobs Mixin](../app_tools.md) — the AI image-checker job

## Classes

### ImageCheckerSettingsPanel
See the Purpose section above.
