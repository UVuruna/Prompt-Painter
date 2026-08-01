# ScrollFrame

**Script:** [ScrollFrame (script)](../scroll.py) ·
**Flow:** [diagram](../__flow/scroll.md)

## Purpose
A vertically (optionally also horizontally) scrollable frame — backs
the Select-images tree and wraps the whole main window. Children go
into `self.body`; without horizontal scroll the body stretches to the
canvas width (content wraps, no x scrollbar), with it the body keeps
its natural width and a horizontal bar appears.

`fill_height=True` (the whole-window wrap uses it) additionally keeps
the body at least as tall as the canvas, so a short window can always
reach the true bottom of the content. This used to be self-healed by a
perpetual `after()` poll (owner 2026-07-21 workflow fix) re-checking
the fit every `SCROLL_FILL_HEIGHT_POLL_MS`, forever, even fully idle —
the owner's own "scroll renders so badly it's horrible" report (owner
2026-07-21 perf fix) flagged the constant background timer. Replaced
with PURE events: the re-fit fires from `<Configure>` on the canvas (a
real viewport resize) and the body (nested content naturally growing)
exactly as before, PLUS an explicit `refresh()` call at every
structural change the poll used to catch instead — a Settings-gear
reveal (`AgentPanel`) or an Advanced-section reveal (`ToolSettingsPanel`
family) nested arbitrarily deep below this `ScrollFrame`, wired through
each panel's own `on_layout_change` callback (PainterGui passes
`self._scroll.refresh`). No timer runs when idle — measured: ~18
poll ticks over a 5s idle window before the fix, 0 after.

Also DEBOUNCES the resize re-fit (tightened 2026-07-20): a window
drag / maximize used to run the fill-height + scrollregion scan on
every intermediate `<Configure>` (visible jank); now a canvas
`<Configure>` only remembers the newest width and re-arms a settle
timer — the whole re-fit (body-width `itemconfigure`, fill-height,
scrollregion) runs ONCE, `RESIZE_SETTLE_MS` after the LAST
`<Configure>` ("wait for mouse release"). Measured over a synthetic
30-step drag: without deferring, 30 width writes triggered 55 CTk
child re-renders; deferring drops both to 0 during the drag itself.
Trade-off (owner accepted 2026-07-20): mid-drag content freezes at its
pre-drag width — a window-bg strip grows (or the content clips) at the
right edge — and snaps to fit `RESIZE_SETTLE_MS` after release. The
FIRST `<Configure>` of an already-settled window (initial layout, or
one lone resize with no follow-up) still applies immediately, so the
viewport never opens with a dead strip.

Split out of the former single-file `gui.py` (root Rule #20 god-file
refactor, step 2/8).

## Connections

### Uses
- [Config (subfolder)](../../painter/config/___config.md) — `RESIZE_SETTLE_MS`
- [The Theme Engine](theme.md) — `skin_canvas` (the canvas
  background re-tints on a theme flip)

### Used by
- [GUI (folder)](../___gui.md) — `__init__.py` re-exports `ScrollFrame`
  and `WHEEL_DELTA_UNIT`; wraps the whole main window and backs
  `SelectWindow`'s tree
- [Agent Panel](agent_panel.md) — `AgentPanel`'s `on_layout_change`
  calls `refresh()` after the Settings-gear reveal
- [Base Tool Settings Panel](../tool_panels/__about/base.md) —
  `ToolSettingsPanel`'s `on_layout_change` calls `refresh()` after the
  Advanced-section reveal

## Classes

### ScrollFrame
See Purpose above. Key state: `_sr_job` (the coalesced, single
`after_idle` scrollregion pass), `_sr_suspended` (bulk-build pause,
see `suspend_scrollregion`/`resume_scrollregion`), `_resizing`/
`_settle_job` (the resize-settle debounce), `_canvas_w`/`_applied_w`
(the newest vs. actually-applied body width), `_fill_h` (the
change-guard that stops the fill-height re-fit from looping against
its own `<Configure>`).

#### Key methods
- `suspend_scrollregion()` / `resume_scrollregion()` — pause the
  per-`<Configure>` scrollregion recompute for a bulk build (the
  Select window's Expand-all), so the O(content) `bbox('all')` scan
  runs ONCE at the end instead of once per chunk.
- `refresh()` — the explicit event side of `fill_height`'s re-fit;
  every widget that reveals/hides content under a `fill_height`
  ScrollFrame must call this (or a callback wired to it) since no poll
  backstops a forgetful caller anymore.

## Design Decisions
See the Purpose section above — this module's content carried over
byte-for-byte from the former `gui.py`; only its home changed. The
fill-height re-fit was made fully event-driven 2026-07-21 (perf fix);
the resize debounce was tightened 2026-07-20 — see
`painter/config/theme.py`'s comment above where
`SCROLL_FILL_HEIGHT_POLL_MS` used to live.
