# ScrollFrame

**Script:** [ScrollFrame (script)](scroll.py)

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

Also DEBOUNCES the resize re-fit: a window drag / maximize used to
run the fill-height + scrollregion scan on every intermediate
`<Configure>` (visible jank); now a canvas `<Configure>` only
remembers the newest width and re-arms a settle timer — the whole
re-fit (body-width `itemconfigure`, fill-height, scrollregion) runs
ONCE, `RESIZE_SETTLE_MS` after the LAST `<Configure>` ("wait for
mouse release").

Split out of the former single-file `gui.py` (root Rule #20 god-file
refactor, step 2/8).

## Connections

### Uses
- [Config (subfolder)](../painter/config/___config.md) — `RESIZE_SETTLE_MS`
- [The Theme Engine](theme.md) — `skin_canvas` (the canvas background
  re-tints on a theme flip)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `ScrollFrame`
  and `WHEEL_DELTA_UNIT`; wraps the whole main window and backs
  `SelectWindow`'s tree
- [Agent Panel](agent_panel.md) — `AgentPanel`'s `on_layout_change`
  calls `refresh()` after the Settings-gear reveal
- [Tool Panels](tool_panels.md) — `ToolSettingsPanel`'s
  `on_layout_change` calls `refresh()` after the Advanced-section reveal

## Design Decisions
See the module docstring above and [GUI (folder)](___gui.md) — this
module's content carried over byte-for-byte from the former `gui.py`;
only its home changed. The fill-height re-fit was made fully
event-driven 2026-07-21 (perf fix) — see the module docstring's own
history note and `painter/config/theme.py`'s comment above where
`SCROLL_FILL_HEIGHT_POLL_MS` used to live.
