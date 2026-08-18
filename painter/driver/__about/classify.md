# Driver Classify

**Script:** [Driver Classify (script)](../classify.py) ·
**Flow:** [diagram](../__flow/classify.md) ·
**Folder:** [driver/](../___driver.md)

## Purpose
Reading the page's own signals and naming what went wrong: a
quota/refusal marker, a degraded-model banner, a thread-level error, an
"image generation failed" line. This is where a page's TEXT becomes a
typed error.

Keeping it apart from [wait](wait.md) is the point: the wait mixin
decides WHEN a turn is finished, this one decides WHAT that turn means —
and a quota wall must never be blind-retried as if it were a timeout.

`_check_markers(text)` checks marker categories MOST-SPECIFIC-FIRST
(copyright before safety) so the runner picks the matching safer-retry
preamble. `_check_degrade_banner()` raises `ModelDegraded`, while
`degrade_banner_text()` is a NON-raising probe of the same banner used
AFTER a save (the image can arrive even while the banner is up).
`_thread_error_risen()` is the STRUCTURAL detector: the count of the
site's Retry buttons RISING above `Baseline.error_turn_count`, never
mere presence — an error turn from an earlier item stays in the chat,
and treating that as ours would fail every later item.
`_check_image_failed(text)` raises on the site's own
`image_failed_text_markers`, and no-ops silently wherever a site ships
none (Gemini today).

The full per-error reasoning, with its incident history, lives in
[Driver Errors](errors.md).

## Connections

### Uses
- [Config (subfolder)](../../config/___config.md) — `parse_quota_reset`
- [Driver Errors](errors.md) — `ImageGenFailed`, `ItemRefused`,
  `ModelDegraded`, `TerminalState`

### Used by
- [CDP Driver — the package's public surface](__init__.md) — mixed into
  `SiteDriver`
- [Driver Wait](wait.md) — every poll of `await_done` runs these checks

## Classes

### DriverClassifyMixin
`degrade_banner_text`, `_check_degrade_banner`, `_check_markers`,
`_thread_error_risen`, `_check_image_failed`. Never instantiated
alone.
