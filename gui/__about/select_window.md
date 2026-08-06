# Select-Images Window

**Script:** [Select-Images Window (script)](../select_window.py) ·
**Flow:** [diagram](../__flow/select_window.md)

## Purpose
`SelectWindow` — the per-site tick-list Toplevel over the queued
Collections: a 3-level tree (collection -> folder -> image), one
checkbox per site per leaf, so ChatGPT and Gemini can run different
image lists from the same queue.

Every level shows a LIVE selected/total count per site; clicking a
count flips all/none over that scope+site (only the non-done leaves —
an all/none click never touches an already-generated item). Leaf
colour legend: green = done on both sites, olive = done on one site,
red = SUPERSEDED advice, orange = other advice, default = pending.
Already-done items (their saved file exists on disk — file existence
is the source of truth, no sidecar record) show unticked but stay
ENABLED; re-ticking one is a deliberate REDO — the runner saves it as
the next `_vN` version file, the existing image is never overwritten.

The window opens FIT-CONTENT width (a bounded measure of only the
~30 top-level collection titles, never the leaves) and screen-tall
height, every section COLLAPSED — so the expensive per-leaf build
never runs at open time. See the [flow diagram](../__flow/select_window.md)
for the lazy leaf build/destroy and chunked Expand-all algorithm —
the real performance engineering in this file.

## Connections
### Uses
- [Painter (folder)](../../painter/___painter.md) — `config`
  (`RESIZE_SETTLE_MS`, `SITES`), `sheet_parser.Sheet`
- [Scroll](scroll.md) — `ScrollFrame`
- [Theme](theme.md) — `THEME_TOPLEVELS`, `skin_toplevel`
- [Viewer Shared Rules](viewer_shared.md) — `DOC_HEIGHT_FRAC`/
  `DOC_MAX_FRAC`, the "tall open" / "never bigger than screen" clamps
  this window shares with every viewer Toplevel — imported from the
  leaf module that owns the `DOC_*` family (no `gui` dependency of its
  own, so no cycle is possible)
- [Themed Widget Toolkit](widgets.md) — `folder_of`, `rounded_button`,
  `status`, `tk_font`

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `SelectWindow`
- [Settings Mixin](app_settings.md) — `SettingsMixin._select_images`
  opens one per "Select images…" click, passing itself + the loaded
  `Sheet` list; the window reads `gui._done_on_disk`/`gui._select_var`
  back on the `PainterGui` instance it was handed (a runtime
  `self`/arg reference, not a module import — both helpers live in
  `SettingsMixin` too)

## Classes
### SelectWindow
`__init__(gui: PainterGui, sheets: list[Sheet], site_keys: list[str] |
None = None)` — `site_keys` (F4d, owner 2026-07-29) shows only the
TICKED sites' columns; `None` keeps every site (tests, tools). The
`gui: PainterGui` annotation is never evaluated at runtime
(`from __future__ import annotations`), so no import of the
still-cross-cutting `PainterGui` name is needed here.

Key methods: `_build_collection_data`/`_leaf_color` (the pure data
model, built before any widget so counts are correct even for
collapsed subtrees); `_build_collection_widgets`/`_build_folder_widgets`/
`_build_leaves` (L1/L2 always materialised, L3 built lazily);
`_open_folder_now`/`_close_folder_now` (the lazy build/destroy pair);
`_expand_all`/`_expand_step`/`_cancel_expand` (the chunked Expand-all —
see the flow diagram); `_toggle_scope`/`_mark_dirty`/`_recount` (the
coalesced count engine); `_fit_content_width`/`_wraplength_for`/
`_apply_wrap` (fit-content sizing and settle-debounced re-wrap);
`apply_theme` (re-colours legend/traffic-light/leaf-label foregrounds
that don't follow ttk styles).

## Design Decisions
See [GUI (folder)](../___gui.md)'s own "Design Decisions" section for
why the `DOC_*` sizing constants live in `gui.viewer_shared` rather
than duplicated here.

**The top bar's hint wraps via `gui.widgets.wrap_bar_label`** (2026-08-06,
THE SPACE & LEGIBILITY LAW rollout, `tests/test_layout_audit_tk.py`): the
production legend/hint line ("Tick = generate. Done = green ...") is long
enough on its own to force the bar past `SELECT_MIN_W` alongside the three
action buttons — it now wraps into the bar's live remaining width instead.
