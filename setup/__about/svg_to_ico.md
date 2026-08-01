# ICO Generator

**Script:** [ICO Generator (script)](../svg_to_ico.py) ·
**Flow:** [diagram](../__flow/svg_to_ico.md)

## Purpose

Renders `assets/logo.svg` into a multi-resolution `assets/icon.ico`
(16/32/48/64/128/256 px) for the EXE icon, taskbar, and Add/Remove
Programs entry. Uses adaptive supersampling (render larger, then
Lanczos-downscale) so small icon sizes stay crisp instead of showing
the softness a direct small-size SVG rasterization would produce — a
real image-processing technique, not a single-pass library call, which
is why it gets its own [flow diagram](../__flow/svg_to_ico.md).

## Connections

### Uses
- `assets/logo.svg` (project root `assets/`) — the only input; there is no separate `icon.svg`
- PySide6 (`QtCore`, `QtGui`, `QtSvg`) — `QSvgRenderer` + `QPainter` render the SVG into an antialiased `QImage`
- Pillow (`PIL.Image`) — converts the rendered `QImage` bytes to an RGBA image, Lanczos-resizes supersampled frames, and encodes the final multi-frame ICO

### Used by
- [Build Orchestrator](build.md) — step 1 (`generate_ico()`) shells out to this script (`python setup/svg_to_ico.py`); also runnable standalone

## Functions

- `_render_svg_to_pil(renderer, size) -> Image.Image` — renders the SVG at an adaptively supersampled resolution (4x for `size <= 64`, 2x for `size <= 128`, 1x above that) into a transparent `QImage`, converts the raw BGRA bytes into a Pillow RGBA image, then Lanczos-downscales to the target `size` when a supersample factor was used
- `generate_ico() -> Path` — ensures a `QGuiApplication` exists (required by `QSvgRenderer`), loads `assets/logo.svg`, renders every size in `ICO_SIZES`, warns if any rendered frame is fully transparent, reverses the frame order (largest first — Windows uses the first frame as the primary icon), and saves them as one multi-frame `assets/icon.ico`
- `main()` — CLI entry: prints progress, calls `generate_ico()`, prints the list of sizes generated
