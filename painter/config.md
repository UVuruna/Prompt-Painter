# Config

**Script:** [Config (script)](config.py)

## Purpose
The single home of every tunable value (root Rule #4): connection
and Chrome launch, output layout, sheet-contract constants, the
background tool, timing, and the per-site DOM config blocks.
Selectors rot with every reskin — each DOM hook is a tuple of
fallbacks tried in order, and the driver fails loudly when none
match.

## Connections

### Uses
- Nothing (constants only).

### Used by
- [Sheet Parser](sheet_parser.md) — `IMAGE_EXTENSIONS`,
  `SKIP_MARKER_PATTERN`
- [CDP Driver](driver.md) — `SiteConfig`, `Timing`, `MIN_IMAGE_PX`
- [Run Loop](runner.md) — `Timing`, `PROGRESS_SUFFIX`
- [Chrome Launcher](chrome.md) — `CDP_PORT`, `CHROME_CANDIDATES`,
  `CHROME_PROFILE_DIR`, `CHROME_LAUNCH_TIMEOUT_S`
- [Postprocess](postprocess.md) — `BG_FIX_CROP`
- [Review](review.md) — `STAGING_DIRNAME`, `PROGRESS_SUFFIX`,
  `IMAGE_EXTENSIONS`
- [Main (CLI)](../main.md) / [GUI](../gui.md) — `CDP_URL`,
  `DEFAULT_OUT_DIR`, `SITES`, `TIMING`, `BACKGROUND_MODES`,
  `background_suffix`

## Values

- `CDP_PORT` / `CDP_URL` — Chrome's debug endpoint.
- `CHROME_CANDIDATES` — where chrome.exe usually lives.
- `CHROME_PROFILE_DIR` — the dedicated automation profile
  (`chrome-profile/`, gitignored; Chrome 136+ refuses CDP on the
  default profile). Log in once there; sessions persist.
- `DEFAULT_OUT_DIR`, `STAGING_DIRNAME`, `PROGRESS_SUFFIX` —
  generation stages at `<out>/_staging/<site>/<drop-path>`;
  approval moves images to `<out>/<site>/<drop-path>`; run state
  sits beside the staged images.
- `IMAGE_EXTENSIONS`, `SKIP_MARKER_PATTERN` — the sheet contract's
  file-name rule and the REUSE / SUPERSEDED / DO-NOT-GENERATE
  marker regex.
- `BG_FIX_CROP` — autocrop after clearing a background.
- `BACKGROUND_SUFFIXES` / `BACKGROUND_MODES` /
  `background_suffix(mode, site)` — the GUI-selectable background
  instruction appended to every prompt; `auto` resolves to each
  site's `default_background` (transparent on ChatGPT, white on
  Gemini).
- `MIN_IMAGE_PX` — an `<img>` narrower than this is a placeholder.

## Classes

### Timing
All waits and paces in seconds: the selector timeout (required
elements poll instead of one-shot lookups), busy-appear timeout,
the generation hard timeout, image-ready timeout, poll step,
progress-log cadence, and the polite pause between prompts.

### SiteConfig
One site's block: `url` (the tab the launcher opens),
`url_fragment` (finds the open tab), `default_background` (the
suffix key `auto` resolves to), `prompt_box`, `send_button`,
`busy_signal`
(visible only while generating — its disappearance is the done
edge), `response_container`, `result_image`, and
`refusal_text_markers` (the substrings that mark a no-image
response as terminal).

`SITES` maps `chatgpt` / `gemini` to their blocks.
