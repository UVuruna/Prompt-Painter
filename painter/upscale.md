# Upscale (Real-ESRGAN)

**Script:** [Upscale (script)](upscale.py)

## Purpose
Owner's #13: some generations come back small. The fix is the
standalone `realesrgan-ncnn-vulkan` Windows binary (Vulkan GPU, no
Python package), kept under `tools/realesrgan/` (gitignored) and
downloaded ON FIRST USE from the official Real-ESRGAN GitHub
release — with live progress logging and loud, instructive failure
when the download or the exe itself cannot run (no Vulkan device).

**The locked gating (owner 2026-07-18):** an image QUALIFIES only
if (1) its aspect ratio W/H is within `1 ± UPSCALE_ASPECT_TOL`
(0.9–1.1 — the circular/badge class) AND (2) W or H is below
`UPSCALE_MIN_PX` (800). Both pass → upscaled so NO dimension stays
below the minimum, aspect preserved, PNG in/out so transparency
survives. Anything else → `"nothing"`, so callers count done vs
skipped cleanly.

**Native 4x only:** the binary always runs the x4plus model's
native 4x and LANCZOS brings the result down to the exact target.
Non-native `-s 2/3` runs were verified LIVE (2026-07-18, a real
rondel) to corrupt the output — tile misalignment, lost detail.

## Connections

### Uses
- [Config](config.md) — the `UPSCALE_*` block, `fmt_size`
- Pillow (LANCZOS correction), `urllib`/`zipfile` (the one-time
  download), `subprocess` (the binary)

### Used by
- [Main (Entry Point)](../main.md) — composed into the `post_save`
  hook (`--upscale`/`--no-upscale`, default on)
- [GUI](../gui.md) — its own composed hook / standalone runs

## Functions

- `ensure_binary(log) -> Path` — the verified exe; downloads and
  unpacks the release zip on first use, probes `-h` once per
  process. Raises `UpscaleError` with manual instructions when the
  download fails or the exe does not run on this machine.
- `upscale_if_small(path, log, *, min_px, aspect_tol) -> str` —
  `"done" | "nothing"` per the gating above, in place. Raises
  `UpscaleError` — LOUD but catchable, so a machine without Vulkan
  keeps the rest of the pipeline alive.
