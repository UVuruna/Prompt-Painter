# Upscale (Real-ESRGAN)

**Script:** [Upscale (script)](upscale.py)

## Purpose
Owner's #13: some generations come back small. The fix is the
standalone `realesrgan-ncnn-vulkan` Windows binary (Vulkan GPU, no
Python package), kept under `tools/realesrgan/` (gitignored) and
downloaded ON FIRST USE from the official Real-ESRGAN GitHub
release — with live progress logging and loud, instructive failure
when the download or the exe itself cannot run (no Vulkan device).

**The gating (owner 2026-07-19 — four editable params, defaults
reproduce the old locked 2026-07-18 rule):** an image QUALIFIES only
if (1) its aspect ratio W/H is within `[aspect_min, aspect_max]`
(default 0.9–1.1 — the circular/badge class) AND (2) `W < min_width`
OR `H < min_height` (default 800 / 800). Both pass → upscaled so
`W >= min_width` and `H >= min_height`, aspect preserved (the 4x
image is LANCZOS-scaled by the smallest factor keeping BOTH minimums,
so the binding axis lands on its target), PNG in/out so transparency
survives. Anything else → `"nothing"`, so callers count done vs
skipped cleanly. The GUI passes PER-AGENT values (each site's own
fine-tune block) and the standalone Upscale dialog's remembered four
params; the config defaults are the shipped values.

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
- `upscale_if_small(path, log, *, min_width, min_height, aspect_min,
  aspect_max) -> str` — `"done" | "nothing"` per the gating above, in
  place (defaults from config reproduce the old behaviour). Raises
  `UpscaleError` — LOUD but catchable, so a machine without Vulkan
  keeps the rest of the pipeline alive.
