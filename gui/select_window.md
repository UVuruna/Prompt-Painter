# Select-Images Window

**Script:** [Select-Images Window (script)](select_window.py)

## Purpose
`SelectWindow` — the per-site tick-list Toplevel over the queued
Collections (a 3-level tree: collection -> folder -> image, each leaf
with one checkbox per site), pulled out of `gui/__init__.py` (root
Rule #20 god-file refactor). Performance model: plain ttk only inside
the scroll body (no CTk canvas redraws), L3 leaf rows built/destroyed
on a folder's open/close, `Expand all` builds folder-atomic chunks
across `after()` ticks with a live progress cue instead of freezing the
main thread on a big queue, and one coalesced `after_idle` recount
services every tick/all-none click.

## Connections

### Uses
- [Painter (folder)](../painter/___painter.md) — `config`
  (`RESIZE_SETTLE_MS`, `SITES`), `sheet_parser.Sheet`
- [Scroll (script)](scroll.py) — `ScrollFrame`
- [Theme (script)](theme.py) — `THEME_TOPLEVELS`, `skin_toplevel`
- [Viewer Shared Rules](viewer_shared.md) — `DOC_HEIGHT_FRAC`/
  `DOC_MAX_FRAC` (the shared "tall open" / "never bigger than screen"
  clamps this window shares with every viewer Toplevel — imported from
  the leaf module that owns the `DOC_*` family, which has no `gui`
  dependency of its own, so no cycle is possible)
- [Themed Widget Toolkit](widgets.md) — `folder_of`, `rounded_button`,
  `status`, `tk_font`

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `SelectWindow`
- `PainterGui` (still in `gui/__init__.py`) — opens one per "Select
  images…" click, passing itself + the loaded `Sheet` list; reads
  `gui._done_on_disk`/`gui._select_var` back on the `PainterGui`
  instance it was handed (a runtime `self`/arg reference, not a
  module-level one — no import needed for those)

## Classes

### SelectWindow
See the Purpose section above. `__init__` takes `(gui: PainterGui,
sheets: list[Sheet])` — the `PainterGui` annotation is never evaluated
at runtime (`from __future__ import annotations` in this module, same
as the original file), so no import of the still-monolithic
`PainterGui` class is needed.

Done items (their saved file exists — `gui._done_on_disk`) show green
and stay RE-TICKABLE, unticked by default. Ticking one is a
deliberate REDO (owner 2026-07-27): the runner generates it again and
saves it as the next `_vN` version file beside the existing image,
which is never overwritten (see [Run Loop](../painter/runner.md) —
Resume model). All/none count-clicks still flip only the NON-done
rows; a version redo is always an individual, explicit tick.

## Design Decisions
See [GUI (folder)](___gui.md)'s own "Design Decisions" section for why
the `DOC_*` sizing constants live in `gui.viewers` rather than
duplicated here.
