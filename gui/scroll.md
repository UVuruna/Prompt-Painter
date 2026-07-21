# ScrollFrame

**Script:** [ScrollFrame (script)](scroll.py)

## Purpose
A vertically (optionally also horizontally) scrollable frame — backs
the Select-images tree and wraps the whole main window. Children go
into `self.body`; without horizontal scroll the body stretches to the
canvas width (content wraps, no x scrollbar), with it the body keeps
its natural width and a horizontal bar appears.

`fill_height=True` (the whole-window wrap uses it) additionally
self-heals: whenever the embedded body's true required height grows
past what was last applied — a Settings gear reveal, a filter row
added, anything with no reference to THIS `ScrollFrame` to call
`refresh()` on — a cheap periodic check catches the mismatch and
recomputes, so a short window can always reach the true bottom of the
content regardless of which caller forgot to ask.

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
- [Config (subfolder)](../painter/config/___config.md) —
  `RESIZE_SETTLE_MS`, `SCROLL_FILL_HEIGHT_POLL_MS`
- [The Theme Engine](theme.md) — `skin_canvas` (the canvas background
  re-tints on a theme flip)

### Used by
- [GUI (folder)](___gui.md) — `__init__.py` re-exports `ScrollFrame`
  and `WHEEL_DELTA_UNIT`; wraps the whole main window and backs
  `SelectWindow`'s tree

## Design Decisions
See the module docstring above and [GUI (folder)](___gui.md) — this
module's content (and the reasoning behind the self-healing poll /
resize debounce) carried over byte-for-byte from the former
`gui.py`; only its home changed.
