# API Image Job (PainterGui mixin)

**Script:** [API Image Job (script)](../app_api_image_job.py) ·
**Flow:** [diagram](../__flow/app_api_image_job.md)

## Purpose
`ApiImageJobMixin` — the paid-API image job (`_start_api_image`), one of
`PainterGui`'s responsibility slices (see [GUI (folder)](../___gui.md)
for the whole composition).

The job that generates through the paid Gemini API instead of driving a
browser tab. It checks the panel's access gate first
(`panel.access_gated` — the "Check API access" probe's verdict, defense
in depth beside the panel's own Start guard), builds an
`ApiImageAdapter` (a `SiteDriver`-shaped stand-in whose `attach`/`close`/
`await_done` are no-ops and whose `extract_image` makes the real
`ai.generate_image` call), and hands it to the SAME `run_sheet` loop the
browser sites use — so pacing, post-save, the dashboard and the report
are ONE code path, not two.

**Why it is its own module.** It sits beside the site run loop rather
than inside it because the two share only `run_sheet`: one speaks CDP to
a tab, the other speaks HTTP to an API, and neither branches on the
other. Split from `gui/app_jobs.py` on 2026-08-18 (audit
[AUDIT-OOP-2026-08-18](../../docs/AUDIT-OOP-2026-08-18.md) → R5) — the
exact three-way split the structure ratchet had already named.

No `__init__` here — every attribute it reads is set by
`BuildMixin.__init__`, and the site-loop helpers it calls
(`_compose_post_save`, `_update_status`, `_sync_running_state`) resolve
through the shared `PainterGui` MRO exactly as before.

## Connections

### Uses
- [API Panel](api_panel.md) — `ApiImageAdapter` (the `SiteDriver`-shaped
  stand-in) and the panel's settings + access gate
- [Config (subfolder)](../../painter/config/___config.md) —
  `AI_IMAGE_GATE_MESSAGE`, `TIMING`, `prompt_suffix`
- [Painter (folder)](../../painter/___painter.md) — `jobtemp`,
  `run_sheet`
- [Site Jobs](app_jobs.md) — `_compose_post_save`, `_update_status`,
  `_sync_running_state`, through the shared MRO
- [Queue Pump](app_dispatch.md) — every message this job's worker posts
  lands there

### Used by
- [GUI (folder)](../___gui.md) — `gui/app.py` composes it into
  `PainterGui`

## Classes

### ApiImageJobMixin
`_start_api_image`. Never instantiated alone.
