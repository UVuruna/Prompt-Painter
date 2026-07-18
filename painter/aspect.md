# Change Aspect Ratio

**Script:** [Change Aspect Ratio (script)](aspect.py)

## Purpose
The owner's standalone batch **deform** tool (2026-07-19): pick a
folder and a target ratio `X:Y`, then non-proportionally STRETCH every
image to that ratio IN PLACE. It stands beside the other in-place batch
tools (background removal, crop, upscale) and reports on the dashboard
the same way — `done` = resized, `nothing`/Refused = already at ratio.

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
- Pillow (LANCZOS resize, PNG save)

### Used by
- [GUI](../gui.md) — the standalone **"Aspect ratio…"** toolbar button
  (its `AspectRatioDialog` asks for `W : H`, then the run reuses the
  generic standalone-tool plumbing with the ratio bound in)

## Functions

- `change_aspect(path, ratio_w, ratio_h, log, *, tol=ASPECT_TOL) -> str`
  — stretch one image to the target ratio in place. Returns `"done"`
  (resized) or `"nothing"` (already at ratio within `tol`; the file is
  left BYTE-UNCHANGED — no write). Raises `AspectError` loudly on a
  non-positive target ratio or a real image failure; a no-op never
  raises, so a batch survives one bad file.

## Design Decisions

- **Grow-only, never shrink.** Stretching one axis up (rather than
  cropping or letterboxing) keeps every original pixel; the owner wants
  the whole image forced to the frame, deformation accepted.
- **Byte-unchanged no-op.** An image already at the target ratio
  returns `"nothing"` BEFORE any save, so re-running the tool over a
  finished folder rewrites nothing and the Refused count is honest.
- **Same shape as the other standalone tools** (`func(path, log) ->
  str`), so the GUI drives all four (BG removal / crop / upscale /
  aspect) through one loop with one dashboard-reporting path.
