# Paths

**Script:** [Paths (script)](../paths.py) ·
**Flow:** [diagram](../__flow/paths.md)

## Purpose

Project paths, the CDP/Chrome launch block, the output layout (the
`out/` tree that MIRRORS DOMY's `assets/` tree), and the settings
file location. The one leaf every other config submodule that needs
a project-relative path imports from (`PROJECT_ROOT`) — no dependency
on any other config submodule.

## Connections

### Uses
Nothing — a leaf module.

### Used by
- [Chrome Launcher](../../__about/chrome.md) — `CDP_PORT`, `CDP_URL`,
  `CHROME_CANDIDATES`, `CHROME_PROFILE_DIR`, `CHROME_LAUNCH_TIMEOUT_S`
- [Run Loop](../../__about/runner.md) — `STATE_DIRNAME`,
  `REPORT_SUFFIX`, `dest_for`, `versioned_dest_for`
- [Settings](../../__about/settings.md) — `SETTINGS_PATH`
- [Main (Entry Point)](../../../__about/main.md) /
  [GUI (folder)](../../../gui/___gui.md) — `CDP_URL`, `DEFAULT_OUT_DIR`
- [Job Temp](../../__about/jobtemp.md), [Upscale config](upscale.md),
  [AI config](ai.md) — `PROJECT_ROOT` (intra-package and cross-file)
- Re-exported by [Config Package Index](__init__.md)

## Constants

- `PROJECT_ROOT` — the repo root, resolved from this file's own location
- `CDP_PORT`, `CDP_URL` — the CDP attach endpoint
- `CHROME_CANDIDATES` — chrome.exe search paths, tried in order
- `CHROME_PROFILE_DIR` — the project's own Chrome profile folder
  (Chrome 136+ refuses `--remote-debugging-port` on the default profile)
- `CHROME_LAUNCH_TIMEOUT_S` — launch → CDP endpoint answering window
- `DEFAULT_OUT_DIR` — `<project>/out`
- `STATE_DIRNAME` — `_state` (run state + reports, out of the copyable tree)
- `REPORT_SUFFIX` — `_report.txt`
- `SITE_FILE_SUFFIX` — site key → DOMY filename suffix (`chatgpt` →
  `_gpt`, `gemini` → `_gem`, `api_image` → `_api`); THE one authority
  for every generator's suffix (CLAUDE.md "The Generator Suffix
  Registry")
- `SETTINGS_PATH` — the GUI's `settings.json` (gitignored)

## Functions

### `dest_for(drop_path, site_key) -> str`
The save path (relative to the out base) for one drop path — see
[flow](../__flow/paths.md).

### `versioned_dest_for(drop_path, site_key, out_base) -> str`
The dest for a NEW VERSION of an image whose canonical file already
exists — the ticked-redo path (owner 2026-07-27). See
[flow](../__flow/paths.md) for the full algorithm.
