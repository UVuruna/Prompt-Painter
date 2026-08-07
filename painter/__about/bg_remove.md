# Background Remover

**Script:** [Background Remover (script)](../bg_remove.py) ·
**Flow:** [diagram](../__flow/bg_remove.md)

## Purpose

Makes a generated image's background transparent. Originally built
inside DOMY Watch (`tools/bg_remove.py`); moved here 2026-07-17 on
the owner's rule that no part of this program lives in another
project. Also runnable standalone
(`python painter/bg_remove.py <file-or-folder> --in-place --crop`).

### One engine, several recipes

`remove_color_background` is the ONLY removal (owner 2026-07-28, root
Rule #19 — define the rule, never enumerate the cases). It clears the
BORDER-CONNECTED region within a per-channel distance of a TARGET
COLOUR; white, black and any custom colour are three sets of arguments
to it, not three algorithms:

```
distance(pixel, target) = MAX over channels of |pixel_channel - target_channel|
matching                = pixels with distance <= dist_edge

IF reach is EDGE (default):
    background = the matching pixels REACHABLE FROM THE IMAGE FRAME,
                 walking only through other matching pixels
                 (a flood fill inward from all four sides)
ELSE (reach is ALL):
    background = every matching pixel, wherever it sits

alpha                   = 0        where distance <= dist_full
                          ramps    between dist_full and dist_edge
                          255      elsewhere
                          (then a Gaussian feather when sigma > 0)
```

### Why enclosed regions of the background colour survive

The default `reach` is a **flood fill from the frame**, not a colour
test. A pixel is background only if you can walk to it from the edge
of the image through other matching pixels. So the counters inside the
letters of HOPE / SALVATION — pure `#000000`, identical to the
background — stay OPAQUE: the letter stroke walls them off, and the
fill never reaches them. `BG_REACH_ALL` (owner 2026-07-28) drops the
connectivity test: every matching pixel goes, wherever it sits, and
the letters are left as outlines. Measured on Compass-Ages: 42.14 %
edge-reach vs 42.42 % everywhere — the difference IS the letter
counters.

That single key subsumes both historical ones EXACTLY: distance from
black `#000000` is `max(r,g,b)` (the old `brightness`) and distance
from white `#FFFFFF` is `255 - min(r,g,b)` (255 minus the old
`whiteness`) — so black and white lost no tuning when they became
targets (verified byte-identical against the pre-refactor code over
17 real plates and 400 randomised ones).

Only BORDER-CONNECTED pixels are cleared, so a dark region ENCLOSED by
the subject stays opaque. This replaced the old "largest bright blob +
fill holes" disc, which could not tell a DARK subject from a black
background and ate the dark stone frame of the bible/dark rondels
(50-78% turned transparent — swiss cheese).

### Which recipe an image gets — `plan(img, mode)`

- **`BG_MODE_AUTO`** — three steps, in order:
  1. sniff the outer 1% frame for white / off-white (thresholds
     ADAPTED to that plate's own white level);
  2. else sniff it for a black void;
  3. else ask the **FOUR CORNERS** (owner 2026-07-28, his own rule).
     Each corner contributes its median; if all four agree within
     `AUTO_CORNER_AGREE_MAX` per channel, THAT is the background
     colour and it is cleared with the configured tolerance — logged,
     never silent.

  Only when even the corners disagree (a gradient, a scene) is the
  image **ambiguous** → reported and left alone. The report names the
  colour it saw, so it can be pasted into the custom-colour field —
  skip, never guess, but never a dead end either. Corners, not the
  whole border band: a medallion running to the top edge drags the
  border median, but leaves all four corners sitting on the true
  background.
- **`BG_MODE_BLACK` / `BG_MODE_WHITE`** (owner 2026-07-28) — the owner
  STATING the background; the sniff is skipped entirely.
- **`BG_MODE_COLOR`** (owner 2026-07-28) — any target colour plus a
  `±X %` tolerance (percent of 255, per channel), BOTH owner-editable
  fields. His own worked example: `#FF0000 ± 6.67 %` spans
  `#EE0000`…`#FF1111` (±17 levels). **`0 %` is legal** and keys the
  typed colour EXACTLY.
- **already transparent** → skipped untouched in EVERY mode, forced
  ones included (it has a real alpha channel a colour key knows
  nothing about) — this is what makes re-running a folder safe.

### How the result is written

`process_file` saves through `config.PNG_SAVE_KWARGS` — never with
Pillow's `optimize=True`, which on a 4 Mpx plate costs 9.5 s to save
4.6 % of file size against a 0.3 s removal. See
[Postprocess Config](../config/__about/postprocess.md) → PNG write
settings for the measurement.

### The SAFETY GUARD

`remove_color_background` returns `(rgba, removed_frac)`, and the
caller ABORTS when the fraction cleared exceeds the path's guard
(`SAFETY_GUARD_DEFAULT`). An aborted removal leaves the ORIGINAL
untouched (never a destroyed save): `process_file` returns
`"skip-risky"` and [Postprocess](postprocess.md) returns `"unclear"`,
its message NAMING the guard that fired.

| Path | Guard | Why |
|------|-------|-----|
| black | `SAFETY_MAX_REMOVE_FRAC` (40 %) | tight — a fence around a GUESS (auto may have keyed a dark subject as background) |
| white | `SAFETY_MAX_REMOVE_FRAC_WHITE` (85 %) | legit white backgrounds run large, reaching ~57 % |
| custom | `SAFETY_MAX_REMOVE_FRAC_COLOR` (85 %) | the colour is known — typed, or agreed on by four corners |

The constants are FRACTIONS because the engine compares them against a
fraction; the GUI shows and takes them as PERCENT and converts at the
panel edge. All three are owner-editable per run.

**Known limit (owner 2026-07-28, the "pointers" case).** The black
guard measures AREA, which is only a proxy for "it ate the subject",
and the proxy fails on shapes whose legitimate background is simply
large. 17 disc-in-a-square plates measured 41.2–42.2 % of pure-black
background with the subject fully intact — a perfectly clean cut that
black's 0.40 nonetheless bails on. Stating the colour (`BG_MODE_COLOR`
`#000000`, guard 0.85) is the way through; raising the black guard per
run is the other. Pinned by
`test_pointers_regression_black_guard_bails_custom_colour_succeeds`.

## Connections

### Uses
- numpy, scipy (`ndimage`), Pillow
- [Config (subfolder)](../config/___config.md) — `CROP_INK_ALPHA`,
  `CROP_MIN_INK_PX`, `CLEAN_EDGE_ALPHA` (the ink-crop / edge-cleanup
  thresholds), `BLACK_VOID_MAX` (the black-void brightness ceiling),
  the background-mode constants (`BG_MODE_*`, `BG_COLOR_DEFAULT`,
  `BG_COLOR_TOLERANCE_PCT`, `AUTO_CORNER_PX`, `AUTO_CORNER_AGREE_MAX`)
  and the three SAFETY guards `SAFETY_MAX_REMOVE_FRAC` / `_WHITE` /
  `_COLOR`. Imported package-first (`from painter.config`) with a bare
  `from config` fallback so the standalone script still runs.

### Used by
- [Postprocess](postprocess.md) — uses the internals (`plan`,
  `apply_plan`, `parse_hex_color`, `content_bbox`, `clean_edge_halo`)
  for its two split, composable steps
- [GUI (folder)](../../gui/___gui.md) — `BgSettingsPanel` calls
  `parse_hex_color` to validate the typed colour at Start and to drive
  the live swatch
- The owner, standalone:
  `python painter/bg_remove.py <file-or-folder> --in-place --crop`

## Functions

- `process_file(src, dst, mode, crop, force_full, force_edge, color,
  tolerance_pct) -> str` — one image; returns the action taken, or
  `"skip-risky"` when the SAFETY guard fires (removal too large —
  source left untouched, nothing written). The standalone CLI's engine
  — the per-save pipeline goes through [Postprocess](postprocess.md)
  instead.
- `rgba_array(img) -> np.ndarray` — the image as ONE `(H, W, 4)` uint8
  array: THE single decode + mode-convert the whole removal shares
  (owner decree 2026-08-07, Priority A). One image used to be converted
  FIVE times per removal — `plan` built an RGBA copy for the alpha check
  and an RGB copy for the border sniff, `remove_color_background` built
  its own RGB copy of the same pixels, and `clean_edge_halo` another
  RGBA one; every convert walks every pixel and allocates a full frame.
  Callers now build it once and pass it as the optional `rgba=` argument
  to `plan`/`apply_plan`/`remove_color_background`; RGB inside them is a
  free VIEW (`arr[:, :, :3]`), never a fourth copy. Omitting the
  argument still works and simply builds the array itself, so every
  external caller keeps working unchanged. Measured on a 1664x2550
  plate: a single background removal 1.45s -> 1.29s, output
  byte-identical (verified by sha1 against the previous commit).
- `plan(img, mode, *, color, tolerance_pct, rgba=None) -> RemovalPlan` — decides
  how ONE image is treated (see the modes above). The named tuple
  carries `action`, the `target` colour, `dist_full`/`dist_edge`,
  `sigma`, and `border_hex` (always the colour it saw, so an ambiguous
  skip can say WHICH colour to state instead).
- `corner_background_color(rgb, corner_px, agree_max) -> (r,g,b) |
  None` — the four-corner colour vote (see `BG_MODE_AUTO` above);
  `None` when the corners disagree.
- `apply_plan(img, removal, reach, rgba=None) -> (rgba, removed_frac)` — run the
  engine with one plan's parameters. `reach` is NOT part of the plan:
  it is orthogonal to WHICH colour is the background, so it stays the
  caller's choice rather than something detection decides.
- `remove_color_background(img, target, dist_full, dist_edge, sigma,
  reach) -> (rgba, removed_frac)` — THE engine (see above); the second
  value is the fraction the removal clears, which the guard checks.
- `color_distance(rgb, target)` — the per-pixel Chebyshev distance key.
- `parse_hex_color(text) -> (r, g, b)` — `#FF0000` / `ff0000` / `#f00`;
  loud `ValueError` on anything else (Rule #1 — a mistyped colour must
  never silently become a different one).
- `format_hex_color(rgb) -> str` — the inverse, used to report a
  sniffed border colour back to the owner.
- `tolerance_to_distance(pct) -> int` — the owner's `± X %` as a
  per-channel distance in 0..255 (6.67 % → 17 levels).
- `autocrop` — crop to the ink-based content box.
- `content_bbox(img, ink_alpha, min_ink_px) -> (l, t, r, b) | None`
  — the INK-BASED content box shared by `autocrop` and the
  postprocess crop step. A row/col counts as content only when it
  holds at least `min_ink_px` pixels that are at least `ink_alpha`
  opaque; `None` when no row/col qualifies.
- `clean_edge_halo(img, edge_alpha) -> (rgba_copy, n_cleaned)` — the
  CONSERVATIVE edge-halo cleanup: faint pixels (alpha < `edge_alpha`)
  that connect to the image border are zeroed (reusing
  `edge_connected_background`), while faint pixels enclosed by the
  solid subject stay untouched.
- `main(argv)` — the standalone CLI (`--in-place`, `--crop`,
  `--backup`, `--mode auto|white|black|color`, `--reach edge|all`, and
  for the colour mode `--color '#RRGGBB'` / `--tolerance <percent>`).
