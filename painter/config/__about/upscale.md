# Upscale Config

**Script:** [Upscale Config (script)](../upscale.py) ·
**Flow:** [diagram](../__flow/upscale.md)

## Purpose

Real-ESRGAN upscaler config (owner's #13): where the downloaded
`realesrgan-ncnn-vulkan` binary lives, which model it runs, and the
gate deciding which images qualify for upscaling.

## Connections

### Uses
- [Paths](paths.md) — `PROJECT_ROOT`

### Used by
- [Upscale](../../__about/upscale.md) (`painter/upscale.py`) —
  `upscale_if_small`'s engine-level gate defaults
- GUI `AgentPanel`/`UpscaleParamsDialog` — the min-side spinner seed,
  step, and the FilterEditor-authored aspect band
- Re-exported by [Config Package Index](__init__.md)

## Constants

- `TOOLS_DIR`, `UPSCALE_DIR`, `UPSCALE_EXE_NAME`, `UPSCALE_ZIP_URL` —
  the gitignored binary's location and the official release zip it is
  downloaded from on first use
- `UPSCALE_MODEL` — `"realesrgan-x4plus-anime"` (owner research
  2026-07-21: art-tuned for this project's flat-colour rondels/badges;
  A/B-verified crisper linework, no colour shift, ~2.4x faster than
  the general-purpose `x4plus` net)
- `UPSCALE_MIN_WIDTH`, `UPSCALE_MIN_HEIGHT` — 800/800, the engine's
  own qualifying minimum
- `UPSCALE_ASPECT_MIN`, `UPSCALE_ASPECT_MAX` — 0.9/1.1, the
  circular/badge aspect band
- `UPSCALE_MINDIM_STEP` — GUI spinner step (px)
- `UPSCALE_MIN_SIDE_DEFAULT` — the GUI's single min-side spinner seed
  (GUI rework Phase 6 collapsed the old two-field width/height gate
  into one spinner; reuses `UPSCALE_MIN_WIDTH`'s value)
