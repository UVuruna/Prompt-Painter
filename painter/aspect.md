# Change Aspect Ratio

**Script:** [Change Aspect Ratio (script)](aspect.py)

## Purpose
The owner's standalone batch **deform** tool (2026-07-19): pick image
FILES **or** a folder and a target ratio `X:Y`, then non-proportionally
STRETCH every image to that ratio IN PLACE. It stands beside the other
in-place batch tools (background removal, crop, upscale) and reports on
the dashboard the same way — `done` = resized, `nothing`/Refused =
already at ratio **or filtered out**.

An optional INPUT FILTER (owner 2026-07-19) gates which images are
touched by their CURRENT ratio `cur = W/H`: a `[from, to]` range plus a
mode — `off` (process all), `IF` (process ONLY in-range), `IF NOT` (skip
in-range, process the rest). A filtered-out image is a plain `"nothing"`
skip (no backup). This is what makes a whole-folder input useful: throw
the project at it with `IF NOT 0.9-1.1` and only the not-already-square
images deform.

**The rule (owner-approved): never shrink either dimension.** The
result is the smallest box of the target ratio that still CONTAINS the
original, so exactly ONE axis grows and neither is cut. For an image
`w x h` and target `X:Y` (X = width units, Y = height units):

```
target = X / Y ; cur = w / h
|cur - target| <= ASPECT_TOL  -> already at ratio ("nothing")
cur < target                  -> keep height, grow width:
                                 new_w = round(h * X / Y), new_h = h
else                          -> keep width, grow height:
                                 new_h = round(w * Y / X), new_w = w
```

The resize is a deliberate non-proportional LANCZOS stretch; the image
mode (and so its alpha: RGBA in → RGBA out) is preserved and the file
is written back as PNG. Verified by hand (must reproduce exactly):

| Source | Target | Result |
|--------|--------|--------|
| 1024×1024 | 16:9 | 1820×1024 |
| 1536×1024 | 16:9 | 1820×1024 |
| 1024×1536 | 9:16 | 1024×1820 |
| 1024×1024 | 1:2  | 1024×2048 |

## Connections

### Uses
- [Config](config.md) — `ASPECT_TOL` (the already-at-ratio tolerance)
  and `ASPECT_FILTER_OFF` / `ASPECT_FILTER_IF` / `ASPECT_FILTER_IF_NOT`
  (the input-filter modes)
- Pillow (LANCZOS resize, PNG save)

### Used by
- [GUI](../gui.md) — the standalone **"Aspect ratio…"** toolbar button
  (its `AspectRatioDialog` asks for `W : H` + an optional STACKED
  filter — a `FilterEditor`, GUI rework Phase 4, replacing this
  module's own scalar `filter_from`/`filter_to`/`filter_mode` params in
  the GUI's call — + a files-or-folder choice). The GUI now pre-filters
  WHICH FILES are passed to `change_aspect` itself, via
  `painter.filters.matches()`, so it always calls this function with
  its filter args at their unused `off` defaults; this function's OWN
  `filter_from`/`filter_to`/`filter_mode` parameters are unchanged and
  still exercised directly by `test_aspect.py` and the CLI — nothing
  here was touched by that migration

## Functions

- `change_aspect(path, ratio_w, ratio_h, log, *, tol=ASPECT_TOL,
  filter_from=None, filter_to=None, filter_mode="off") -> str` — stretch
  one image to the target ratio in place. First applies the optional
  INPUT FILTER on `cur = W/H`: `IF` returns `"nothing"` when `cur` is NOT
  in `[filter_from, filter_to]`, `IF NOT` returns `"nothing"` when it IS,
  `off` never filters. Otherwise returns `"done"` (resized) or
  `"nothing"` (already at ratio within `tol`); a `"nothing"` leaves the
  file BYTE-UNCHANGED (no write). Raises `AspectError` loudly on a
  non-positive target ratio or a real image failure; a no-op never
  raises, so a batch survives one bad file.

## Design Decisions

- **Grow-only, never shrink.** Stretching one axis up (rather than
  cropping or letterboxing) keeps every original pixel; the owner wants
  the whole image forced to the frame, deformation accepted.
- **Byte-unchanged no-op.** An image already at the target ratio — or
  filtered out by the input filter — returns `"nothing"` BEFORE any save,
  so re-running the tool over a finished folder rewrites nothing and the
  Refused count is honest.
- **Filter on the RATIO only** (a single W/H range, owner-confirmed), not
  separate W/H bounds — the upscale gate keeps its own separate rule. The
  filter lives in the engine so a filtered image is a genuine skip the
  loop treats like any other no-op (temp backup dropped).
- **Same shape as the other standalone tools** (`func(path, log) ->
  str`), so the GUI drives all four (BG removal / crop / upscale /
  aspect) through one loop with one dashboard-reporting path.
