# Config

**Script:** [Config (script)](config.py)

## Purpose
The single home of every tunable value (root Rule #4): connection,
output, sheet-contract constants, timing, and the per-site DOM
config blocks. Selectors rot with every reskin — each DOM hook is a
tuple of fallbacks tried in order, and the driver fails loudly when
none match.

## Connections

### Uses
- Nothing (constants only).

### Used by
- [Sheet Parser](sheet_parser.md) — `IMAGE_EXTENSIONS`,
  `SKIP_MARKER_PATTERN`
- [CDP Driver](driver.md) — `SiteConfig`, `Timing`, `MIN_IMAGE_PX`
- [Run Loop](runner.md) — `Timing`, `PROGRESS_SUFFIX`
- [Main (CLI)](../main.md) — `CDP_URL`, `DEFAULT_OUT_DIR`, `SITES`,
  `TIMING`

## Values

- `CDP_URL` — Chrome's debug endpoint (`http://localhost:9222`);
  Chrome must be started once with
  `chrome.exe --remote-debugging-port=9222`.
- `DEFAULT_OUT_DIR`, `PROGRESS_SUFFIX` — where images and the
  sidecar run state land.
- `IMAGE_EXTENSIONS`, `SKIP_MARKER_PATTERN` — the sheet contract's
  file-name rule and the REUSE / SUPERSEDED / DO-NOT-GENERATE
  marker regex.
- `MIN_IMAGE_PX` — an `<img>` narrower than this is a placeholder.

## Classes

### Timing
All waits and paces in seconds: busy-appear timeout, the
generation hard timeout, image-ready timeout, poll step, progress-log
cadence, and the polite pause between prompts.

### SiteConfig
One site's DOM state block: `url_fragment` (finds the open tab),
`prompt_box`, `send_button`, `busy_signal` (visible only while
generating — its disappearance is the done edge),
`response_container`, `result_image`, and `refusal_text_markers`
(the substrings that mark a no-image response as terminal).

`SITES` maps `chatgpt` / `gemini` to their blocks.
