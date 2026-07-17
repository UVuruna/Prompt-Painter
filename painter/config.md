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
- [Main (Entry Point)](../main.md) / [GUI](../gui.md) — `CDP_URL`,
  `DEFAULT_OUT_DIR`, `SITES`, `TIMING`, `BACKGROUND_CHOICES`,
  `prompt_suffix`

## Values

- `CDP_PORT` / `CDP_URL` — Chrome's debug endpoint.
- `CHROME_CANDIDATES` — where chrome.exe usually lives.
- `CHROME_PROFILE_DIR` — the dedicated automation profile
  (`chrome-profile/`, gitignored; Chrome 136+ refuses CDP on the
  default profile). Log in once there; sessions persist.
- `DEFAULT_OUT_DIR`, `PROGRESS_SUFFIX`, `REPORT_SUFFIX` — images
  save directly at `<out>/<site>/<drop-path>`; the run state and
  the report sit beside them.
- `IMAGE_EXTENSIONS`, `SKIP_MARKER_PATTERN` — the sheet contract's
  file-name rule and the REUSE / SUPERSEDED / DO-NOT-GENERATE
  marker regex.
- `BG_FIX_CROP` — autocrop after clearing a background.
- `BACKGROUND_CHOICES`, `SITE_PROMPT_RULES`, `GEMINI_ASPECT_RULES`,
  `prompt_suffix(site_key, background, prompt_text)` — the rule
  block appended to every prompt: the chosen background (each
  site's dropdown defaults to its `default_background` — ChatGPT
  transparent, Gemini white) plus the site's forced laws (owner
  2026-07-17). Gemini's aspect law is picked FROM THE PROMPT:
  TALL/lancet prompts get tall portrait, everything else (badges,
  rondels, medallions) a perfect 1:1 square; plus NO reflections.
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
